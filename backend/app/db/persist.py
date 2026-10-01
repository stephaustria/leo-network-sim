from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.links import model as link_model
from app.db.models import (FlowSample, HandoffRecord, LinkSample, SimulationRun,
                           TickMetric)
from app.db.session import SessionLocal
from app.sim.engine import Simulation, StepResult


def persist_tick(db: Session, run_id: int, res: StepResult) -> None:
    t = res.t
    db.add(TickMetric(run_id=run_id, **res.metrics))   # metrics keys match the columns
    db.add_all(
        HandoffRecord(run_id=run_id, t=t, station=e.station, from_sat=e.from_sat,
                      to_sat=e.to_sat, reason=e.reason)
        for e in res.handoffs
    )
    db.add_all(FlowSample(run_id=run_id, t=t, **asdict(f)) for f in res.flows)
    db.add_all(
        LinkSample(run_id=run_id, t=t, u=u, v=v, kind=d["kind"],
                   distance_km=d["distance_km"], load_gbps=d["load_gbps"],
                   capacity_gbps=d["capacity_gbps"], utilization=d["utilization"],
                   queue_ms=d["queue_ms"], loss_eff=d["loss_eff"])
        for u, v, d in res.graph.edges(data=True) if d["load_gbps"] > 0
    )


def execute_run(run_id: int, session_factory=SessionLocal) -> None:
    """Run the simulation for a stored run, committing after every tick."""
    db = session_factory()
    try:
        run = db.get(SimulationRun, run_id)
        p = run.params
        steps = int(p["duration"] // p["dt"])
        sim = Simulation(link_model, load_scale=p["load_scale"])

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