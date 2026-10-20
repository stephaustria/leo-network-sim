from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Scenario
from app.db.session import get_db
from app.sim.scenario import DEFAULT_SCENARIO_NAME, ScenarioConfig, describe
from app.sim.worlds import World, get_world

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class ScenarioIn(BaseModel):
    name: Name
    description: str | None = Field(None, max_length=500)
    config: ScenarioConfig = Field(default_factory=ScenarioConfig)


class PreviewIn(BaseModel):
    config: ScenarioConfig = Field(default_factory=ScenarioConfig)


def _world_or_422(cfg: ScenarioConfig) -> World | None:
    """Scenarios that use TLE data are built here, which checks the sets exist and the filters match."""
    if not cfg.tle_shells:
        return None
    try:
        return get_world(cfg)
    except ValueError as exc:                        # includes TleError
        raise HTTPException(422, str(exc))


def _brief(s: Scenario) -> dict:
    cfg = ScenarioConfig.model_validate(s.config)
    n_sats = cfg.total_sats()
    if cfg.tle_shells:
        try:
            n_sats = get_world(cfg).model.c.n_sats
        except ValueError:
            pass
    return {"id": s.id, "name": s.name, "description": s.description,
            "created_at": s.created_at, "updated_at": s.updated_at,
            "n_sats": n_sats, "n_stations": len(cfg.stations)}


def _full(s: Scenario) -> dict:
    cfg = ScenarioConfig.model_validate(s.config)
    return {**_brief(s), "config": cfg.model_dump(), "summary": describe(cfg, _world_or_422(cfg))}


def _get_or_404(db: Session, scenario_id: int) -> Scenario:
    row = db.get(Scenario, scenario_id)
    if row is None:
        raise HTTPException(404, "scenario not found")
    return row


# static routes first, so "default" and "preview" are never parsed as an id
@router.get("/default")
def default_scenario():
    cfg = ScenarioConfig()
    return {"name": DEFAULT_SCENARIO_NAME,
            "description": "Built-in scenario used when no scenario is selected",
            "config": cfg.model_dump(), "summary": describe(cfg)}


@router.post("/preview")
def preview(req: PreviewIn):
    return {"valid": True, "summary": describe(req.config, _world_or_422(req.config))}


@router.get("")
def list_scenarios(db: Session = Depends(get_db)):
    return [_brief(s) for s in db.scalars(select(Scenario).order_by(Scenario.name))]


@router.post("", status_code=201)
def create_scenario(req: ScenarioIn, db: Session = Depends(get_db)):
    if db.scalar(select(Scenario.id).where(Scenario.name == req.name)) is not None:
        raise HTTPException(409, "a scenario with that name already exists")
    _world_or_422(req.config)
    row = Scenario(name=req.name, description=req.description, config=req.config.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "a scenario with that name already exists")
    db.refresh(row)
    return _full(row)


@router.get("/{scenario_id}")
def get_scenario(scenario_id: int, db: Session = Depends(get_db)):
    return _full(_get_or_404(db, scenario_id))


@router.put("/{scenario_id}")
def update_scenario(scenario_id: int, req: ScenarioIn, db: Session = Depends(get_db)):
    row = _get_or_404(db, scenario_id)
    clash = db.scalar(select(Scenario.id).where(Scenario.name == req.name, Scenario.id != scenario_id))
    if clash is not None:
        raise HTTPException(409, "a scenario with that name already exists")
    _world_or_422(req.config)
    row.name, row.description, row.config = req.name, req.description, req.config.model_dump()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "a scenario with that name already exists")
    db.refresh(row)
    return _full(row)


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, scenario_id))
    db.commit()