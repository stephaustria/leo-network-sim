import asyncio
import json
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.links import model as link_model
from app.api.runs import to_dict
from app.db.models import FlowSample, HandoffRecord, LinkSample, TickMetric
from app.db.session import get_session_factory
from app.sim.engine import Simulation
from app.sim.routing import default_flows
from app.sim.stream import build_frame, init_message, live_frame, sat_latlon

router = APIRouter(tags=["websocket"])


def clamp(x, lo, hi) -> float:
    return max(lo, min(hi, float(x)))


async def pace(get_speed: Callable[[], float], began: float) -> None:
    """Sleep until 1/speed seconds have passed, re-reading speed so changes apply fast."""
    while True:
        remaining = 1.0 / get_speed() - (time.monotonic() - began)
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, 0.05))


class Channel:
    """Serializes sends and tears down the reader task."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.lock = asyncio.Lock()

    async def send(self, msg: dict) -> None:
        async with self.lock:
            await self.ws.send_json(msg)

    async def read_commands(self, apply) -> None:
        while True:
            raw = await self.ws.receive_text()
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError("message must be a JSON object")
            except ValueError as exc:
                await self.send({"type": "error", "message": f"bad message: {exc}"})
                continue
            err = apply(msg)
            await self.send({"type": "error", "message": err} if err else apply.state_msg())


async def shutdown(task: asyncio.Task) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


# ------------------------------------------------------------------ live

@dataclass
class LiveState:
    started: bool = False
    paused: bool = False
    reset: bool = False
    t_start: float = 0.0
    t_end: float = 7200.0
    t: float = 0.0
    dt: float = 30.0
    speed: float = 1.0          # ticks per wall-clock second
    load_scale: float = 1.0

    def message(self) -> dict:
        return {"type": "state", "running": self.started and not self.paused,
                "started": self.started, "paused": self.paused, "t": self.t,
                "dt": self.dt, "speed": self.speed, "load_scale": self.load_scale}


class LiveCommands:
    def __init__(self, state: LiveState):
        self.state = state

    def state_msg(self) -> dict:
        return self.state.message()

    def __call__(self, msg: dict) -> str | None:
        s, cmd = self.state, msg.get("cmd")
        try:
            if cmd == "start":
                s.t_start = float(msg.get("t_start", 0.0))
                s.dt = clamp(msg.get("dt", s.dt), 10, 600)
                s.t_end = s.t_start + clamp(msg.get("duration", 7200), s.dt, 86400)
                s.speed = clamp(msg.get("speed", s.speed), 0.1, 20)
                s.load_scale = clamp(msg.get("load_scale", s.load_scale), 0, 200)
                s.started, s.paused, s.reset = True, False, True
            elif cmd == "pause":
                s.paused = True
            elif cmd == "resume":
                s.paused = False
            elif cmd == "stop":
                s.started = False
            elif cmd == "set":
                if "speed" in msg:
                    s.speed = clamp(msg["speed"], 0.1, 20)
                if "load_scale" in msg:
                    s.load_scale = clamp(msg["load_scale"], 0, 200)
                if "dt" in msg:
                    s.dt = clamp(msg["dt"], 10, 600)
            else:
                return f"unknown cmd: {cmd!r}"
        except (TypeError, ValueError) as exc:
            return f"invalid value: {exc}"
        return None


@router.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    ch = Channel(ws)
    state = LiveState()
    sim: Simulation | None = None

    await ch.send(init_message(link_model, default_flows(len(link_model.stations))))
    await ch.send(state.message())
    reader = asyncio.create_task(ch.read_commands(LiveCommands(state)))

    try:
        while not reader.done():
            if not state.started or state.paused:
                await asyncio.sleep(0.05)
                continue
            if state.reset or sim is None:
                sim = Simulation(link_model, load_scale=state.load_scale)
                state.t = state.t_start
                state.reset = False

            sim.load_scale = state.load_scale          # live traffic changes apply next tick
            began = time.monotonic()
            res = await asyncio.to_thread(sim.tick, state.t)

            progress = {"tick": int((state.t - state.t_start) // state.dt),
                        "of": int((state.t_end - state.t_start) // state.dt) + 1}
            await ch.send(live_frame(link_model, res, progress))

            state.t += state.dt
            if state.t > state.t_end:
                state.started = False
                await ch.send({"type": "done", "t": res.t})
            await pace(lambda: state.speed, began)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await shutdown(reader)


# ---------------------------------------------------------------- replay

@dataclass
class ReplayState:
    idx: int = 0
    paused: bool = False
    pending: bool = False       # emit exactly one frame even while paused (after a seek)
    done_sent: bool = False
    speed: float = 1.0

    def message(self) -> dict:
        return {"type": "state", "paused": self.paused, "speed": self.speed, "index": self.idx}


class ReplayCommands:
    def __init__(self, state: ReplayState, times: list[float]):
        self.state, self.times = state, times

    def state_msg(self) -> dict:
        return self.state.message()

    def __call__(self, msg: dict) -> str | None:
        s, cmd = self.state, msg.get("cmd")
        try:
            if cmd == "pause":
                s.paused = True
            elif cmd == "resume":
                s.paused = False
            elif cmd == "speed":
                s.speed = clamp(msg["speed"], 0.1, 60)
            elif cmd == "seek":
                t = float(msg["t"])
                s.idx = min(range(len(self.times)), key=lambda i: abs(self.times[i] - t))
                s.pending, s.done_sent = True, False
            elif cmd == "restart":
                s.idx, s.paused, s.pending, s.done_sent = 0, False, True, False
            else:
                return f"unknown cmd: {cmd!r}"
        except (KeyError, TypeError, ValueError) as exc:
            return f"invalid value: {exc}"
        return None


def load_tick_times(session_factory, run_id: int) -> list[float]:
    with session_factory() as db:
        return list(db.scalars(
            select(TickMetric.t).where(TickMetric.run_id == run_id).order_by(TickMetric.t)))


def load_replay_frame(session_factory, run_id: int, t: float, idx: int, n: int) -> dict:
    with session_factory() as db:
        metrics = db.scalars(select(TickMetric).where(
            TickMetric.run_id == run_id, TickMetric.t == t)).one()
        flows = db.scalars(select(FlowSample).where(
            FlowSample.run_id == run_id, FlowSample.t == t).order_by(FlowSample.id))
        links = db.scalars(select(LinkSample).where(
            LinkSample.run_id == run_id, LinkSample.t == t))
        handoffs = db.scalars(select(HandoffRecord).where(
            HandoffRecord.run_id == run_id, HandoffRecord.t == t))
        return build_frame(
            t=t, mode="replay", sats=sat_latlon(link_model.c, t),
            links=[to_dict(l, ("id", "run_id", "t")) for l in links],
            flows=[to_dict(f, ("id", "run_id", "t")) for f in flows],
            handoffs=[to_dict(h, ("id", "run_id")) for h in handoffs],
            metrics=to_dict(metrics), progress={"tick": idx, "of": n},
        )


@router.websocket("/ws/replay/{run_id}")
async def ws_replay(ws: WebSocket, run_id: int,
                    session_factory: Callable = Depends(get_session_factory)):
    await ws.accept()
    ch = Channel(ws)

    times = await asyncio.to_thread(load_tick_times, session_factory, run_id)
    if not times:
        await ch.send({"type": "error", "message": "run not found or has no ticks yet"})
        await ws.close(code=4404)
        return

    state = ReplayState()
    await ch.send(init_message(link_model, default_flows(len(link_model.stations))))
    await ch.send(state.message())
    reader = asyncio.create_task(ch.read_commands(ReplayCommands(state, times)))

    try:
        while not reader.done():
            if state.paused and not state.pending:
                await asyncio.sleep(0.05)
                continue
            if state.idx >= len(times):
                if not state.done_sent:
                    state.done_sent = True
                    await ch.send({"type": "done", "t": times[-1]})
                state.pending = False
                await asyncio.sleep(0.05)
                continue

            began, i = time.monotonic(), state.idx
            frame = await asyncio.to_thread(
                load_replay_frame, session_factory, run_id, times[i], i, len(times))
            await ch.send(frame)
            state.pending = False
            if state.idx == i:                 # unchanged by a concurrent seek
                state.idx += 1
            await pace(lambda: state.speed, began)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await shutdown(reader)