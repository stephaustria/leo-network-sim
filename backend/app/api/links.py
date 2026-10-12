import numpy as np
from fastapi import APIRouter, Depends

from app.api.deps import world_from_query
from app.sim.worlds import World

router = APIRouter(prefix="/links", tags=["links"])


@router.get("/summary")
def summary(t: float = 0.0, world: World = Depends(world_from_query)):
    model = world.model
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

    isl_stats = {"active": int(len(isl.a)), "candidates": snap.n_isl_candidates}
    if len(isl.a):
        isl_stats.update({
            "latency_ms_min": round(float(isl.latency_ms.min()), 2),
            "latency_ms_mean": round(float(isl.latency_ms.mean()), 2),
            "latency_ms_max": round(float(isl.latency_ms.max()), 2),
        })

    return {"t": t, "isl": isl_stats, "ground_links": int(len(gl.sat)), "stations": stations}