from datetime import datetime, timedelta, timezone

import numpy as np

from .constants import OMEGA_EARTH, R_EARTH

J2000_JD = 2451545.0
_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)


def jd_to_datetime(jd: float) -> datetime:
    return _J2000 + timedelta(days=jd - J2000_JD)


def datetime_to_jd(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return J2000_JD + (dt - _J2000).total_seconds() / 86400.0


def gmst(jd_ut1: float) -> float:
    """Greenwich mean sidereal time in radians (IAU 1982 model). UT1 is approximated by UTC."""
    T = (jd_ut1 - J2000_JD) / 36525.0
    seconds = 67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * T + 0.093104 * T**2 - 6.2e-6 * T**3
    return (seconds % 86400.0) * (2.0 * np.pi / 86400.0)


def rotate_z(pos: np.ndarray, theta: float) -> np.ndarray:
    """Rotate vectors (N,3) about z. With theta = Greenwich sidereal angle this turns
    inertial coordinates into Earth-fixed ones."""
    c, s = np.cos(theta), np.sin(theta)
    x = pos[:, 0] * c + pos[:, 1] * s
    y = -pos[:, 0] * s + pos[:, 1] * c
    return np.column_stack([x, y, pos[:, 2]])


def eci_to_ecef(pos: np.ndarray, t: float) -> np.ndarray:
    """Simplified rotation for scenarios without an epoch: Earth angle = rotation rate x t."""
    return rotate_z(pos, OMEGA_EARTH * t)


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