import numpy as np

from .frames import ecef_to_latlon_alt


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def sat_latlon(constellation, t: float) -> list[list[float]]:
    """[[lat, lon], ...] for every satellite at time t."""
    lat, lon, _ = ecef_to_latlon_alt(constellation.positions_ecef(t))
    return np.column_stack([lat, lon]).round(2).tolist()


def links_from_graph(G) -> list[dict]:
    """Ground links (always) plus any link carrying traffic."""
    return [
        {"u": u, "v": v, "kind": d["kind"], "distance_km": d["distance_km"],
         "load_gbps": d["load_gbps"], "capacity_gbps": d["capacity_gbps"],
         "utilization": d["utilization"], "queue_ms": d["queue_ms"],
         "loss_eff": d["loss_eff"]}
        for u, v, d in G.edges(data=True)
        if d["kind"] == "ground" or d["load_gbps"] > 0
    ]


def build_frame(*, t, mode, sats, links, flows, handoffs, metrics, progress=None,
                failures=None) -> dict:
    ground, loaded = [], []
    for l in links:
        if l["kind"] == "ground":
            g, s = (l["u"], l["v"]) if l["u"][0] == "G" else (l["v"], l["u"])
            ground.append({"station": int(g[1:]), "sat": int(s[1:]),
                           "load_gbps": _r(l["load_gbps"]),
                           "capacity_gbps": _r(l["capacity_gbps"]),
                           "utilization": _r(l["utilization"])})
        elif l["load_gbps"] > 0:
            loaded.append({"u": l["u"], "v": l["v"], "kind": l["kind"],
                           "utilization": _r(l["utilization"]),
                           "queue_ms": _r(l["queue_ms"]),
                           "loss": _r(l["loss_eff"], 5)})
    return {"type": "frame", "t": t, "mode": mode, "progress": progress,
            "sats": sats, "ground_links": ground, "loaded_links": loaded,
            "flows": flows, "handoffs": handoffs, "metrics": metrics,
            "failures": failures or {"sats": [], "stations": [], "isls": []}}


def live_frame(model, res, progress=None) -> dict:
    return build_frame(
        t=res.t, mode="live", sats=sat_latlon(model.c, res.t),
        links=links_from_graph(res.graph), flows=res.flows_detail(),
        handoffs=[e.to_dict() for e in res.handoffs], metrics=res.metrics,
        progress=progress,
        failures=res.failures.to_dict() if res.failures else None,
    )


def init_message(model, flows) -> dict:
    cfg = model.c.cfg
    return {
        "type": "init",
        "constellation": {
            "n_sats": model.c.n_sats, "planes": cfg.planes,
            "sats_per_plane": cfg.sats_per_plane, "altitude_km": cfg.altitude_km,
            "inclination_deg": cfg.inclination_deg,
            "period_min": round(float(model.c.period_s) / 60, 2),
        },
        "stations": [{"id": i, "name": s.name, "lat": s.lat, "lon": s.lon}
                     for i, s in enumerate(model.stations)],
        "isl_pairs": model.pairs.tolist(),
        "flows": [{"src": f.src, "dst": f.dst, "demand_gbps": f.demand_gbps} for f in flows],
    }