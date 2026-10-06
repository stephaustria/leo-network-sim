from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.links import model
from app.sim.engine import Simulation

router = APIRouter(prefix="/simulation", tags=["simulation"])

MAX_TICKS = 60


@router.get("/run")
def run(
    t_start: float = 0.0,
    duration: float = Query(1800.0, gt=0, le=7200),
    dt: float = Query(60.0, ge=10, le=600),
    load_scale: float = Query(1.0, ge=0, le=200),
    policy: Literal["min_hop", "shortest_latency", "congestion_aware"] = "congestion_aware",
):
    steps = int(duration // dt)
    if steps > MAX_TICKS:
        raise HTTPException(400, f"Too many ticks ({steps}); max {MAX_TICKS}. Raise dt or lower duration.")

    sim = Simulation(model, load_scale=load_scale, policy=policy)
    timeline, handoffs, last = [], [], None
    for k in range(steps + 1):
        last = sim.tick(t_start + k * dt)
        timeline.append(last.metrics)
        handoffs += [e.to_dict() for e in last.handoffs if e.reason != "acquired"]

    return {
        "params": {"t_start": t_start, "duration": duration, "dt": dt,
                   "load_scale": load_scale, "policy": policy},
        "timeline": timeline,
        "handoff_events": handoffs,
        "final_flows": last.flows_detail(),
    }