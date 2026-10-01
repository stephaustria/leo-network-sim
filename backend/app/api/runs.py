from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import (FlowSample, HandoffRecord, LinkSample, SimulationRun,
                           TickMetric)
from app.db.persist import execute_run
from app.db.session import get_db, get_session_factory

router = APIRouter(prefix="/runs", tags=["runs"])

MAX_TICKS = 240


class RunRequest(BaseModel):
    t_start: float = 0.0
    duration: float = Field(1800.0, gt=0, le=7200)
    dt: float = Field(60.0, ge=10, le=600)
    load_scale: float = Field(1.0, ge=0, le=200)

    @model_validator(mode="after")
    def check_tick_count(self):
        if self.duration // self.dt > MAX_TICKS:
            raise ValueError(f"too many ticks (max {MAX_TICKS}); raise dt or lower duration")
        return self


def to_dict(obj, exclude=("id", "run_id")) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in exclude}


def get_run_or_404(db: Session, run_id: int) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


def nearest_tick(db: Session, run_id: int, t: float | None) -> float:
    if t is None:
        q = select(func.max(TickMetric.t)).where(TickMetric.run_id == run_id)
    else:
        q = (select(TickMetric.t).where(TickMetric.run_id == run_id)
             .order_by(func.abs(TickMetric.t - t)).limit(1))
    found = db.execute(q).scalar()
    if found is None:
        raise HTTPException(404, "no ticks stored for this run yet")
    return found


@router.post("", status_code=202)
def create_run(req: RunRequest, background: BackgroundTasks,
               db: Session = Depends(get_db),
               session_factory: Callable = Depends(get_session_factory)):
    run = SimulationRun(params=req.model_dump(), status="running")
    db.add(run)
    db.commit()
    background.add_task(execute_run, run.id, session_factory)
    return {"id": run.id, "status": run.status,
            "ticks_expected": int(req.duration // req.dt) + 1}


@router.get("")
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(limit))
    return [{"id": r.id, **to_dict(r)} for r in runs]


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id)
    return {"id": run.id, **to_dict(run)}


@router.get("/{run_id}/timeline")
def timeline(run_id: int, db: Session = Depends(get_db)):
    get_run_or_404(db, run_id)
    rows = db.scalars(select(TickMetric).where(TickMetric.run_id == run_id).order_by(TickMetric.t))
    return [to_dict(r) for r in rows]


@router.get("/{run_id}/handoffs")
def handoffs(run_id: int, include_acquired: bool = False, db: Session = Depends(get_db)):
    get_run_or_404(db, run_id)
    q = select(HandoffRecord).where(HandoffRecord.run_id == run_id)
    if not include_acquired:
        q = q.where(HandoffRecord.reason != "acquired")
    return [to_dict(r) for r in db.scalars(q.order_by(HandoffRecord.t, HandoffRecord.station))]


@router.get("/{run_id}/flows")
def flows(run_id: int, t: float | None = None, db: Session = Depends(get_db)):
    get_run_or_404(db, run_id)
    tick = nearest_tick(db, run_id, t)
    rows = db.scalars(select(FlowSample).where(FlowSample.run_id == run_id, FlowSample.t == tick)
                      .order_by(FlowSample.id))
    return {"run_id": run_id, "t": tick, "flows": [to_dict(r, ("id", "run_id", "t")) for r in rows]}


@router.get("/{run_id}/links")
def links(run_id: int, t: float | None = None, db: Session = Depends(get_db)):
    get_run_or_404(db, run_id)
    tick = nearest_tick(db, run_id, t)
    rows = db.scalars(select(LinkSample).where(LinkSample.run_id == run_id, LinkSample.t == tick)
                      .order_by(LinkSample.utilization.desc()))
    return {"run_id": run_id, "t": tick, "links": [to_dict(r, ("id", "run_id", "t")) for r in rows]}


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id)
    for model in (LinkSample, FlowSample, HandoffRecord, TickMetric):
        db.execute(delete(model).where(model.run_id == run_id))
    db.delete(run)
    db.commit()