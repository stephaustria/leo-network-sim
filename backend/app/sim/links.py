from dataclasses import dataclass, replace


import numpy as np
import math
import threading

from .constants import C_LIGHT
from .constellation import Constellation
from .ground import DEFAULT_STATIONS, stations_ecef
from .isl import clear_of_earth, inter_shell_links, nearest_links     # clear_of_earth is re-exported

# ISL kinds: codes stored in IslLinks.kind, names used on graph edges
KIND_INTRA, KIND_CROSS, KIND_NEAR, KIND_SHELL = 0, 1, 2, 3
ISL_KIND_NAMES = ("isl_intra", "isl_cross", "isl_near", "isl_shell")
ISL_MODES = ("auto", "grid", "nearest", "none")


@dataclass(frozen=True)
class LinkParams:
    min_elevation_deg: float = 25.0
    max_isl_range_km: float = 5000.0
    grazing_margin_km: float = 80.0
    cross_plane_max_abs_lat_deg: float | None = None  # e.g. 50 to drop grid cross-plane links near the orbit apex
    node_processing_ms: float = 0.5
    isl_capacity_gbps: float = 10.0
    isl_loss: float = 1e-5
    ground_capacity_gbps: float = 2.0
    ground_min_capacity_frac: float = 0.4   # capacity fraction at the minimum elevation
    ground_base_loss: float = 1e-3
    ground_fade_loss: float = 0.03          # extra loss at the horizon


@dataclass(frozen=True)
class IslPolicy:
    """How inter-satellite links are chosen.
    auto: +Grid inside Walker shells, nearest-neighbour for TLE shells.
    grid: +Grid inside Walker shells only (TLE shells get none).
    nearest: nearest-neighbour links in every shell.
    none: no ISLs at all (stations can only use a satellite they both see).

    Nearest-neighbour links are planned at the start of every `replan_s` interval and held
    for as long as they stay valid (0 = re-plan every tick)."""
    mode: str = "auto"
    max_degree: int = 4               # links per satellite inside a shell (nearest mode)
    inter_shell_degree: int = 0       # extra links per satellite to other Walker shells
    replan_s: float = 300.0

    def __post_init__(self):
        if self.mode not in ISL_MODES:
            raise ValueError(f"isl mode must be one of {ISL_MODES}, got {self.mode!r}")
        if self.max_degree < 1 or self.inter_shell_degree < 0 or self.replan_s < 0:
            raise ValueError("max_degree must be >= 1; inter_shell_degree and replan_s must be >= 0")


@dataclass
class IslLinks:
    a: np.ndarray
    b: np.ndarray
    kind: np.ndarray            # KIND_* codes
    distance_km: np.ndarray
    latency_ms: np.ndarray
    capacity_gbps: np.ndarray
    loss: np.ndarray


@dataclass
class GroundLinks:
    station: np.ndarray
    sat: np.ndarray
    elevation_deg: np.ndarray
    range_km: np.ndarray
    latency_ms: np.ndarray
    capacity_gbps: np.ndarray
    loss: np.ndarray


@dataclass
class LinkSnapshot:
    t: float
    n_isl_candidates: int
    isl: IslLinks
    ground: GroundLinks


def elevation_and_range(gs_ecef: np.ndarray, sat_ecef: np.ndarray):
    """Elevation (deg) and slant range (m), both shaped (G, N)."""
    vec = sat_ecef[None, :, :] - gs_ecef[:, None, :]
    rng = np.linalg.norm(vec, axis=2)
    up = gs_ecef / np.linalg.norm(gs_ecef, axis=1, keepdims=True)
    sin_el = np.einsum("gnk,gk->gn", vec, up) / rng
    return np.degrees(np.arcsin(np.clip(sin_el, -1.0, 1.0))), rng


def shell_modes(c: Constellation, mode: str) -> list[str]:
    """Per shell: 'grid' (+Grid inside a Walker shell), 'nearest' (dynamic) or 'none'."""
    out = []
    for shell in c.shells:
        if mode == "none":
            out.append("none")
        elif mode == "auto":
            out.append("grid" if shell.kind == "walker" else "nearest")
        elif mode == "grid":
            out.append("grid" if shell.kind == "walker" else "none")
        else:
            out.append("nearest")
    return out


