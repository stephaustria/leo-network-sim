import time
import warnings
from dataclasses import dataclass

import numpy as np

from .constants import C_LIGHT, R_EARTH

CHUNK = 2000        # grid points processed at once (bounds memory)
MAX_WORK = 2.5e9    # cells x satellites x samples; keeps one request to roughly 20 s


@dataclass(frozen=True)
class CoverageParams:
    res_deg: float = 5.0
    window_hours: float = 12.0
    step_s: float = 180.0

    @property
    def samples(self) -> int:
        return max(1, int(self.window_hours * 3600 // self.step_s))


@dataclass
class PointCoverage:
    availability: np.ndarray
    mean_visible: np.ndarray
    mean_latency_ms: np.ndarray
    p95_latency_ms: np.ndarray
    longest_gap_s: np.ndarray


def valid_resolution(res_deg: float) -> bool:
    """The grid must tile the globe exactly: 180 / res must be a whole number."""
    return 1 <= res_deg <= 30 and abs(180 / res_deg - round(180 / res_deg)) < 1e-9


def grid_dims(res_deg: float) -> tuple[int, int]:
    return round(180 / res_deg), round(360 / res_deg)


def work_estimate(res_deg: float, n_sats: int, samples: int) -> float:
    n_lat, n_lon = grid_dims(res_deg)
    return float(n_lat * n_lon * n_sats * samples)


def grid_points(res_deg: float):
    """Cell centers: (lat_centers, lon_centers, flat lat, flat lon), latitude-major order."""
    n_lat, n_lon = grid_dims(res_deg)
    lat_c = -90 + res_deg * (np.arange(n_lat) + 0.5)
    lon_c = -180 + res_deg * (np.arange(n_lon) + 0.5)
    lat, lon = np.meshgrid(lat_c, lon_c, indexing="ij")
    return lat_c, lon_c, lat.ravel(), lon.ravel()

def _half_angle(R: float, r: float, el: float) -> float:
    """Earth-central half-angle of a satellite's footprint at minimum elevation `el`."""
    return np.pi / 2 - el - np.arcsin(R * np.cos(el) / r)


def coverage_at_points(model, lat_deg, lon_deg, step_s: float, samples: int) -> PointCoverage:
    c = model.c
    R = R_EARTH
    el = np.radians(model.params.min_elevation_deg)
    shells = [(s.offset, s.offset + s.n_sats, s.radius) for s in c.shells]
    cos_lams = [np.float32(np.cos(_half_angle(R, r, el))) for _, _, r in shells]

    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    unit = np.column_stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    unit = unit.astype(np.float32)
    P = len(unit)

    visible_sum = np.zeros(P)
    covered_count = np.zeros(P)
    run = np.zeros(P, dtype=np.int64)
    max_run = np.zeros(P, dtype=np.int64)
    latency = np.full((samples, P), np.nan, dtype=np.float32)

    for k in range(samples):
        sat_all = c.positions_ecef(k * step_s)
        n_vis = np.zeros(P, dtype=np.int64)
        nearest = np.full(P, np.inf)                       # slant range to the nearest visible satellite

        for (lo, hi, r), cos_lam in zip(shells, cos_lams):
            sat = (sat_all[lo:hi] / r).astype(np.float32)               # unit vectors, all radius r
            for s in range(0, P, CHUNK):
                dots = unit[s:s + CHUNK] @ sat.T                         # cos of central angle
                n_vis[s:s + CHUNK] += (dots >= cos_lam).sum(axis=1)
                best = dots.max(axis=1).astype(np.float64)
                d = np.sqrt(np.maximum(R * R + r * r - 2 * R * r * best, 0.0))
                d = np.where(best >= cos_lam, d, np.inf)                 # only if visible
                view = nearest[s:s + CHUNK]
                np.minimum(view, d, out=view)

        ok = n_vis > 0
        visible_sum += n_vis
        covered_count += ok
        run = np.where(ok, 0, run + 1)
        np.maximum(max_run, run, out=max_run)
        latency[k, ok] = (nearest[ok] / C_LIGHT * 1000.0).astype(np.float32)

    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_ms = np.nanmean(latency, axis=0)
        p95_ms = np.nanpercentile(latency, 95, axis=0)

    return PointCoverage(
        availability=covered_count / samples,
        mean_visible=visible_sum / samples,
        mean_latency_ms=mean_ms,
        p95_latency_ms=p95_ms,
        longest_gap_s=max_run * step_s,
    )


def _clean(arr, ndigits: int) -> list:
    return [round(float(x), ndigits) if np.isfinite(x) else None for x in arr]


def _r(x, n: int):
    return None if x is None else round(x, n)


def _row_mean(x: np.ndarray, n_lat: int, n_lon: int) -> np.ndarray:
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(x.reshape(n_lat, n_lon), axis=1)


def compute_coverage(model, p: CoverageParams) -> dict:
    """Heatmap-ready coverage statistics for a world, plus per-latitude and per-station rows."""
    started = time.perf_counter()
    lat_c, lon_c, lat, lon = grid_points(p.res_deg)
    n_lat, n_lon, G = len(lat_c), len(lon_c), len(lat)
    stations = model.stations

    cov = coverage_at_points(
        model,
        np.concatenate([lat, [s.lat for s in stations]]),
        np.concatenate([lon, [s.lon for s in stations]]),
        p.step_s, p.samples,
    )
    avail, vis = cov.availability[:G], cov.mean_visible[:G]
    mean_ms, p95_ms, gap = cov.mean_latency_ms[:G], cov.p95_latency_ms[:G], cov.longest_gap_s[:G]

    w = np.cos(np.radians(lat))
    w = w / w.sum()                                              # area weights

    def wmean(x):
        ok = np.isfinite(x)
        return float((x[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() else None

    summary = {
        "global_availability": _r(wmean(avail), 4),
        "global_mean_visible": _r(wmean(vis), 2),
        "mean_access_latency_ms": _r(wmean(mean_ms), 2),
        "area_pct_with_any_coverage": round(float(w[avail > 0].sum() * 100), 1),
        "area_pct_availability_ge_99": round(float(w[avail >= 0.99].sum() * 100), 1),
        "worst_gap_min": round(float(gap.max() / 60), 1),
    }

    row_avail = avail.reshape(n_lat, n_lon).mean(axis=1)
    row_vis = vis.reshape(n_lat, n_lon).mean(axis=1)
    row_ms = _row_mean(mean_ms, n_lat, n_lon)
    by_latitude = [
        {"lat": float(lat_c[i]), "availability": round(float(row_avail[i]), 3),
         "mean_visible": round(float(row_vis[i]), 2),
         "mean_latency_ms": round(float(row_ms[i]), 2) if np.isfinite(row_ms[i]) else None}
        for i in range(n_lat)
    ]

    station_rows = []
    for i, s in enumerate(stations):
        j = G + i
        station_rows.append({
            "name": s.name, "lat": s.lat, "lon": s.lon,
            "availability": round(float(cov.availability[j]), 3),
            "mean_visible": round(float(cov.mean_visible[j]), 2),
            "mean_latency_ms": _clean([cov.mean_latency_ms[j]], 2)[0],
            "p95_latency_ms": _clean([cov.p95_latency_ms[j]], 2)[0],
            "longest_gap_min": round(float(cov.longest_gap_s[j] / 60), 1),
        })

    return {
        "grid": {"res_deg": p.res_deg, "lat0": float(lat_c[0]), "lon0": float(lon_c[0]),
                 "n_lat": n_lat, "n_lon": n_lon},
        "params": {"res_deg": p.res_deg, "window_hours": p.window_hours, "step_s": p.step_s,
                   "samples": p.samples, "min_elevation_deg": model.params.min_elevation_deg,
                   "n_sats": model.c.n_sats},
        "summary": summary,
        "availability": _clean(avail, 3),
        "mean_visible": _clean(vis, 2),
        "mean_latency_ms": _clean(mean_ms, 2),
        "p95_latency_ms": _clean(p95_ms, 2),
        "longest_gap_min": _clean(gap / 60, 1),
        "by_latitude": by_latitude,
        "stations": station_rows,
        "elapsed_s": round(time.perf_counter() - started, 2),
    }