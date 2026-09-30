from fastapi import APIRouter

from app.sim.constellation import Constellation
from app.sim.frames import ecef_to_latlon_alt
from app.sim.ground import DEFAULT_STATIONS

router = APIRouter(prefix="/constellation", tags=["constellation"])

constellation = Constellation()


@router.get("/info")
def info():
    c = constellation
    return {
        "n_sats": c.n_sats,
        "planes": c.n_planes,
        "sats_per_plane": c.per_plane,
        "altitude_km": c.cfg.altitude_km,
        "inclination_deg": c.cfg.inclination_deg,
        "period_min": round(c.period_s / 60, 2),
        "stations": [s.__dict__ for s in DEFAULT_STATIONS],
    }


@router.get("/positions")
def positions(t: float = 0.0):
    lat, lon, alt = ecef_to_latlon_alt(constellation.positions_ecef(t))
    return {
        "t": t,
        "satellites": [
            {"id": i, "plane": int(constellation.plane[i]),
             "lat": round(float(lat[i]), 3), "lon": round(float(lon[i]), 3),
             "alt_km": round(float(alt[i]) / 1000, 1)}
            for i in range(constellation.n_sats)
        ],
    }