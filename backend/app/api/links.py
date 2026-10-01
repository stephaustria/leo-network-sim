import numpy as np
from fastapi import APIRouter

from app.api.constellation import constellation
from app.sim.links import LinkModel

router = APIRouter(prefix="/links", tags=["links"])

model = LinkModel(constellation)


@router.get("/summary")
def summary(t: float = 0.0):
    snap = model.snapshot(t)
    isl, gl = snap.isl, snap.ground

    stations = []
    for i, st in enumerate(model.stations):
        m = gl.station == i
        if m.any():
            best = np.argmax(np.where(m, gl.elevation_deg, -90))
            stations.append({
                "name": st.name,
                "visible_sats": int(m.sum()),
                "best_sat": int(gl.sat[best]),
                "best_elevation_deg": round(float(gl.elevation_deg[best]), 1),
                "best_latency_ms": round(float(gl.latency_ms[best]), 2),
                "best_capacity_gbps": round(float(gl.capacity_gbps[best]), 2),
                "best_loss": round(float(gl.loss[best]), 5),
            })
        else:
            stations.append({"name": st.name, "visible_sats": 0})

    return {
        "t": t,
        "isl": {
            "active": int(len(isl.a)),
            "candidates": snap.n_isl_candidates,
            "latency_ms_min": round(float(isl.latency_ms.min()), 2),
            "latency_ms_mean": round(float(isl.latency_ms.mean()), 2),
            "latency_ms_max": round(float(isl.latency_ms.max()), 2),
        },
        "ground_links": int(len(gl.sat)),
        "stations": stations,
    }