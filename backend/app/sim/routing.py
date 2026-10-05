from collections import Counter
from dataclasses import dataclass

import networkx as nx

from .graph import gs_node

POLICIES = ("min_hop", "shortest_latency", "congestion_aware")


@dataclass(frozen=True)
class TrafficParams:
    max_util: float = 0.98            # cap used in the queueing formula
    queue_scale_ms: float = 0.2       # queueing delay = scale * rho / (1 - rho)
    overload_penalty_ms: float = 20.0  # routing-only penalty per 100% overload
    handoff_loss: float = 0.02        # extra loss on a freshly handed-off link
    chunks: int = 4                   # each flow is split into this many chunks
    policy: str = "congestion_aware"

    def __post_init__(self):
        if self.policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}, got {self.policy!r}")


@dataclass(frozen=True)
class Flow:
    src: str
    dst: str
    demand_gbps: float


@dataclass
class FlowResult:
    src: str
    dst: str
    demand_gbps: float
    reachable: bool
    latency_ms: float | None
    loss: float | None
    delivered_gbps: float
    hops: int | None
    max_util: float | None
    distinct_paths: int
    path: list[str]

    def to_dict(self) -> dict:
        r = lambda x, n=3: None if x is None else round(x, n)
        return {"src": self.src, "dst": self.dst, "demand_gbps": r(self.demand_gbps),
                "reachable": self.reachable, "latency_ms": r(self.latency_ms, 2),
                "loss": r(self.loss, 5), "delivered_gbps": r(self.delivered_gbps),
                "hops": self.hops, "max_util": r(self.max_util),
                "distinct_paths": self.distinct_paths, "path": self.path}


def default_flows(n_stations: int, demand_gbps: float = 0.15) -> list[Flow]:
    """Full mesh: one flow per station pair."""
    return [Flow(gs_node(i), gs_node(j), demand_gbps)
            for i in range(n_stations) for j in range(i + 1, n_stations)]


def queue_delay_ms(util: float, p: TrafficParams) -> float:
    u = min(util, p.max_util)
    return p.queue_scale_ms * u / (1.0 - u)


def edge_cost(d: dict, p: TrafficParams, extra_gbps: float = 0.0) -> float:
    """Congestion-aware cost: latency + queueing at the utilization *after* adding extra_gbps."""
    util = (d["load_gbps"] + extra_gbps) / d["capacity_gbps"]
    cost = d["latency_ms"] + queue_delay_ms(util, p)
    if util > 1.0:
        cost += p.overload_penalty_ms * (util - 1.0)
    return cost


def policy_cost(d: dict, p: TrafficParams, extra_gbps: float = 0.0) -> float:
    if p.policy == "min_hop":
        return 1.0 + 1e-6 * d["latency_ms"]      # hops first, latency only breaks ties
    if p.policy == "shortest_latency":
        return d["latency_ms"]
    return edge_cost(d, p, extra_gbps)


def _route(G: nx.Graph, src: str, dst: str, chunk_gbps: float, p: TrafficParams):
    if src not in G or dst not in G:
        return None

    def weight(u, v, d):
        for n in (u, v):                    # ground stations can't be transit nodes
            if n[0] == "G" and n != src and n != dst:
                return None                 # None hides the edge from Dijkstra
        return policy_cost(d, p, chunk_gbps)

    try:
        return nx.shortest_path(G, src, dst, weight=weight)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def finalize_links(G: nx.Graph, p: TrafficParams) -> None:
    """Derive utilization, queueing delay and effective loss on every edge."""
    for _, _, d in G.edges(data=True):
        load, cap = d["load_gbps"], d["capacity_gbps"]
        util = load / cap
        congestion_loss = max(0.0, 1.0 - cap / load) if load > 0 else 0.0
        handoff_loss = p.handoff_loss if d.get("handoff") else 0.0
        ok = (1 - d["loss"]) * (1 - congestion_loss) * (1 - handoff_loss)
        d["utilization"] = util
        d["queue_ms"] = queue_delay_ms(util, p)
        d["loss_eff"] = 1 - ok


def _flow_result(G: nx.Graph, f: Flow, paths: list[list[str]], demand: float) -> FlowResult:
    if not paths:
        return FlowResult(f.src, f.dst, demand, False, None, None, 0.0, None, None, 0, [])

    n = len(paths)
    lat = loss = max_util = delivered = 0.0
    for path in paths:
        l, ok, mu = 0.0, 1.0, 0.0
        for u, v in zip(path, path[1:]):
            d = G[u][v]
            l += d["latency_ms"] + d["queue_ms"]
            ok *= 1 - d["loss_eff"]
            mu = max(mu, d["utilization"])
        lat += l / n
        loss += (1 - ok) / n
        delivered += (demand / n) * ok
        max_util = max(max_util, mu)

    primary = list(Counter(map(tuple, paths)).most_common(1)[0][0])
    return FlowResult(f.src, f.dst, demand, True, lat, loss, delivered,
                      len(primary) - 1, max_util, len({tuple(x) for x in paths}), primary)


def route_flows(G: nx.Graph, flows: list[Flow], p: TrafficParams,
                load_scale: float = 1.0) -> list[FlowResult]:
    """Greedy incremental assignment. Mutates edge loads in G."""
    load_aware = p.policy == "congestion_aware"
    chunk_paths: list[list[list[str]]] = [[] for _ in flows]

    for _ in range(p.chunks):                       # rounds, so flows share fairly
        for i, f in enumerate(flows):
            chunk = f.demand_gbps * load_scale / p.chunks
            if chunk <= 0:
                continue
            if not load_aware and chunk_paths[i]:
                path = chunk_paths[i][0]            # static policy: same path every chunk
            else:
                path = _route(G, f.src, f.dst, chunk, p)
            if path is None:
                continue
            for u, v in zip(path, path[1:]):
                G[u][v]["load_gbps"] += chunk
            chunk_paths[i].append(path)

    finalize_links(G, p)
    return [_flow_result(G, f, chunk_paths[i], f.demand_gbps * load_scale)
            for i, f in enumerate(flows)]