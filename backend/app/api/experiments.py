import json
import uuid
from typing import Callable, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.links import model as link_model
from app.api.runs import RunRequest, purge_run, to_dict
from app.db.models import SimulationRun, TickMetric
from app.db.persist import execute_run
from app.db.session import get_db, get_session_factory
from app.sim.analysis import failure_window, summarize_arm, tick_goodput
from app.sim.presets import preset_failures
from app.sim.routing import POLICIES

router = APIRouter(prefix="/experiments", tags=["experiments"])

MAX_EXPERIMENT_TICKS = 120
ALLOWED_METRICS = ({c.name for c in TickMetric.__table__.columns} - {"id", "run_id", "t"}) | {"goodput"}
DEFAULT_METRICS = "goodput,mean_latency_ms,mean_hops,route_changes,overloaded_links,max_link_util"


class Arm(BaseModel):
    policy: Literal["min_hop", "shortest_latency", "congestion_aware"]
    route_stickiness: float = Field(0.0, ge=0, le=0.5)
    label: str | None = Field(None, max_length=60)


class ExperimentRequest(BaseModel):
    name: str = Field("experiment", max_length=80)
    preset: Literal["none", "plane_outage", "adjacent_planes", "station_loss", "plane_seam_cut"] = "none"
    t_start: float = 0.0
    duration: float = Field(1800.0, gt=0, le=7200)
    dt: float = Field(60.0, ge=10, le=600)
    load_scale: float = Field(1.0, ge=0, le=200)
    failures: list[dict] = Field(default_factory=list, max_length=50)   # overrides the preset
    link_params: dict[str, float] = Field(default_factory=dict)
    arms: list[Arm] = Field(default_factory=lambda: [Arm(policy=p) for p in POLICIES],
                            min_length=2, max_length=6)

    @model_validator(mode="after")
    def check_ticks(self):
        if self.duration // self.dt > MAX_EXPERIMENT_TICKS:
            raise ValueError(f"too many ticks (max {MAX_EXPERIMENT_TICKS}); raise dt or lower duration")
        return self


def arm_label(a: Arm) -> str:
    if a.label:
        return a.label
    return a.policy + (f" + stickiness {a.route_stickiness:g}" if a.route_stickiness > 0 else "")


def experiment_runs(db: Session, exp_id: str) -> list[SimulationRun]:
    rows = db.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(1000))
    runs = [r for r in rows if (r.params.get("experiment") or {}).get("id") == exp_id]
    if not runs:
        raise HTTPException(404, "experiment not found")
    return sorted(runs, key=lambda r: r.id)


def aggregate_status(runs: list[SimulationRun]) -> str:
    statuses = {r.status for r in runs}
    if "failed" in statuses:
        return "failed"
    return "running" if "running" in statuses else "completed"


def run_ticks(db: Session, run_id: int) -> list[dict]:
    rows = db.scalars(select(TickMetric).where(TickMetric.run_id == run_id).order_by(TickMetric.t))
    return [to_dict(r) for r in rows]


@router.post("", status_code=202)
def create_experiment(req: ExperimentRequest, background: BackgroundTasks,
                      db: Session = Depends(get_db),
                      session_factory: Callable = Depends(get_session_factory)):
    failures = req.failures or preset_failures(
        req.preset, req.t_start, req.duration, req.dt, link_model.c, link_model.pairs)
    exp_id = uuid.uuid4().hex[:12]

    runs = []
    try:
        for i, arm in enumerate(req.arms):
            run_req = RunRequest(
                t_start=req.t_start, duration=req.duration, dt=req.dt, load_scale=req.load_scale,
                policy=arm.policy, route_stickiness=arm.route_stickiness,
                failures=failures, link_params=req.link_params)
            params = run_req.model_dump()
            params["experiment"] = {
                "id": exp_id, "name": req.name, "preset": req.preset, "arm_index": i,
                "arm": {"policy": arm.policy, "route_stickiness": arm.route_stickiness,
                        "label": arm_label(arm)},
            }
            run = SimulationRun(params=params, status="running")
            db.add(run)
            runs.append(run)
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(422, detail=json.loads(exc.json()))

    db.commit()
    for run in runs:                       # background tasks run one after another
        background.add_task(execute_run, run.id, session_factory)

    return {"experiment_id": exp_id, "runs": [r.id for r in runs],
            "ticks_per_run": int(req.duration // req.dt) + 1}


@router.get("")
def list_experiments(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(500))
    groups: dict[str, list[SimulationRun]] = {}
    for r in rows:
        exp = r.params.get("experiment")
        if exp:
            groups.setdefault(exp["id"], []).append(r)
    out = []
    for exp_id, runs in list(groups.items())[:limit]:
        runs.sort(key=lambda r: r.id)
        meta = runs[0].params["experiment"]
        out.append({"id": exp_id, "name": meta["name"], "preset": meta["preset"],
                    "created_at": runs[0].created_at, "status": aggregate_status(runs),
                    "arms": [{"run_id": r.id, "label": r.params["experiment"]["arm"]["label"],
                              "status": r.status} for r in runs]})
    return out


@router.get("/{exp_id}")
def get_experiment(exp_id: str, db: Session = Depends(get_db)):
    runs = experiment_runs(db, exp_id)
    first = runs[0].params
    arms = []
    for r in runs:
        arm = r.params["experiment"]["arm"]
        entry = {"run_id": r.id, "label": arm["label"], "policy": arm["policy"],
                 "route_stickiness": arm["route_stickiness"], "status": r.status,
                 "n_ticks": r.n_ticks}
        if r.status == "completed":
            entry["summary"] = summarize_arm(run_ticks(db, r.id), r.params)
        arms.append(entry)
    return {
        "id": exp_id, "name": first["experiment"]["name"], "preset": first["experiment"]["preset"],
        "status": aggregate_status(runs),
        "params": {k: first[k] for k in ("t_start", "duration", "dt", "load_scale",
                                         "failures", "link_params")},
        "failure_window": failure_window(first.get("failures")),
        "arms": arms,
    }


@router.get("/{exp_id}/timelines")
def timelines(exp_id: str, metrics: str = DEFAULT_METRICS, db: Session = Depends(get_db)):
    wanted = [m.strip() for m in metrics.split(",") if m.strip()]
    bad = [m for m in wanted if m not in ALLOWED_METRICS]
    if bad:
        raise HTTPException(422, f"unknown metrics {bad}; allowed: {sorted(ALLOWED_METRICS)}")

    runs = experiment_runs(db, exp_id)
    arms = []
    for r in runs:
        series = []
        for tick in run_ticks(db, r.id):
            row = {"t": tick["t"]}
            for m in wanted:
                row[m] = tick_goodput(tick, r.params) if m == "goodput" else tick.get(m)
            series.append(row)
        arms.append({"run_id": r.id, "label": r.params["experiment"]["arm"]["label"], "series": series})
    return {"experiment_id": exp_id, "metrics": wanted,
            "failure_window": failure_window(runs[0].params.get("failures")), "arms": arms}


@router.delete("/{exp_id}", status_code=204)
def delete_experiment(exp_id: str, db: Session = Depends(get_db)):
    for run in experiment_runs(db, exp_id):
        purge_run(db, run)
    db.commit()