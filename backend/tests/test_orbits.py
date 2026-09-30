import numpy as np

from app.sim.constants import R_EARTH
from app.sim.constellation import Constellation
from app.sim.frames import eci_to_ecef, geodetic_to_ecef


def test_constant_radius():
    c = Constellation()
    for t in (0, 1000, 5000):
        r = np.linalg.norm(c.positions_eci(t), axis=1)
        assert np.allclose(r, c.radius)


def test_period_is_realistic_for_550km():
    assert 94 < Constellation().period_s / 60 < 97


def test_returns_to_start_after_one_period():
    c = Constellation()
    assert np.allclose(c.positions_eci(0), c.positions_eci(c.period_s), atol=1.0)


def test_max_latitude_matches_inclination():
    c = Constellation()
    z_max = max(c.positions_eci(t)[:, 2].max() for t in np.linspace(0, c.period_s, 200))
    lat_max = np.degrees(np.arcsin(z_max / c.radius))
    assert abs(lat_max - 53.0) < 0.5


def test_ecef_rotation_preserves_radius():
    c = Constellation()
    ecef = eci_to_ecef(c.positions_eci(3000), 3000)
    assert np.allclose(np.linalg.norm(ecef, axis=1), c.radius)


def test_ground_station_on_surface():
    p = geodetic_to_ecef(37.77, -122.42)
    assert abs(np.linalg.norm(p) - R_EARTH) < 1.0