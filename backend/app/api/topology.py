from fastapi import APIRouter

from app.api.links import model
from app.sim.graph import (build_graph, diff_graphs, graph_stats, gs_node,
                           shortest_latency)

router = APIRouter(prefix="/topology", tags=["topology"])


def _round(d: dict) -> dict:
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in d.items()}


@router.get("/summary")
def summary(t: float = 0.0):
    G = build_graph(model, t)
    src = gs_node(0)
    routes = []
    for i in range(1, len(model.stations)):
        dst = gs_node(i)
        res = shortest_latency(G, src, dst)
        routes.append({
            "from": G.nodes[src]["name"], "to": G.nodes[dst]["name"],
            **({"latency_ms": round(res[0], 2), "hops": len(res[1]) - 1} if res
               else {"latency_ms": None, "hops": None}),
        })
    return {"t": t, **graph_stats(G), "routes_from_first_station": routes}


@router.get("/delta")
def delta(t0: float = 0.0, t1: float = 60.0):
    d = diff_graphs(build_graph(model, t0), build_graph(model, t1))
    return {
        "t0": t0, "t1": t1,
        **d.counts_by_kind(),
        "added_sample": d.added[:20],
        "removed_sample": d.removed[:20],
    }


@router.get("/graph")
def graph(t: float = 0.0):
    """Full node/edge list for the frontend."""
    G = build_graph(model, t)
    return {
        "t": t,
        "nodes": [{"id": n, **_round(d)} for n, d in G.nodes(data=True)],
        "edges": [{"source": u, "target": v, **_round(d)} for u, v, d in G.edges(data=True)],
    }