import numpy as np

from app.sim.constellation import Constellation
from app.sim.links import LinkModel, clear_of_earth
from app.sim.constants import R_EARTH


def make():
    c = Constellation()
    return c, LinkModel(c)


def test_isl_topology_is_4_regular():
    c, m = make()
    deg = np.bincount(m.pairs.ravel(), minlength=c.n_sats)
    assert len(m.pairs) == 2 * c.n_sats
    assert (deg == 4).all()


def test_intra_plane_spacing_matches_chord():
    c, m = make()
    expected_km = 2 * c.radius * np.sin(np.pi / c.per_plane) / 1000
    snap = m.snapshot(0)
    intra = snap.isl.distance_km[~m.is_cross[np.isin(m.pairs[:, 0], snap.isl.a)]]
    assert np.isclose(np.median(intra), expected_km, rtol=0.01)


def test_default_isl_links_all_usable():
    c, m = make()
    for t in (0, 1500, 3000):
        snap = m.snapshot(t)
        assert len(snap.isl.a) == snap.n_isl_candidates
        assert snap.isl.distance_km.max() < 5000


def test_earth_occlusion():
    p1 = np.array([[R_EARTH + 500e3, 0, 0]])
    p2 = np.array([[-(R_EARTH + 500e3), 0, 0]])
    assert not clear_of_earth(p1, p2, 0.0)[0]


def test_ground_coverage_and_min_elevation():
    c, m = make()
    counts = []
    for t in range(0, 6000, 600):
        snap = m.snapshot(t)
        assert (snap.ground.elevation_deg >= m.params.min_elevation_deg).all()
        counts.append(np.bincount(snap.ground.station, minlength=len(m.stations)))
    assert np.mean(counts) > 1.0


def test_ground_latency_bounds():
    _, m = make()
    snap = m.snapshot(0)
    floor = 550e3 / 299_792_458 * 1000 + m.params.node_processing_ms
    assert (snap.ground.latency_ms >= floor - 1e-6).all()
    assert (snap.ground.capacity_gbps <= m.params.ground_capacity_gbps + 1e-9).all()
    assert (snap.ground.loss < 0.05).all()