from dataclasses import dataclass, field

import networkx as nx

from .frames import ecef_to_latlon_alt
from .links import LinkModel


def sat_node(i) -> str:
    return f"S{int(i)}"


def gs_node(i) -> str:
    return f"G{int(i)}"


def is_sat(n: str) -> bool:
    return n[0] == "S"


def is_gs(n: str) -> bool:
    return n[0] == "G"


def build_graph(model: LinkModel, t: float) -> nx.Graph:
    """Network graph of the constellation at time t."""
    snap = model.snapshot(t)
    lat, lon, alt = ecef_to_latlon_alt(model.c.positions_ecef(t))
    c = model.c

    G = nx.Graph(t=t)
    for i in range(c.n_sats):
        G.add_node(sat_node(i), kind="sat", plane=int(c.plane[i]), slot=int(c.slot[i]),
                   lat=float(lat[i]), lon=float(lon[i]), alt_km=float(alt[i]) / 1000)
    for i, st in enumerate(model.stations):
        G.add_node(gs_node(i), kind="ground", name=st.name, lat=st.lat, lon=st.lon)

    isl = snap.isl
    for k in range(len(isl.a)):
        G.add_edge(
            sat_node(isl.a[k]), sat_node(isl.b[k]),
            kind="isl_cross" if isl.cross_plane[k] else "isl_intra",
            distance_km=float(isl.distance_km[k]),
            latency_ms=float(isl.latency_ms[k]),
            capacity_gbps=float(isl.capacity_gbps[k]),
            loss=float(isl.loss[k]),
            load_gbps=0.0,
        )

    gl = snap.ground
    for k in range(len(gl.sat)):
        G.add_edge(
            gs_node(gl.station[k]), sat_node(gl.sat[k]),
            kind="ground",
            distance_km=float(gl.range_km[k]),
            elevation_deg=float(gl.elevation_deg[k]),
            latency_ms=float(gl.latency_ms[k]),
            capacity_gbps=float(gl.capacity_gbps[k]),
            loss=float(gl.loss[k]),
            load_gbps=0.0,
        )
    return G


# ---------- topology change tracking ----------

def _edge_kinds(G: nx.Graph) -> dict[tuple[str, str], str]:
    return {tuple(sorted((u, v))): d["kind"] for u, v, d in G.edges(data=True)}


@dataclass
class TopologyDelta:
    t0: float
    t1: float
    added: list[tuple[str, str, str]] = field(default_factory=list)    # (u, v, kind)
    removed: list[tuple[str, str, str]] = field(default_factory=list)

    def counts_by_kind(self) -> dict:
        out: dict = {"added": {}, "removed": {}}
        for name in ("added", "removed"):
            for _, _, kind in getattr(self, name):
                out[name][kind] = out[name].get(kind, 0) + 1
        return out


def diff_graphs(old: nx.Graph, new: nx.Graph) -> TopologyDelta:
    ko, kn = _edge_kinds(old), _edge_kinds(new)
    return TopologyDelta(
        t0=old.graph["t"], t1=new.graph["t"],
        added=sorted((*k, kn[k]) for k in kn.keys() - ko.keys()),
        removed=sorted((*k, ko[k]) for k in ko.keys() - kn.keys()),
    )


class TopologyTracker:
    """Stateful: call advance(t) each tick to get the new graph and what changed."""

    def __init__(self, model: LinkModel):
        self.model = model
        self.graph: nx.Graph | None = None

    def advance(self, t: float) -> tuple[nx.Graph, TopologyDelta | None]:
        new = build_graph(self.model, t)
        delta = diff_graphs(self.graph, new) if self.graph is not None else None
        self.graph = new
        return new, delta


# ---------- analysis helpers ----------

def graph_stats(G: nx.Graph) -> dict:
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    main = comps[0]
    stations = [n for n in G if is_gs(n)]
    kinds: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "edges_by_kind": kinds,
        "components": len(comps),
        "stations_in_main_component": sum(1 for s in stations if s in main),
        "stations_total": len(stations),
    }


def shortest_latency(G: nx.Graph, src: str, dst: str):
    """Lowest-latency path from src to dst, transiting satellites only.
    Returns (latency_ms, path) or None if unreachable."""
    H = G.subgraph([n for n in G if is_sat(n) or n in (src, dst)])
    try:
        path = nx.shortest_path(H, src, dst, weight="latency_ms")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    ms = sum(H[u][v]["latency_ms"] for u, v in zip(path, path[1:]))
    return ms, path