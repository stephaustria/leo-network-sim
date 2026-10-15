import math
from dataclasses import replace
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from .constants import MU_EARTH, R_EARTH
from .constellation import Constellation, WalkerConfig
from .frames import datetime_to_jd
from .ground import DEFAULT_STATIONS, GroundStation
from .links import LinkModel, LinkParams, validate_link_overrides
from .routing import DEFAULT_FLOW_GBPS
from .tle import TleShell, parse_tle_text

MAX_SATELLITES = 1600
MAX_EXTRA_SHELLS = 3
MAX_TLE_SHELLS = 3
DEFAULT_SCENARIO_NAME = "Default (Starlink-like shell)"


class ConstellationConfig(BaseModel):
    altitude_km: float = Field(550.0, ge=300, le=2000)
    inclination_deg: float = Field(53.0, ge=0, le=100)
    planes: int = Field(24, ge=3, le=72)
    sats_per_plane: int = Field(22, ge=3, le=72)
    phasing: int = Field(1, ge=0, le=71)          # Walker "F"; must be < planes


class TleShellConfig(BaseModel):
    tle_set_id: int = Field(ge=1)
    limit: int | None = Field(None, ge=1, le=MAX_SATELLITES)       # keep only the first N satellites
    name_contains: str | None = Field(None, max_length=40)          # keep satellites whose name matches


