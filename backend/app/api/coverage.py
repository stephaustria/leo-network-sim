import json
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import world_from_query
from app.sim.coverage import (MAX_WORK, CoverageParams, compute_coverage, valid_resolution,
                              work_estimate)
from app.sim.scenario import ScenarioConfig
from app.sim.worlds import World, get_world

router = APIRouter(prefix="/coverage", tags=["coverage"])


@lru_cache(maxsize=8)
def _cached(config_json: str, res_deg: float, window_hours: float, step_s: float) -> dict:
    world = get_world(ScenarioConfig.model_validate_json(config_json))
    return compute_coverage(world.model, CoverageParams(res_deg, window_hours, step_s))


@router.get("")
def coverage(
    res_deg: float = Query(5.0, ge=1, le=30),
    window_hours: float = Query(12.0, ge=1, le=48),
    step_s: float = Query(180.0, ge=30, le=900),
    world: World = Depends(world_from_query),
):
    if not valid_resolution(res_deg):
        raise HTTPException(422, "res_deg must divide 180 evenly (for example 1, 2, 5, 10, 15 or 30)")

    params = CoverageParams(res_deg, window_hours, step_s)
    work = work_estimate(res_deg, world.model.c.n_sats, params.samples)
    if work > MAX_WORK:
        raise HTTPException(
            422, f"request too heavy ({work:.1e} > {MAX_WORK:.1e}); use a coarser grid, "
                 "a shorter window or a larger step")

    key = json.dumps(world.config.model_dump(), sort_keys=True)
    return _cached(key, res_deg, window_hours, step_s)       # repeated requests are instant