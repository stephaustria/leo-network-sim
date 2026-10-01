from app.sim.constellation import Constellation
from app.sim.graph import (TopologyTracker, build_graph, diff_graphs, gs_node,
                           is_sat, shortest_latency)
from app.sim.links import LinkModel


def make():
    c = Constellation()
    return c, LinkModel(c)


def test_graph_structure():
    c, m = make()
    G = build_graph(m, 0)
    snap = m.snapshot(0)
    assert G.number_of_nodes() == c.n_sats + len(m.stations)
    assert G.number_of_edges() == len(snap.isl.a) + len(snap.ground.sat)
    for _, _, d in G.edges(data=True):
        assert d["latency_ms"] > 0 and d["capacity_gbps"] > 0
        assert d["kind"] in ("isl_intra", "isl_cross", "ground")


def test_no_change_means_empty_delta():
    _, m = make()
    d = diff_graphs(build_graph(m, 100), build_graph(m, 100))
    assert not d.added and not d.removed


def test_ground_links_change_but_isl_stable():
    _, m = make()
    d = diff_graphs(build_graph(m, 0), build_graph(m, 600))
    kinds = {k for _, _, k in d.added + d.removed}
    assert "ground" in kinds
    assert not kinds & {"isl_intra", "isl_cross"}   # default params keep all ISLs up


def test_tracker_returns_delta_after_first_step():
    _, m = make()
    tr = TopologyTracker(m)
    _, d0 = tr.advance(0)
    _, d1 = tr.advance(120)
    assert d0 is None and d1 is not None


def test_sf_to_london_route():
    _, m = make()
    found = 0
    for t in range(0, 3000, 300):
        G = build_graph(m, t)
        res = shortest_latency(G, gs_node(0), gs_node(1))
        if res:
            found += 1
            ms, path = res
            assert 28 < ms < 150                      # >= light time over ~8,600 km
            assert all(is_sat(n) for n in path[1:-1])  # no ground transit
    assert found >= 1