def build_isl_topology(c: Constellation, modes: list[str] | None = None):
    """Static +Grid ISL pairs inside every Walker shell whose mode is 'grid'.
    Returns (pairs (M,2) global indices, is_cross_plane (M,))."""
    modes = modes if modes is not None else shell_modes(c, "auto")
    links: dict[tuple[int, int], bool] = {}
    for shell, mode in zip(c.shells, modes):
        if shell.kind != "walker" or mode != "grid":
            continue
        P, S, F = shell.n_planes, shell.per_plane, shell.cfg.phasing
        for p in range(P):
            for s in range(S):
                a = shell.offset + shell.sat_index(p, s)
                b = shell.offset + shell.sat_index(p, s + 1)                # intra-plane
                if a != b:
                    links[(min(a, b), max(a, b))] = False
                shift = F if p == P - 1 else 0                              # Walker wrap-around alignment
                b = shell.offset + shell.sat_index(p + 1, s + shift)        # cross-plane
                if a != b:
                    links.setdefault((min(a, b), max(a, b)), True)
    keys = sorted(links)
    pairs = np.array(keys, dtype=np.int64).reshape(-1, 2)
    return pairs, np.array([links[k] for k in keys], dtype=bool)


class LinkModel:
    def __init__(self, constellation: Constellation, stations=DEFAULT_STATIONS,
                 params: LinkParams = LinkParams(), isl: IslPolicy = IslPolicy()):
        self.c = constellation
        self.stations = stations
        self.params = params
        self.isl = isl
        self.gs_ecef = stations_ecef(stations)

        self.shell_modes = shell_modes(constellation, isl.mode)
        self.pairs, self.is_cross = build_isl_topology(constellation, self.shell_modes)   # static grid links
        self.dynamic_shells = [s for s, m in zip(constellation.shells, self.shell_modes) if m == "nearest"]
        walkers = [s for s in constellation.shells if s.kind == "walker"]
        self.inter_pairs = (
            [(a, b) for i, a in enumerate(walkers) for b in walkers[i + 1:]]
            if isl.inter_shell_degree > 0 and isl.mode != "none" else []
        )
        self.isl_dynamic = bool(self.dynamic_shells or self.inter_pairs)    # topology changes over time
        self._plans: dict[float, tuple] = {}
        self._plan_lock = threading.Lock()

    def snapshot(self, t: float) -> LinkSnapshot:
        sat = self.c.positions_ecef(t)
        isl, n_candidates = self._isl(sat, t)
        return LinkSnapshot(t=t, n_isl_candidates=n_candidates, isl=isl, ground=self._ground(sat))

    def _plan(self, t: float, sat: np.ndarray):
        """Planned nearest-neighbour and inter-shell links for the replan interval containing t:
        (a, b, kind) arrays. A pure function of t (cached), so live runs and replays agree."""
        rs = self.isl.replan_s
        t_plan = t if rs <= 0 else math.floor(t / rs) * rs
        key = round(t_plan, 3)
        with self._plan_lock:
            plan = self._plans.get(key)
        if plan is not None:
            return plan

        sat_plan = sat if t_plan == t else self.c.positions_ecef(t_plan)
        p = self.params
        range_m, margin_m = p.max_isl_range_km * 1000.0, p.grazing_margin_km * 1000.0
        a_parts, b_parts, k_parts = [], [], []

        for shell in self.dynamic_shells:
            lo, hi = shell.offset, shell.offset + shell.n_sats
            a, b = nearest_links(sat_plan[lo:hi], self.isl.max_degree, range_m, margin_m)
            a_parts.append(a + lo)
            b_parts.append(b + lo)
            k_parts.append(np.full(len(a), KIND_NEAR))

        for sa, sb in self.inter_pairs:
            a, b = inter_shell_links(
                sat_plan[sa.offset:sa.offset + sa.n_sats], sat_plan[sb.offset:sb.offset + sb.n_sats],
                self.isl.inter_shell_degree, range_m, margin_m)
            a_parts.append(a + sa.offset)
            b_parts.append(b + sb.offset)
            k_parts.append(np.full(len(a), KIND_SHELL))

        plan = (np.concatenate(a_parts), np.concatenate(b_parts), np.concatenate(k_parts))
        with self._plan_lock:
            self._plans[key] = plan
            while len(self._plans) > 8:
                self._plans.pop(next(iter(self._plans)))
        return plan

    def _isl(self, sat: np.ndarray, t: float):
        p = self.params
        a, b = self.pairs[:, 0], self.pairs[:, 1]
        kind = np.where(self.is_cross, KIND_CROSS, KIND_INTRA)
        if self.isl_dynamic:
            da, db, dk = self._plan(t, sat)
            a, b, kind = np.concatenate([a, da]), np.concatenate([b, db]), np.concatenate([kind, dk])
        kind = kind.astype(np.int8)
        n_candidates = len(a)

        # planned links are checked against the CURRENT geometry: a link that has gone out of
        # range or behind the Earth since the plan was made is dropped
        pa, pb = sat[a], sat[b]
        dist = np.linalg.norm(pb - pa, axis=1)
        ok = (dist <= p.max_isl_range_km * 1000) & clear_of_earth(pa, pb, p.grazing_margin_km * 1000)
        if p.cross_plane_max_abs_lat_deg is not None:
            lat_a = np.degrees(np.arcsin(pa[:, 2] / np.linalg.norm(pa, axis=1)))
            ok &= ~((kind == KIND_CROSS) & (np.abs(lat_a) > p.cross_plane_max_abs_lat_deg))

        dist = dist[ok]
        links = IslLinks(
            a=a[ok], b=b[ok], kind=kind[ok],
            distance_km=dist / 1000,
            latency_ms=dist / C_LIGHT * 1000 + p.node_processing_ms,
            capacity_gbps=np.full(dist.shape, p.isl_capacity_gbps),
            loss=np.full(dist.shape, p.isl_loss),
        )
        return links, n_candidates

    def _ground(self, sat: np.ndarray) -> GroundLinks:
        p = self.params
        elev, rng = elevation_and_range(self.gs_ecef, sat)
        g, s = np.nonzero(elev >= p.min_elevation_deg)
        el, r = elev[g, s], rng[g, s]

        sin_el = np.sin(np.radians(el))
        sin_min = np.sin(np.radians(p.min_elevation_deg))
        frac = p.ground_min_capacity_frac + (1 - p.ground_min_capacity_frac) * (
            (sin_el - sin_min) / (1 - sin_min)
        )
        return GroundLinks(
            station=g, sat=s,
            elevation_deg=el,
            range_km=r / 1000,
            latency_ms=r / C_LIGHT * 1000 + p.node_processing_ms,
            capacity_gbps=p.ground_capacity_gbps * frac,
            loss=p.ground_base_loss + p.ground_fade_loss * (1 - sin_el) ** 2,
        )


# Link parameters an experiment is allowed to override, with (min, max) bounds.
TUNABLE_LINK_PARAMS = {
    "ground_capacity_gbps": (0.1, 10_000.0),
    "isl_capacity_gbps": (0.1, 10_000.0),
    "min_elevation_deg": (5.0, 60.0),
    "max_isl_range_km": (500.0, 20_000.0),
}


def validate_link_overrides(overrides: dict | None) -> dict:
    out = {}
    for key, value in (overrides or {}).items():
        if key not in TUNABLE_LINK_PARAMS:
            raise ValueError(f"link_params: unknown key {key!r}; allowed: {sorted(TUNABLE_LINK_PARAMS)}")
        lo, hi = TUNABLE_LINK_PARAMS[key]
        value = float(value)
        if not lo <= value <= hi:
            raise ValueError(f"link_params: {key} must be between {lo} and {hi}")
        out[key] = value
    return out


def with_overrides(base: LinkModel, overrides: dict | None) -> LinkModel:
    """A LinkModel sharing the constellation but with some link parameters changed."""
    if not overrides:
        return base
    return LinkModel(base.c, base.stations,
                     replace(base.params, **validate_link_overrides(overrides)), base.isl)