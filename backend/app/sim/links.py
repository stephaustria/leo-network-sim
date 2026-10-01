from dataclasses import dataclass

import numpy as np

from .constants import C_LIGHT, R_EARTH
from .constellation import Constellation
from .ground import DEFAULT_STATIONS, stations_ecef


@dataclass(frozen=True)
class LinkParams:
    min_elevation_deg: float = 25.0
    max_isl_range_km: float = 5000.0
    grazing_margin_km: float = 80.0
    cross_plane_max_abs_lat_deg: float | None = None  # e.g. 50 to drop cross-plane links near orbit apex
    node_processing_ms: float = 0.5
    isl_capacity_gbps: float = 10.0
    isl_loss: float = 1e-5
    ground_capacity_gbps: float = 2.0
    ground_min_capacity_frac: float = 0.4   # capacity fraction at the minimum elevation
    ground_base_loss: float = 1e-3
    ground_fade_loss: float = 0.03          # extra loss at the horizon


@dataclass
class IslLinks:
    a: np.ndarray
    b: np.ndarray
    cross_plane: np.ndarray
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


def clear_of_earth(p1: np.ndarray, p2: np.ndarray, margin_m: float) -> np.ndarray:
    """True where the segment p1-p2 stays above the Earth (plus margin)."""
    d = p2 - p1
    t = -np.einsum("ij,ij->i", p1, d) / np.einsum("ij,ij->i", d, d)
    closest = p1 + np.clip(t, 0.0, 1.0)[:, None] * d
    return np.linalg.norm(closest, axis=1) > (R_EARTH + margin_m)


def build_isl_topology(c: Constellation):
    """+Grid ISL pairs. Returns (pairs (M,2), is_cross_plane (M,))."""
    P, S, F = c.n_planes, c.per_plane, c.cfg.phasing
    links: dict[tuple[int, int], bool] = {}
    for p in range(P):
        for s in range(S):
            a = c.sat_index(p, s)
            b = c.sat_index(p, s + 1)                      # intra-plane
            if a != b:
                links[(min(a, b), max(a, b))] = False
            shift = F if p == P - 1 else 0                 # Walker wrap-around alignment
            b = c.sat_index(p + 1, s + shift)              # cross-plane
            if a != b:
                links.setdefault((min(a, b), max(a, b)), True)
    keys = sorted(links)
    return np.array(keys), np.array([links[k] for k in keys])


class LinkModel:
    def __init__(self, constellation: Constellation, stations=DEFAULT_STATIONS,
                 params: LinkParams = LinkParams()):
        self.c = constellation
        self.stations = stations
        self.params = params
        self.gs_ecef = stations_ecef(stations)
        self.pairs, self.is_cross = build_isl_topology(constellation)

    def snapshot(self, t: float) -> LinkSnapshot:
        p = self.params
        sat = self.c.positions_ecef(t)
        return LinkSnapshot(
            t=t,
            n_isl_candidates=len(self.pairs),
            isl=self._isl(sat),
            ground=self._ground(sat),
        )

    def _isl(self, sat: np.ndarray) -> IslLinks:
        p = self.params
        a, b = self.pairs[:, 0], self.pairs[:, 1]
        pa, pb = sat[a], sat[b]
        dist = np.linalg.norm(pb - pa, axis=1)

        ok = (dist <= p.max_isl_range_km * 1000) & clear_of_earth(pa, pb, p.grazing_margin_km * 1000)
        if p.cross_plane_max_abs_lat_deg is not None:
            lat_a = np.degrees(np.arcsin(pa[:, 2] / np.linalg.norm(pa, axis=1)))
            ok &= ~(self.is_cross & (np.abs(lat_a) > p.cross_plane_max_abs_lat_deg))

        dist = dist[ok]
        return IslLinks(
            a=a[ok], b=b[ok],
            cross_plane=self.is_cross[ok],
            distance_km=dist / 1000,
            latency_ms=dist / C_LIGHT * 1000 + p.node_processing_ms,
            capacity_gbps=np.full(dist.shape, p.isl_capacity_gbps),
            loss=np.full(dist.shape, p.isl_loss),
        )

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