import numpy as np
import pytest
from pydantic import ValidationError

from app.sim.constellation import Constellation, WalkerConfig
from app.sim.coverage import CoverageParams, compute_coverage
from app.sim.engine import Simulation
from app.sim.failures import FailureSchedule
from app.sim.links import build_isl_topology
from app.sim.presets import seam_cut
from app.sim.scenario import ScenarioConfig, build_world, describe

LOW = WalkerConfig(altitude_km=550, inclination_deg=53, planes=6, sats_per_plane=8, phasing=1)
HIGH = WalkerConfig(altitude_km=1100, inclination_deg=70, planes=4, sats_per_plane=6, phasing=1)
TWO = Constellation([LOW, HIGH])

SCEN = {
    "constellation": {"planes": 6, "sats_per_plane": 8, "altitude_km": 550},
    "extra_shells": [{"planes": 4, "sats_per_plane": 6, "altitude_km": 1100, "inclination_deg": 70}],
}


def test_two_shell_layout():
    assert TWO.n_sats == 72 and TWO.n_planes == 10 and len(TWO.shells) == 2
    assert [s.offset for s in TWO.shells] == [0, 48]
    assert (TWO.shell_of[:48] == 0).all() and (TWO.shell_of[48:] == 1).all()
    assert sorted(set(TWO.plane[48:])) == [6, 7, 8, 9]
    assert len(TWO.sats_in_plane(7)) == 6 and (TWO.shell_of[TWO.sats_in_plane(7)] == 1).all()
    assert TWO.next_plane(5) == 0 and TWO.next_plane(9) == 6 and TWO.next_plane(6) == 7


def test_each_shell_keeps_its_own_radius():
    pos = TWO.positions_eci(1234.0)
    assert pos.shape == (72, 3)
    r = np.linalg.norm(pos, axis=1)
    assert np.allclose(r[:48], TWO.shells[0].radius) and np.allclose(r[48:], TWO.shells[1].radius)
    assert TWO.shells[1].period_s > TWO.shells[0].period_s


def test_single_shell_api_is_unchanged():
    c = Constellation()
    assert c.n_sats == 528 and c.n_planes == 24 and c.per_plane == 22 and c.cfg.phasing == 1
    assert c.sat_index(0, 22) == 0 and c.sat_index(24, 0) == 0
    assert c.radius == c.shells[0].radius


def test_isl_topology_stays_inside_each_shell():
    pairs, _ = build_isl_topology(TWO)
    assert len(pairs) == 2 * 72
    assert (TWO.shell_of[pairs[:, 0]] == TWO.shell_of[pairs[:, 1]]).all()
    assert (np.bincount(pairs.ravel(), minlength=72) == 4).all()


def test_plane_failures_use_global_plane_ids():
    s = FailureSchedule.from_dicts([{"kind": "plane", "target": 7}], TWO, 6)
    assert s.active_at(0, TWO).sats == {int(i) for i in TWO.sats_in_plane(7)}
    with pytest.raises(ValueError):
        FailureSchedule.from_dicts([{"kind": "plane", "target": 10}], TWO, 6)


def test_seam_cut_stays_inside_a_shell():
    pairs, _ = build_isl_topology(TWO)
    assert len(seam_cut(TWO, pairs, 5, 0.0)) == 8      # last plane of shell 1 <-> its first (wrap)
    assert len(seam_cut(TWO, pairs, 6, 0.0)) == 6      # planes 6-7 of the second shell
    assert len(seam_cut(TWO, pairs, 3, 0.0)) == 8      # planes 3-4 of the first shell


def test_scenario_with_an_extra_shell():
    cfg = ScenarioConfig(**SCEN)
    model = build_world(cfg)
    assert model.c.n_sats == 72 and len(model.c.shells) == 2
    d = describe(cfg)
    assert d["n_sats"] == 72 and len(d["shells"]) == 2
    assert d["shells"][1]["altitude_km"] == 1100
    assert d["period_min"] == d["shells"][0]["period_min"]        # top-level fields describe shell 1


@pytest.mark.parametrize("bad", [
    {"extra_shells": [{"planes": 72, "sats_per_plane": 22}, {"planes": 72, "sats_per_plane": 22}]},
    {"extra_shells": [{"planes": 6, "phasing": 6}]},
    {"extra_shells": [{"altitude_km": 100}]},
    {"extra_shells": [{}, {}, {}, {}]},                                  # at most 3 extra shells
])
def test_invalid_extra_shells_rejected(bad):
    with pytest.raises(ValidationError):
        ScenarioConfig(**bad)


def test_simulation_runs_on_two_shells():
    res = Simulation(build_world(ScenarioConfig(**SCEN))).tick(0)
    assert res.metrics["flows_total"] == 15
    shells = {d["shell"] for _, d in res.graph.nodes(data=True) if d.get("kind") == "sat"}
    assert shells == {0, 1}


def test_coverage_handles_mixed_altitudes():
    cfg = ScenarioConfig(**SCEN)
    cov = compute_coverage(build_world(cfg), CoverageParams(6.0, 2.0, 180.0))
    estimate = describe(cfg)["mean_sats_in_view_estimate"]
    assert abs(cov["summary"]["global_mean_visible"] - estimate) < 0.15
    values = [v for v in cov["mean_latency_ms"] if v is not None]
    assert values and min(values) >= 1.8                                 # 550 km zenith is 1.83 ms