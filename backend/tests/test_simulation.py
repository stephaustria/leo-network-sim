from app.sim.constellation import Constellation
from app.sim.engine import Simulation
from app.sim.graph import gs_node
from app.sim.links import LinkModel
from app.sim.routing import Flow, TrafficParams, queue_delay_ms
from app.sim.serving import ServingTracker

MODEL = LinkModel(Constellation())


def good_tick(load_scale, min_reachable=3):
    """First tick (fresh sim) where enough flows are reachable."""
    for t in range(0, 3000, 300):
        res = Simulation(MODEL, load_scale=load_scale).tick(t)
        if res.metrics["flows_reachable"] >= min_reachable:
            return res
    raise AssertionError("no tick with enough reachable flows")


def test_queue_delay_monotonic_and_bounded():
    p = TrafficParams()
    vals = [queue_delay_ms(u, p) for u in (0.0, 0.3, 0.6, 0.9, 1.0, 5.0)]
    assert vals == sorted(vals)
    assert vals[0] == 0.0 and vals[-1] == vals[-2] < 20


def test_one_serving_link_per_station():
    res = good_tick(1.0)
    ground = [(u, v) for u, v, d in res.graph.edges(data=True) if d["kind"] == "ground"]
    assert len(ground) <= len(MODEL.stations)


def test_light_load_is_clean_heavy_load_drops_traffic():
    light = good_tick(0.1).metrics
    heavy = good_tick(40.0).metrics
    assert light["delivery_ratio"] > 0.95
    assert light["overloaded_links"] == 0
    assert heavy["delivery_ratio"] < 0.5
    assert heavy["overloaded_links"] > 0
    assert heavy["mean_latency_ms"] > light["mean_latency_ms"]


def test_load_conservation_on_source_ground_link():
    for t in range(0, 3000, 300):
        flow = Flow(gs_node(0), gs_node(1), 0.4)
        sim = Simulation(MODEL, flows=[flow])
        res = sim.tick(t)
        if res.flows[0].reachable:
            src_edges = [d for u, v, d in res.graph.edges(data=True)
                         if d["kind"] == "ground" and gs_node(0) in (u, v)]
            assert len(src_edges) == 1
            assert abs(src_edges[0]["load_gbps"] - 0.4) < 1e-9
            return
    raise AssertionError("flow never reachable")


def test_handoffs_happen_and_serving_is_visible():
    sim = Simulation(MODEL)
    reasons = set()
    for t in range(0, 1800, 60):
        res = sim.tick(t)
        reasons |= {e.reason for e in res.handoffs}
        snap = MODEL.snapshot(t)
        for g, s in sim.serving.serving.items():
            if s is not None:
                assert ((snap.ground.station == g) & (snap.ground.sat == s)).any()
    assert "acquired" in reasons
    assert reasons & {"better", "lost"}


def test_hysteresis_keeps_satellite():
    tr = ServingTracker(hysteresis_deg=15.0)
    snap0 = MODEL.snapshot(0).ground
    tr.update(0, snap0, len(MODEL.stations))
    before = dict(tr.serving)
    events = tr.update(0, snap0, len(MODEL.stations))   # same snapshot again
    assert events == [] and tr.serving == before

def test_zero_hysteresis_never_hands_off_to_same_satellite():
    tr = ServingTracker(hysteresis_deg=0.0)
    snap = MODEL.snapshot(0).ground
    tr.update(0, snap, len(MODEL.stations))
    assert tr.update(0, snap, len(MODEL.stations)) == []


def test_lower_hysteresis_means_more_handoffs():
    def total(h):
        sim = Simulation(MODEL, flows=[], hysteresis_deg=h)      # no traffic: faster
        return sum(sim.tick(t).metrics["handoffs"] for t in range(0, 1200, 60))

    assert total(0.0) > total(40.0)