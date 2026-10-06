import math
from statistics import mean

from .routing import DEFAULT_FLOW_GBPS

RECOVERY_TOLERANCE = 0.02     # goodput within 2 points of baseline counts as recovered


def _r(x, n=3):
    return None if x is None else round(x, n)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def percentile(values, q: float):
    """Nearest-rank percentile, q in (0, 1]."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(q * len(s)) - 1))
    return s[k]


def tick_goodput(tick: dict, params: dict) -> float:
    """Delivered / offered traffic. Unreachable flows count as lost."""
    offered = tick["flows_total"] * DEFAULT_FLOW_GBPS * params["load_scale"]
    if offered <= 0:
        return 1.0
    return min(1.0, (tick.get("delivered_gbps") or 0.0) / offered)


def failure_window(failures: list[dict] | None) -> dict | None:
    if not failures:
        return None
    ends = [f.get("t_end") for f in failures]
    return {"start": min(f["t_start"] for f in failures),
            "end": None if any(e is None for e in ends) else max(ends)}


def _failure_impact(ticks, goodput, params):
    win = failure_window(params.get("failures"))
    if win is None:
        return None
    start, end = win["start"], win["end"]
    rows = list(zip(ticks, goodput))
    before = [(x, g) for x, g in rows if x["t"] < start]
    during = [(x, g) for x, g in rows if x["t"] >= start and (end is None or x["t"] < end)]
    after = [(x, g) for x, g in rows if end is not None and x["t"] >= end]

    base_g, during_g = _mean([g for _, g in before]), _mean([g for _, g in during])
    base_lat = _mean([x["mean_latency_ms"] for x, _ in before])
    during_lat = _mean([x["mean_latency_ms"] for x, _ in during])

    recovered, recovery = None, None
    if end is not None and base_g is not None and after:
        recovered = False
        for x, g in after:
            if g >= base_g - RECOVERY_TOLERANCE:
                recovered, recovery = True, x["t"] - end
                break

    return {
        "start": start, "end": end,
        "baseline_goodput": _r(base_g, 4), "during_goodput": _r(during_g, 4),
        "goodput_drop": _r(base_g - during_g, 4) if None not in (base_g, during_g) else None,
        "baseline_latency_ms": _r(base_lat, 2), "during_latency_ms": _r(during_lat, 2),
        "latency_penalty_ms": _r(during_lat - base_lat, 2) if None not in (base_lat, during_lat) else None,
        "recovered": recovered, "recovery_time_s": recovery,
    }


def summarize_arm(ticks: list[dict], params: dict) -> dict:
    if not ticks:
        return {}
    ticks = sorted(ticks, key=lambda x: x["t"])
    dt = params["dt"]
    goodput = [tick_goodput(x, params) for x in ticks]
    lost = sum(
        max(0.0, x["flows_total"] * DEFAULT_FLOW_GBPS * params["load_scale"]
            - (x.get("delivered_gbps") or 0.0)) * dt
        for x in ticks
    )
    lat = [x["mean_latency_ms"] for x in ticks if x["mean_latency_ms"] is not None]
    changes = sum(x["route_changes"] for x in ticks)

    return {
        "ticks": len(ticks),
        "mean_goodput": _r(mean(goodput), 4),
        "min_goodput": _r(min(goodput), 4),
        "traffic_lost_gbit": _r(lost, 1),
        "mean_latency_ms": _r(_mean(lat), 2),
        "p95_latency_ms": _r(percentile(lat, 0.95), 2),
        "mean_hops": _r(_mean([x["mean_hops"] for x in ticks]), 2),
        "route_changes_total": changes,
        "route_changes_per_tick": _r(changes / len(ticks), 2),
        "mean_overloaded_links": _r(mean(x["overloaded_links"] for x in ticks), 2),
        "peak_link_util": _r(max((x["max_link_util"] or 0.0) for x in ticks), 3),
        "handoffs_total": sum(x["handoffs"] for x in ticks),
        "failure": _failure_impact(ticks, goodput, params),
    }