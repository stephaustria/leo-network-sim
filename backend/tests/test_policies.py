import pytest

from app.sim.constellation import Constellation
from app.sim.engine import Simulation
from app.sim.links import LinkModel, LinkParams
from app.sim.routing import TrafficParams

MODEL = LinkModel(Constellation())
FAST = LinkModel(Constellation(), params=LinkParams(ground_capacity_gbps=100.0))


def tick_with(policy, t, load_scale=1.0, model=MODEL):
    return Simulation(model, load_scale=load_scale, policy=policy).tick(t)


def good_tick():
    for t in range(0, 3000, 300):
        if tick_with("shortest_latency", t).metrics["flows_reachable"] >= 5:
            return t
    raise AssertionError("no tick with enough reachable flows")


def isl_excess(res):
    """Total utilization above 100% summed over inter-satellite links."""
    return sum(max(0.0, d["utilization"] - 1.0)
               for _, _, d in res.graph.edges(data=True) if d["kind"] != "ground")


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        TrafficParams(policy="random")


def test_simulation_policy_argument():
    assert Simulation(MODEL, policy="min_hop").params.policy == "min_hop"
    assert Simulation(MODEL).params.policy == "congestion_aware"


def test_each_policy_minimizes_its_own_objective():
    t = good_tick()
    hop = {(f.src, f.dst): f for f in tick_with("min_hop", t, 0.1).flows if f.reachable}
    lat = {(f.src, f.dst): f for f in tick_with("shortest_latency", t, 0.1).flows if f.reachable}
    common = hop.keys() & lat.keys()
    assert common
    for k in common:
        assert hop[k].hops <= lat[k].hops
        assert lat[k].latency_ms <= hop[k].latency_ms + 1.0   # slack for tiny queueing delay


def test_congestion_aware_spreads_load_better_than_static():
    t = good_tick()
    static = isl_excess(tick_with("shortest_latency", t, load_scale=100, model=FAST))
    aware = isl_excess(tick_with("congestion_aware", t, load_scale=100, model=FAST))
    assert static > 0
    assert aware <= static


def test_mean_hops_reported():
    m = tick_with("min_hop", good_tick()).metrics
    assert 2 <= m["mean_hops"] < 60


def test_route_changes_counted_over_time():
    sim = Simulation(MODEL, policy="min_hop")
    changes = [sim.tick(t).metrics["route_changes"] for t in range(0, 1440, 120)]
    assert changes[0] == 0
    assert sum(changes) > 0

def test_invalid_stickiness_rejected():
    with pytest.raises(ValueError):
        TrafficParams(route_stickiness=1.0)


def test_route_stickiness_reduces_flapping():
    def total_changes(stick):
        sim = Simulation(MODEL, params=TrafficParams(route_stickiness=stick), policy="min_hop")
        return sum(sim.tick(t).metrics["route_changes"] for t in range(0, 1200, 120))

    assert total_changes(0.2) <= total_changes(0.0)