from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (FlowSample, HandoffRecord, LinkSample, SimulationRun,
                           TickMetric)
from app.db.session import SessionLocal
from app.sim.engine import Simulation, StepResult
from app.sim.failures import FailureSchedule
from app.sim.routing import TrafficParams
from app.sim.serving import DEFAULT_HYSTERESIS_DEG
from app.sim.stream import links_from_graph
from app.sim.worlds import world_for_params


def persist_tick(db: Session, run_id: int, res: StepResult) -> None:
    t = res.t
    db.add(TickMetric(run_id=run_id, **res.metrics))   # metrics keys match the columns
    db.add_all(
        HandoffRecord(run_id=run_id, t=t, station=e.station, from_sat=e.from_sat,
                      to_sat=e.to_sat, reason=e.reason)
        for e in res.handoffs
    )
    db.add_all(FlowSample(run_id=run_id, t=t, **asdict(f)) for f in res.flows)
    db.add_all(LinkSample(run_id=run_id, t=t, **l) for l in links_from_graph(res.graph))


def execute_run(run_id: int, session_factory=SessionLocal) -> None:
    """Run the simulation for a stored run, committing after every tick."""
    db = session_factory()
    try:
        run = db.get(SimulationRun, run_id)
        p = run.params
        world = world_for_params(p)              # the run's own scenario snapshot
        model = world.model
        steps = int(p["duration"] // p["dt"])
        sim = Simulation(
            model,
            flows=world.flows(),
            load_scale=p["load_scale"],
            params=TrafficParams(route_stickiness=p.get("route_stickiness", 0.0)),
            policy=p.get("policy", "congestion_aware"),
            hysteresis_deg=p.get("hysteresis_deg", DEFAULT_HYSTERESIS_DEG),
            schedule=FailureSchedule.from_dicts(p.get("failures"), model.c, len(model.stations)),
        )

        for k in range(steps + 1):
            persist_tick(db, run_id, sim.tick(p["t_start"] + k * p["dt"]))
            run.n_ticks = k + 1
            db.commit()

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(SimulationRun, run_id)
        run.status = "failed"
        run.error = str(exc)[:500]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()