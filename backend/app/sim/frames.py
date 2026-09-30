import numpy as np

from .constants import OMEGA_EARTH, R_EARTH


def eci_to_ecef(pos: np.ndarray, t: float) -> np.ndarray:
    """Rotate ECI positions (N,3) into the Earth-fixed frame at time t."""
    theta = OMEGA_EARTH * t
    c, s = np.cos(theta), np.sin(theta)
    x = pos[:, 0] * c + pos[:, 1] * s
    y = -pos[:, 0] * s + pos[:, 1] * c
    return np.column_stack([x, y, pos[:, 2]])


def geodetic_to_ecef(lat_deg, lon_deg, alt_m=0.0) -> np.ndarray:
    """Lat/lon (degrees) to ECEF meters. Accepts scalars or arrays."""
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    r = R_EARTH + np.asarray(alt_m)
    return np.column_stack([
        np.atleast_1d(r * np.cos(lat) * np.cos(lon)),
        np.atleast_1d(r * np.cos(lat) * np.sin(lon)),
        np.atleast_1d(r * np.sin(lat)),
    ])


def ecef_to_latlon_alt(pos: np.ndarray):
    """ECEF (N,3) to (lat_deg, lon_deg, alt_m) arrays."""
    r = np.linalg.norm(pos, axis=1)
    lat = np.degrees(np.arcsin(pos[:, 2] / r))
    lon = np.degrees(np.arctan2(pos[:, 1], pos[:, 0]))
    return lat, lon, r - R_EARTH