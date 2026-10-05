from dataclasses import dataclass, replace

import networkx as nx

from .failures import FailureSchedule, FailureState, apply_failures
from .graph import TopologyDelta, build_graph, diff_graphs, gs_node, sat_node
from .links import LinkModel
from .routing import Flow, FlowResult, TrafficParams, default_flows, route_flows
from .serving import HandoffEvent, ServingTracker


def _r(x, n=3):
    return None if x is None else round(x, n)


@dataclass
class StepResult:
    t: float
    graph: nx.Graph
    delta: TopologyDelta | None
    handoffs: list[HandoffEvent]
    flows: list[FlowResult]
    metrics: dict
    failures: FailureState | None = None

    def flows_detail(self) -> list[dict]:
        return [f.to_dict() for f in self.flows]


def compute_metrics(t, G, flows, handoffs, delta, route_changes: int = 0) -> dict:
    reach = [f for f in flows if f.reachable]
    demand = sum(f.demand_gbps for f in reach)
    delivered = sum(f.delivered_gbps for f in reach)
    loaded = [d for _, _, d in G.edges(data=True) if d["load_gbps"] > 0]
    utils = [d["utilization"] for d in loaded]

    return {
        "t": t,
        "flows_total": len(flows),
        "flows_reachable": len(reach),
        "demand_gbps": _r(demand),
        "delivered_gbps": _r(delivered),
        "delivery_ratio": _r(delivered / demand, 4) if demand else None,
        "mean_latency_ms": _r(sum(f.latency_ms * f.demand_gbps for f in reach) / demand, 2)
        if demand else None,
        "max_latency_ms": _r(max((f.latency_ms for f in reach), default=None), 2),
        "loaded_links": len(loaded),
        "max_link_util": _r(max(utils, default=0.0)),
        "congested_links": sum(u >= 0.8 for u in utils),
        "overloaded_links": sum(u > 1.0 for u in utils),
        "handoffs": sum(e.reason in ("better", "lost") for e in handoffs),
        "outages": sum(e.reason == "outage" for e in handoffs),
        "links_added": len(delta.added) if delta else 0,
        "links_removed": len(delta.removed) if delta else 0,
        "mean_hops": _r(sum(f.hops * f.demand_gbps for f in reach) / demand, 2) if demand else None,
        "route_changes": route_changes,
    }


class Simulation:
    """Stateful simulation. Call tick(t) with increasing t."""

    def __init__(self, model: LinkModel, flows: list[Flow] | None = None,
                 params: TrafficParams = TrafficParams(), load_scale: float = 1.0,
                 hysteresis_deg: float = 15.0, schedule: FailureSchedule | None = None,
                 policy: str | None = None):
        self.model = model
        self.flows = flows if flows is not None else default_flows(len(model.stations))
        self.params = replace(params, policy=policy) if policy else params
        self.load_scale = load_scale
        self.serving = ServingTracker(hysteresis_deg)
        self.schedule = schedule if schedule is not None else FailureSchedule()
        self.prev: nx.Graph | None = None
        self.prev_paths: dict[tuple[str, str], tuple[str, ...]] = {}

    def tick(self, t: float) -> StepResult:
        snap = self.model.snapshot(t)
        state = self.schedule.active_at(t, self.model.c)
        snap = apply_failures(snap, state, self.model.c.n_sats)   # failures act before selection

        events = self.serving.update(t, snap.ground, len(self.model.stations))
        fresh = {e.station for e in events if e.reason in ("better", "lost")}

        G = build_graph(self.model, t, snap=snap, serving=dict(self.serving.serving),
                        handoff_stations=fresh)
        for s in state.sats:
            G.nodes[sat_node(s)]["failed"] = True
        for g in state.stations:
            G.nodes[gs_node(g)]["failed"] = True

        delta = diff_graphs(self.prev, G) if self.prev is not None else None
        results = route_flows(G, self.flows, self.params, self.load_scale)

        # route stability: primary-path changes between consecutive ticks
        new_paths: dict[tuple[str, str], tuple[str, ...]] = {}
        changes = 0
        for f in results:
            if not f.reachable:
                continue
            key, path = (f.src, f.dst), tuple(f.path)
            if key in self.prev_paths and self.prev_paths[key] != path:
                changes += 1
            new_paths[key] = path
        self.prev_paths = new_paths
        self.prev = G

        return StepResult(t, G, delta, events, results,
                          compute_metrics(t, G, results, events, delta, changes), failures=state)