from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Scenario
from app.db.session import get_db
from app.sim.scenario import DEFAULT_SCENARIO_NAME, ScenarioConfig
from app.sim.worlds import World, world_for_params


def scenario_snapshot(db: Session, scenario_id: int | None) -> dict:
    """{'id', 'name', 'config'} for a stored scenario, or for the built-in default when id is None."""
    if scenario_id is None:
        return {"id": None, "name": DEFAULT_SCENARIO_NAME, "config": ScenarioConfig().model_dump()}
    row = db.get(Scenario, scenario_id)
    if row is None:
        raise HTTPException(404, f"scenario {scenario_id} not found")
    return {"id": row.id, "name": row.name,
            "config": ScenarioConfig.model_validate(row.config).model_dump()}


def world_from_query(scenario_id: int | None = None, db: Session = Depends(get_db)) -> World:
    """FastAPI dependency: the world for ?scenario_id=, or the default world."""
    return world_for_params({"scenario": scenario_snapshot(db, scenario_id)})