import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from .links import LinkModel, with_overrides
from .routing import Flow, default_flows
from .scenario import ScenarioConfig, build_world

TleLoader = Callable[[int], str]
_tle_loader: TleLoader | None = None


@dataclass(frozen=True)
class World:
    model: LinkModel
    flow_demand_gbps: float
    config: ScenarioConfig

    def flows(self) -> list[Flow]:
        return default_flows(len(self.model.stations), self.flow_demand_gbps)


@lru_cache(maxsize=8)
def _build(config_json: str) -> World:
    cfg = ScenarioConfig.model_validate_json(config_json)
    return World(build_world(cfg, _tle_loader), cfg.flow_demand_gbps, cfg)


def set_tle_loader(loader: TleLoader | None) -> None:
    """Where scenarios find TLE text. Clears cached worlds, which may have used another source.
    TLE sets are immutable, so the cache is safe otherwise."""
    global _tle_loader
    _tle_loader = loader
    _build.cache_clear()


def get_world(cfg: ScenarioConfig) -> World:
    """Shared, cached world for a scenario config (LinkModel is stateless, so sharing is safe)."""
    return _build(json.dumps(cfg.model_dump(), sort_keys=True))


def world_for_params(params: dict) -> World:
    """World for a run's params: its scenario snapshot (the default if absent)
    plus any run-level link parameter overrides."""
    snapshot = params.get("scenario")
    cfg = ScenarioConfig.model_validate(snapshot["config"]) if snapshot else ScenarioConfig()
    world = get_world(cfg)
    overrides = params.get("link_params")
    if overrides:
        return World(with_overrides(world.model, overrides), world.flow_demand_gbps, cfg)
    return world