class StationConfig(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def _default_stations() -> list[StationConfig]:
    return [StationConfig(name=s.name, lat=s.lat, lon=s.lon) for s in DEFAULT_STATIONS]


def _parse_epoch(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ScenarioConfig(BaseModel):
    constellation: ConstellationConfig | None = Field(default_factory=ConstellationConfig)   # Walker shell 1
    extra_shells: list[ConstellationConfig] = Field(default_factory=list, max_length=MAX_EXTRA_SHELLS)
    tle_shells: list[TleShellConfig] = Field(default_factory=list, max_length=MAX_TLE_SHELLS)
    epoch: str | None = None                      # ISO 8601; time 0 of the simulation (needed for real orbits)
    stations: list[StationConfig] = Field(default_factory=_default_stations, min_length=2, max_length=20)
    link_params: dict[str, float] = Field(default_factory=dict)
    flow_demand_gbps: float = Field(DEFAULT_FLOW_GBPS, gt=0, le=10)

    @field_validator("epoch")
    @classmethod
    def normalize_epoch(cls, value):
        if value is None:
            return None
        try:
            dt = _parse_epoch(value)
        except ValueError as exc:
            raise ValueError("epoch must be an ISO 8601 date-time such as 2026-10-13T00:00:00Z") from exc
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def shells(self) -> list[ConstellationConfig]:
        """Walker shells only (null `constellation` means none)."""
        return ([self.constellation] if self.constellation else []) + list(self.extra_shells)

    def total_sats(self) -> int:
        """Walker satellites. TLE satellites are only counted once the world is built."""
        return sum(s.planes * s.sats_per_plane for s in self.shells())

    @model_validator(mode="after")
    def check_scenario(self):
        if not self.shells() and not self.tle_shells:
            raise ValueError("a scenario needs a Walker constellation or at least one TLE shell")
        for i, s in enumerate(self.shells(), start=1):
            if s.phasing >= s.planes:
                raise ValueError(f"shell {i}: phasing must be smaller than the number of planes")
        if self.total_sats() > MAX_SATELLITES:
            raise ValueError(
                f"at most {MAX_SATELLITES} satellites in total (this scenario has {self.total_sats()})")
        names = [s.name.strip().lower() for s in self.stations]
        if len(set(names)) != len(names):
            raise ValueError("station names must be unique")
        self.link_params = validate_link_overrides(self.link_params)
        return self


def build_world(cfg: ScenarioConfig, load_tle=None) -> LinkModel:
    """Turn a validated scenario into a ready-to-simulate LinkModel.
    `load_tle(set_id) -> text` supplies TLE data; ValueError is raised for missing sets,
    empty filters, or too many satellites."""
    items: list = [WalkerConfig(**s.model_dump()) for s in cfg.shells()]
    for ts in cfg.tle_shells:
        if load_tle is None:
            raise ValueError("this scenario uses TLE data but no TLE source is configured")
        records = parse_tle_text(load_tle(ts.tle_set_id))
        if ts.name_contains:
            needle = ts.name_contains.lower()
            records = [r for r in records if needle in r.name.lower()]
        if ts.limit:
            records = records[: ts.limit]
        if not records:
            raise ValueError(f"TLE set {ts.tle_set_id}: no satellites match the filters")
        items.append(TleShell(records, name=f"TLE set {ts.tle_set_id}"))

    epoch_jd = datetime_to_jd(_parse_epoch(cfg.epoch)) if cfg.epoch else None
    constellation = Constellation(items, epoch_jd=epoch_jd)
    if constellation.n_sats > MAX_SATELLITES:
        raise ValueError(f"at most {MAX_SATELLITES} satellites in total (this scenario has {constellation.n_sats})")

    stations = [GroundStation(s.name.strip(), s.lat, s.lon) for s in cfg.stations]
    return LinkModel(constellation, stations, replace(LinkParams(), **cfg.link_params))


def _footprint(altitude_km: float, params: LinkParams) -> float:
    r = R_EARTH + altitude_km * 1000.0
    el = math.radians(params.min_elevation_deg)
    return math.pi / 2 - el - math.asin(R_EARTH * math.cos(el) / r)       # footprint half-angle


def _describe_shell(s: ConstellationConfig, params: LinkParams) -> dict:
    r = R_EARTH + s.altitude_km * 1000.0
    n = s.planes * s.sats_per_plane
    lam = _footprint(s.altitude_km, params)
    spacing_km = 2 * r * math.sin(math.pi / s.sats_per_plane) / 1000
    return {
        "kind": "walker",
        "n_sats": n,
        "altitude_km": s.altitude_km,
        "inclination_deg": s.inclination_deg,
        "period_min": round(2 * math.pi * math.sqrt(r**3 / MU_EARTH) / 60, 2),
        "orbital_speed_kms": round(math.sqrt(MU_EARTH / r) / 1000, 2),
        "intra_plane_spacing_km": round(spacing_km),
        "intra_plane_links_in_range": spacing_km <= params.max_isl_range_km,
        "footprint_radius_km": round(R_EARTH * lam / 1000),
        # uniform-coverage estimate; the real value varies with latitude (see the coverage heatmaps)
        "mean_sats_in_view_estimate": round(n * (1 - math.cos(lam)) / 2, 3),
    }


def _describe_tle_shell(shell, params: LinkParams) -> dict:
    s = shell.summary()
    r = R_EARTH + s["altitude_km"] * 1000.0
    lam = _footprint(s["altitude_km"], params)
    return {
        **s,
        "orbital_speed_kms": round(math.sqrt(MU_EARTH / r) / 1000, 2),
        "intra_plane_spacing_km": None,
        "intra_plane_links_in_range": True,
        "footprint_radius_km": round(R_EARTH * lam / 1000),
        "mean_sats_in_view_estimate": round(s["n_sats"] * (1 - math.cos(lam)) / 2, 3),
    }


def describe(cfg: ScenarioConfig, world=None) -> dict:
    """Quick analytic facts about a scenario. Top-level orbit fields describe the first shell,
    `shells` has one entry per shell (pass the built `world` to include TLE shells)."""
    params = replace(LinkParams(), **cfg.link_params)
    per_shell = [_describe_shell(s, params) for s in cfg.shells()]
    if world is not None:
        per_shell += [_describe_tle_shell(sh, params) for sh in world.model.c.shells if sh.kind == "tle"]
    first = per_shell[0] if per_shell else {}
    k = len(cfg.stations)
    return {
        "n_sats": world.model.c.n_sats if world is not None else cfg.total_sats(),
        "epoch": cfg.epoch,
        "period_min": first.get("period_min"),
        "orbital_speed_kms": first.get("orbital_speed_kms"),
        "intra_plane_spacing_km": first.get("intra_plane_spacing_km"),
        "max_isl_range_km": params.max_isl_range_km,
        "intra_plane_links_in_range": all(p.get("intra_plane_links_in_range", True) for p in per_shell),
        "footprint_radius_km": first.get("footprint_radius_km"),
        "mean_sats_in_view_estimate": round(sum(p["mean_sats_in_view_estimate"] for p in per_shell), 2),
        "n_stations": k,
        "n_flows": k * (k - 1) // 2,
        "shells": per_shell,
    }