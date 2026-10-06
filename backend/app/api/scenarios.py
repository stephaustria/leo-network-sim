from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Scenario
from app.db.session import get_db
from app.sim.scenario import ScenarioConfig, describe

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class ScenarioIn(BaseModel):
    name: Name
    description: str | None = Field(None, max_length=500)
    config: ScenarioConfig = Field(default_factory=ScenarioConfig)


class PreviewIn(BaseModel):
    config: ScenarioConfig = Field(default_factory=ScenarioConfig)


def _brief(s: Scenario) -> dict:
    cfg = ScenarioConfig.model_validate(s.config)
    return {"id": s.id, "name": s.name, "description": s.description,
            "created_at": s.created_at, "updated_at": s.updated_at,
            "n_sats": cfg.constellation.planes * cfg.constellation.sats_per_plane,
            "n_stations": len(cfg.stations)}


def _full(s: Scenario) -> dict:
    cfg = ScenarioConfig.model_validate(s.config)
    return {**_brief(s), "config": cfg.model_dump(), "summary": describe(cfg)}


def _get_or_404(db: Session, scenario_id: int) -> Scenario:
    row = db.get(Scenario, scenario_id)
    if row is None:
        raise HTTPException(404, "scenario not found")
    return row


# static routes first, so "default" and "preview" are never parsed as an id
@router.get("/default")
def default_scenario():
    cfg = ScenarioConfig()
    return {"name": "Default (Starlink-like shell)",
            "description": "Built-in scenario used when no scenario is selected",
            "config": cfg.model_dump(), "summary": describe(cfg)}


@router.post("/preview")
def preview(req: PreviewIn):
    return {"valid": True, "summary": describe(req.config)}


@router.get("")
def list_scenarios(db: Session = Depends(get_db)):
    return [_brief(s) for s in db.scalars(select(Scenario).order_by(Scenario.name))]


@router.post("", status_code=201)
def create_scenario(req: ScenarioIn, db: Session = Depends(get_db)):
    if db.scalar(select(Scenario.id).where(Scenario.name == req.name)) is not None:
        raise HTTPException(409, "a scenario with that name already exists")
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