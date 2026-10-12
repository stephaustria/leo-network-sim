import pytest

from app.sim.constellation import Constellation
from app.sim.coverage import (CoverageParams, compute_coverage, grid_points, valid_resolution,
                              work_estimate)
from app.sim.links import LinkModel
from app.sim.scenario import ScenarioConfig, build_world, describe

MODEL = LinkModel(Constellation())
FAST = CoverageParams(res_deg=6.0, window_hours=2.0, step_s=180.0)     # 30 x 60 grid, 40 samples


@pytest.fixture(scope="module")
def cov():
    return compute_coverage(MODEL, FAST)


def row(c, key, lat):
    g = c["grid"]
    i = round((lat - g["lat0"]) / g["res_deg"])
    return c[key][i * g["n_lon"]:(i + 1) * g["n_lon"]]


def test_grid_and_budget_helpers():
    lat_c, lon_c, lat, lon = grid_points(10)
    assert lat_c[0] == -85 and lat_c[-1] == 85 and len(lon_c) == 36 and len(lat) == 648
    assert all(valid_resolution(x) for x in (1, 2, 2.5, 5, 30))
    assert not any(valid_resolution(x) for x in (7, 0.5, 40))
    assert work_estimate(10, 528, 24) == 648 * 528 * 24


def test_shape(cov):
    assert cov["grid"]["n_lat"] == 30 and cov["grid"]["n_lon"] == 60
    assert len(cov["availability"]) == 1800
    assert len(cov["by_latitude"]) == 30 and len(cov["stations"]) == 6


def test_polar_cells_uncovered_and_midlatitudes_well_covered(cov):
    assert max(row(cov, "availability", 87)) == 0.0                  # shell reaches ~62 deg at most
    mid = row(cov, "availability", 45)
    assert sum(mid) / len(mid) > 0.9
    assert all(v is None for v in row(cov, "mean_latency_ms", 87))   # no coverage, no latency


def test_access_latency_is_within_physical_bounds(cov):
    values = [v for v in cov["mean_latency_ms"] if v is not None]
    assert values and min(values) >= 1.8 and max(values) <= 3.9      # 550 km zenith .. 25 deg edge


def test_longest_gap(cov):
    window_min = FAST.samples * FAST.step_s / 60
    assert max(row(cov, "longest_gap_min", 87)) == pytest.approx(window_min, abs=0.1)
    assert max(row(cov, "longest_gap_min", 45)) < window_min


def test_global_mean_visible_matches_the_analytic_estimate(cov):
    estimate = describe(ScenarioConfig())["mean_sats_in_view_estimate"]
    assert abs(cov["summary"]["global_mean_visible"] - estimate) < 0.4


def test_station_rows(cov):
    sf = cov["stations"][0]
    assert sf["name"] == "San Francisco"
    assert sf["availability"] > 0.9 and 1.8 <= sf["mean_latency_ms"] <= 3.9


def test_sparser_constellation_has_lower_availability(cov):
    small = build_world(ScenarioConfig(
        constellation={"planes": 6, "sats_per_plane": 8, "altitude_km": 800}))
    sparse = compute_coverage(small, FAST)
    assert sparse["summary"]["global_availability"] < cov["summary"]["global_availability"]


def test_polar_shell_covers_the_poles():
    polar = build_world(ScenarioConfig(constellation={
        "planes": 12, "sats_per_plane": 12, "altitude_km": 1000, "inclination_deg": 87}))
    c = compute_coverage(polar, FAST)
    assert max(row(c, "availability", 87)) > 0.5