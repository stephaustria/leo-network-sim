import numpy as np
import pytest

from app.sim.constants import R_EARTH
from app.sim.constellation import Constellation, WalkerConfig
from app.sim.engine import Simulation
from app.sim.isl import clear_of_earth, greedy_match, inter_shell_links, nearest_links
from app.sim.links import KIND_NEAR, KIND_SHELL, IslPolicy, LinkModel
from app.sim.tle import TleShell, parse_tle_text, walker_tle_text

MID = WalkerConfig(planes=12, sats_per_plane=12, altitude_km=1000, inclination_deg=55)
HIGH = WalkerConfig(planes=12, sats_per_plane=12, altitude_km=1300, inclination_deg=55)


def test_greedy_match_respects_degree_caps_and_prefers_short_edges():
    a, b, d = np.array([0, 0, 0]), np.array([1, 2, 3]), np.array([3.0, 1.0, 2.0])
    keep = greedy_match(a, b, d, 2, 2, 4, 4, shared=True)       # node 0 may keep only two links
    assert sorted(b[keep].tolist()) == [2, 3]


def test_nearest_links_respect_range_degree_and_geometry():
    pos = Constellation().positions_ecef(0)
    a, b = nearest_links(pos, 4, 5_000_000.0, 80_000.0)
    deg = np.bincount(np.concatenate([a, b]), minlength=len(pos))
    assert deg.max() <= 4 and deg.mean() > 3.0
    assert np.all(a < b) and len(set(zip(a.tolist(), b.tolist()))) == len(a)
    assert np.linalg.norm(pos[a] - pos[b], axis=1).max() <= 5_000_000.0
    assert clear_of_earth(pos[a], pos[b], 80_000.0).all()


def test_links_through_the_earth_are_rejected():
    r = R_EARTH + 550e3
    angle = np.radians(20)
    pos = np.array([[r, 0, 0], [r * np.cos(angle), r * np.sin(angle), 0], [-r, 0, 0]], dtype=float)
    a, b = nearest_links(pos, 4, 2e7, 80_000.0)               # range allows every pair
    assert set(zip(a.tolist(), b.tolist())) == {(0, 1)}        # the others pass through the Earth


def test_inter_shell_links_connect_different_shells_within_the_degree_limit():
    pos = Constellation([MID, HIGH]).positions_ecef(0)
    a, b = inter_shell_links(pos[:144], pos[144:], 1, 5_000_000.0, 80_000.0)
    assert len(a) > 0
    assert np.bincount(a, minlength=144).max() <= 1 and np.bincount(b, minlength=144).max() <= 1
    assert np.linalg.norm(pos[a] - pos[144 + b], axis=1).max() <= 5_000_000.0


def test_isl_policy_modes():
    c = Constellation(MID)
    auto, none, near = (LinkModel(c, isl=IslPolicy(mode=m)) for m in ("auto", "none", "nearest"))
    assert not auto.isl_dynamic and len(auto.pairs) == 2 * 144
    assert not none.isl_dynamic and len(none.snapshot(0).isl.a) == 0

    snap = near.snapshot(0)
    assert near.isl_dynamic and len(near.pairs) == 0
    assert len(snap.isl.a) > 0 and (snap.isl.kind == KIND_NEAR).all()
    assert np.bincount(np.concatenate([snap.isl.a, snap.isl.b]), minlength=144).max() <= 4


def test_grid_mode_cannot_link_tle_satellites_but_nearest_can():
    c = Constellation(TleShell(parse_tle_text(walker_tle_text(12, 12, 1000.0, 55.0))))
    assert len(LinkModel(c, isl=IslPolicy(mode="grid")).snapshot(0).isl.a) == 0
    assert len(LinkModel(c, isl=IslPolicy(mode="auto")).snapshot(0).isl.a) > 0


def test_nearest_topology_changes_as_satellites_move():
    m = LinkModel(Constellation(), isl=IslPolicy(mode="nearest"))
    pairs = lambda s: set(zip(s.a.tolist(), s.b.tolist()))
    assert pairs(m.snapshot(0).isl) != pairs(m.snapshot(1800).isl)


def test_inter_shell_links_appear_in_the_model():
    c = Constellation([MID, HIGH])
    m = LinkModel(c, isl=IslPolicy(mode="grid", inter_shell_degree=1))
    isl = m.snapshot(0).isl
    shell_links = isl.kind == KIND_SHELL
    assert m.isl_dynamic and shell_links.any()
    assert (c.shell_of[isl.a[shell_links]] != c.shell_of[isl.b[shell_links]]).all()
    ends = np.concatenate([isl.a[shell_links], isl.b[shell_links]])
    assert np.bincount(ends, minlength=288).max() <= 1
    assert (isl.kind[~shell_links] <= 1).all()                  # the grid links are still there


def test_tle_only_network_routes_with_nearest_links_but_not_without():
    c = Constellation(TleShell(parse_tle_text(walker_tle_text(12, 12, 1000.0, 55.0))))

    def reachable(policy):
        sim = Simulation(LinkModel(c, isl=policy))
        return sum(sim.tick(t).metrics["flows_reachable"] for t in range(0, 3000, 300))

    with_isl, without = reachable(IslPolicy(mode="auto")), reachable(IslPolicy(mode="none"))
    assert with_isl > 0 and with_isl >= without


def test_graph_edges_use_the_new_kind_names():
    sim = Simulation(LinkModel(Constellation(MID), isl=IslPolicy(mode="nearest")))
    kinds = {d["kind"] for _, _, d in sim.tick(0).graph.edges(data=True)}
    assert "isl_near" in kinds and kinds <= {"isl_near", "ground"}

def test_planned_links_are_held_between_replans():
    m = LinkModel(Constellation(), isl=IslPolicy(mode="nearest", replan_s=300))

    def pairs(t):
        isl = m.snapshot(t).isl
        return set(zip(isl.a.tolist(), isl.b.tolist()))

    p0, p100, p300 = pairs(0), pairs(100), pairs(300)
    assert p100 <= p0                              # inside an interval nothing new appears
    assert len(p100) >= 0.8 * len(p0)              # and few links break in 100 s
    assert p300 - p0                               # the next interval plans afresh


def test_replan_every_tick_rewires_continuously():
    m = LinkModel(Constellation(), isl=IslPolicy(mode="nearest", replan_s=0))

    def pairs(t):
        isl = m.snapshot(t).isl
        return set(zip(isl.a.tolist(), isl.b.tolist()))

    assert pairs(100) - pairs(0)


def test_invalid_replan_interval():
    with pytest.raises(ValueError):
        IslPolicy(replan_s=-1)