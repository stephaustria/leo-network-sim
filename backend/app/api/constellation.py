from fastapi import APIRouter, Depends

from app.api.deps import world_from_query
from app.sim.frames import ecef_to_latlon_alt
from app.sim.worlds import World

router = APIRouter(prefix="/constellation", tags=["constellation"])


@router.get("/info")
def info(world: World = Depends(world_from_query)):
    c = world.model.c
    return {
        "n_sats": c.n_sats,
        "planes": c.n_planes,                       # total planes across shells (global plane ids)
        "sats_per_plane": c.per_plane,              # first shell
        "altitude_km": c.cfg.altitude_km,           # first shell
        "inclination_deg": c.cfg.inclination_deg,   # first shell
        "period_min": round(c.period_s / 60, 2),    # first shell
        "shells": [
            {"index": s.index, "n_sats": s.n_sats, "planes": s.n_planes, "sats_per_plane": s.per_plane,
             "altitude_km": s.cfg.altitude_km, "inclination_deg": s.cfg.inclination_deg,
             "period_min": round(s.period_s / 60, 2)}
            for s in c.shells
        ],
        "stations": [{"name": s.name, "lat": s.lat, "lon": s.lon} for s in world.model.stations],
    }


@router.get("/positions")
def positions(t: float = 0.0, world: World = Depends(world_from_query)):
    c = world.model.c
    lat, lon, alt = ecef_to_latlon_alt(c.positions_ecef(t))
    return {
        "t": t,
        "satellites": [
            {"id": i, "shell": int(c.shell_of[i]), "plane": int(c.plane[i]),
             "lat": round(float(lat[i]), 3), "lon": round(float(lon[i]), 3),
             "alt_km": round(float(alt[i]) / 1000, 1)}
            for i in range(c.n_sats)
        ],
    }