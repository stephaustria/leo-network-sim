import pytest

from app.sim.constellation import Constellation
from app.sim.engine import Simulation
from app.sim.failures import FailureEvent, FailureSchedule, apply_failures
from app.sim.graph import gs_node
from app.sim.links import LinkModel
from app.sim.presets import live_failure_events, seam_cut
from app.sim.routing import Flow

C = Constellation()
MODEL = LinkModel(C)
N_STATIONS = len(MODEL.stations)


def sched(*events):
    return FailureSchedule.from_dicts(list(events), C, N_STATIONS)


def good_tick(flow):
    """First tick where this flow is reachable in a healthy network."""
    for t in range(0, 3000, 300):
        if Simulation(MODEL, flows=[flow]).tick(t).flows[0].reachable:
            return t
    raise AssertionError("flow never reachable")


def test_event_windows():
    s = sched({"kind": "satellite", "target": 5, "t_start": 100, "t_end": 200})
    assert 5 not in s.active_at(50, C).sats
    assert 5 in s.active_at(100, C).sats
    assert 5 in s.active_at(199, C).sats
    assert 5 not in s.active_at(200, C).sats


def test_plane_expands_to_all_its_satellites():
    s = sched({"kind": "plane", "target": 3})
    assert s.active_at(0, C).sats == set(range(3 * C.per_plane, 4 * C.per_plane))


def test_isl_target_is_normalized():
    s = sched({"kind": "isl", "target": [9, 4]})
    assert s.active_at(0, C).isls == {(4, 9)}


@pytest.mark.parametrize("bad", [
    {"kind": "bogus", "target": 1},
    {"kind": "satellite", "target": 9999},
    {"kind": "plane", "target": 99},
    {"kind": "station", "target": 99},
    {"kind": "isl", "target": [1]},
    {"kind": "isl", "target": [3, 3]},
    {"kind": "satellite", "target": "abc"},
    {"kind": "satellite", "target": 1, "t_start": 100, "t_end": 50},
])
def test_invalid_events_rejected(bad):
    with pytest.raises(ValueError):
        sched(bad)


def test_failed_satellite_loses_all_its_links():
    snap = MODEL.snapshot(0)
    state = sched({"kind": "satellite", "target": 10}).active_at(0, C)
    out = apply_failures(snap, state, C.n_sats)
    assert len(out.isl.a) == len(snap.isl.a) - 4          # 4-regular +Grid
    assert 10 not in out.isl.a and 10 not in out.isl.b
    assert 10 not in out.ground.sat


def test_failed_isl_removes_exactly_one_link():
    snap = MODEL.snapshot(0)
    a, b = (int(x) for x in MODEL.pairs[0])
    state = sched({"kind": "isl", "target": [a, b]}).active_at(0, C)
    out = apply_failures(snap, state, C.n_sats)
    assert len(out.isl.a) == len(snap.isl.a) - 1
    assert not ((out.isl.a == a) & (out.isl.b == b)).any()


def test_failed_station_loses_ground_links_only():
    snap = MODEL.snapshot(0)
    state = sched({"kind": "station", "target": 0}).active_at(0, C)
    out = apply_failures(snap, state, C.n_sats)
    assert not (out.ground.station == 0).any()
    assert len(out.ground.station) == len(snap.ground.station) - int((snap.ground.station == 0).sum())
    assert len(out.isl.a) == len(snap.isl.a)


def test_no_failures_returns_same_snapshot():
    snap = MODEL.snapshot(0)
    assert apply_failures(snap, sched().active_at(0, C), C.n_sats) is snap


def test_failed_station_makes_its_flows_unreachable_then_recovers():
    flow = Flow(gs_node(0), gs_node(1), 0.3)
    t = good_tick(flow)
    s = sched({"kind": "station", "target": 0, "t_start": 0, "t_end": t + 1})
    sim = Simulation(MODEL, flows=[flow], schedule=s)

    down = sim.tick(t)
    assert not down.flows[0].reachable
    assert down.graph.nodes[gs_node(0)]["failed"] is True

    up = sim.tick(t + 1)                      # failure ended; one second later
    assert up.flows[0].reachable


def test_serving_satellite_failure_triggers_handoff():
    sim = Simulation(MODEL)
    sim.tick(0)
    served = {g: s for g, s in sim.serving.serving.items() if s is not None}
    assert served, "no station has a serving satellite at t=0"
    g, s = next(iter(served.items()))

    sim.schedule.add(FailureEvent("satellite", s, t_start=60))
    res = sim.tick(60)

    assert sim.serving.serving[g] != s
    assert any(e.station == g and e.reason in ("lost", "outage") for e in res.handoffs)
    assert res.graph.nodes[f"S{s}"]["failed"] is True


def test_recover_all_closes_open_events():
    s = sched({"kind": "satellite", "target": 2, "t_start": 0})
    assert 2 in s.active_at(500, C).sats
    s.recover_all(500)
    assert 2 not in s.active_at(500, C).sats
    assert 2 in s.active_at(499, C).sats

def test_live_failure_events():
    ev = live_failure_events({"kind": "plane", "target": 3, "duration": 300},
                             120.0, C, MODEL.pairs, N_STATIONS)
    assert len(ev) == 1 and ev[0].t_start == 120.0 and ev[0].t_end == 420.0

    seam = live_failure_events({"kind": "seam", "target": 5}, 0.0, C, MODEL.pairs, N_STATIONS)
    assert len(seam) == C.per_plane
    assert all(e.kind == "isl" and e.t_end is None for e in seam)

    assert len(seam_cut(C, MODEL.pairs, C.n_planes - 1, 0.0)) == C.per_plane   # wrap-around

    for bad in ({"kind": "bogus", "target": 1}, {"kind": "satellite", "target": 9999},
                {"kind": "satellite"}, {"kind": "plane", "target": 1, "duration": -5}):
        with pytest.raises(ValueError):
            live_failure_events(bad, 0.0, C, MODEL.pairs, N_STATIONS)


def test_recover_all_also_cuts_short_scheduled_events():
    s = sched({"kind": "satellite", "target": 2, "t_start": 0, "t_end": 1000})
    s.recover_all(500)
    assert 2 not in s.active_at(500, C).sats
    assert 2 in s.active_at(499, C).sats