import math
from dataclasses import replace

from pydantic import BaseModel, Field, model_validator

from .constants import MU_EARTH, R_EARTH
from .constellation import Constellation, WalkerConfig
from .ground import DEFAULT_STATIONS, GroundStation
from .links import LinkModel, LinkParams, validate_link_overrides
from .routing import DEFAULT_FLOW_GBPS

MAX_SATELLITES = 1600


class ConstellationConfig(BaseModel):
    altitude_km: float = Field(550.0, ge=300, le=2000)
    inclination_deg: float = Field(53.0, ge=0, le=100)
    planes: int = Field(24, ge=3, le=72)
    sats_per_plane: int = Field(22, ge=3, le=72)
    phasing: int = Field(1, ge=0, le=71)          # Walker "F"; must be < planes


class StationConfig(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def _default_stations() -> list[StationConfig]:
    return [StationConfig(name=s.name, lat=s.lat, lon=s.lon) for s in DEFAULT_STATIONS]


class ScenarioConfig(BaseModel):
    constellation: ConstellationConfig = Field(default_factory=ConstellationConfig)
    stations: list[StationConfig] = Field(default_factory=_default_stations, min_length=2, max_length=20)
    link_params: dict[str, float] = Field(default_factory=dict)
    flow_demand_gbps: float = Field(DEFAULT_FLOW_GBPS, gt=0, le=10)

    @model_validator(mode="after")
    def check_scenario(self):
        c = self.constellation
        if c.planes * c.sats_per_plane > MAX_SATELLITES:
            raise ValueError(
                f"at most {MAX_SATELLITES} satellites ({c.planes} x {c.sats_per_plane} is too many)")
        if c.phasing >= c.planes:
            raise ValueError("phasing must be smaller than the number of planes")
        names = [s.name.strip().lower() for s in self.stations]
        if len(set(names)) != len(names):
            raise ValueError("station names must be unique")
        self.link_params = validate_link_overrides(self.link_params)
        return self


def build_world(cfg: ScenarioConfig) -> LinkModel:
    """Turn a validated scenario into a ready-to-simulate LinkModel."""
    constellation = Constellation(WalkerConfig(**cfg.constellation.model_dump()))
    stations = [GroundStation(s.name.strip(), s.lat, s.lon) for s in cfg.stations]
    return LinkModel(constellation, stations, replace(LinkParams(), **cfg.link_params))


def describe(cfg: ScenarioConfig) -> dict:
    """Quick analytic facts about a scenario, cheap enough to show live in an editor."""
    c = cfg.constellation
    params = replace(LinkParams(), **cfg.link_params)
    r = R_EARTH + c.altitude_km * 1000.0
    n = c.planes * c.sats_per_plane
    el = math.radians(params.min_elevation_deg)
    lam = math.pi / 2 - el - math.asin(R_EARTH * math.cos(el) / r)   # footprint half-angle
    k = len(cfg.stations)
    return {
        "n_sats": n,
        "period_min": round(2 * math.pi * math.sqrt(r**3 / MU_EARTH) / 60, 2),
        "orbital_speed_kms": round(math.sqrt(MU_EARTH / r) / 1000, 2),
        "intra_plane_spacing_km": round(2 * r * math.sin(math.pi / c.sats_per_plane) / 1000),
        "footprint_radius_km": round(R_EARTH * lam / 1000),
        # uniform-coverage estimate; the real value varies with latitude (see the B3 heatmaps)
        "mean_sats_in_view_estimate": round(n * (1 - math.cos(lam)) / 2, 2),
        "n_stations": k,
        "n_flows": k * (k - 1) // 2,
    }