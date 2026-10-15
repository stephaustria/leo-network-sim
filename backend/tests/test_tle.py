import math
from datetime import datetime, timezone

import numpy as np
import pytest

from app.sim.constants import R_EARTH
from app.sim.constellation import Constellation, WalkerConfig
from app.sim.coverage import CoverageParams, compute_coverage
from app.sim.frames import datetime_to_jd, gmst, jd_to_datetime, rotate_z
from app.sim.links import LinkModel, build_isl_topology
from app.sim.tle import TleError, TleShell, checksum, format_tle, parse_tle_text, walker_tle_text

NAME = "ISS (ZARYA)"
L1 = "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
L2 = "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482"
ISS = f"{NAME}\n{L1}\n{L2}\n"
EPOCH = datetime(2026, 10, 13, tzinfo=timezone.utc)


def test_checksum_matches_the_published_example():
    assert checksum(L1) == 1 and checksum(L2) == 2


def test_parse_three_line_and_two_line_forms():
    rec = parse_tle_text(ISS)[0]
    assert rec.name == NAME and rec.norad_id == 25544
    assert rec.inclination_deg == pytest.approx(51.6439, abs=1e-3)
    assert rec.mean_motion_rev_day == pytest.approx(15.50103472, abs=1e-6)
    assert (rec.epoch.year, rec.epoch.month, rec.epoch.day) == (2019, 12, 9)

    assert parse_tle_text(f"{L1}\n{L2}\n")[0].name == "NORAD 25544"
    assert len(parse_tle_text(ISS + ISS)) == 2


@pytest.mark.parametrize("text", [
    "",
    "hello world",
    f"{NAME}\n{L1}\n",                                  # missing line 2
    f"{NAME}\n{L1[:-1]}2\n{L2}\n",                      # bad checksum
    f"{NAME}\n{L1[:-3]}\n{L2}\n",                       # wrong length
    f"{NAME}\n{L1}\n{L2.replace('25544', '25545', 1)}\n",   # catalog number changed
])
def test_invalid_tle_text_is_rejected(text):
    with pytest.raises(TleError):
        parse_tle_text(text)


def test_generated_tles_are_valid_and_round_trip():
    l1, l2 = format_tle("TEST", 90001, EPOCH.replace(hour=6), 53.0, 120.5, 0.0001, 0.0, 45.25, 15.05)
    assert len(l1) == len(l2) == 69
    rec = parse_tle_text(f"TEST\n{l1}\n{l2}\n")[0]
    assert rec.norad_id == 90001
    assert rec.inclination_deg == pytest.approx(53.0, abs=1e-4)
    assert rec.mean_motion_rev_day == pytest.approx(15.05, abs=1e-7)
    assert abs((rec.epoch - EPOCH.replace(hour=6)).total_seconds()) < 1.0


def test_time_and_sidereal_helpers():
    j2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    assert datetime_to_jd(j2000) == 2451545.0 and jd_to_datetime(2451545.0) == j2000
    assert datetime_to_jd(EPOCH) == pytest.approx(2461326.5)
    assert gmst(2451545.0) == pytest.approx(math.radians(280.46061837), abs=1e-8)
    advance = (gmst(2451546.0) - gmst(2451545.0)) % (2 * math.pi)       # one UT day of sidereal drift
    assert advance == pytest.approx(math.radians(0.9856473663), abs=1e-6)


def test_sgp4_reproduces_the_iss_orbit():
    shell = TleShell(parse_tle_text(ISS))
    c = Constellation(shell)
    assert c.n_sats == 1 and c.n_planes == 0
    assert c.epoch_jd == pytest.approx(shell.epoch_jd)

    heights, max_lat = [], 0.0
    for t in range(0, 5600, 60):                         # about one orbit
        p = c.positions_eci(t)[0]
        r = np.linalg.norm(p)
        heights.append((r - R_EARTH) / 1000)
        max_lat = max(max_lat, math.degrees(math.asin(p[2] / r)))
    assert all(380 < h < 470 for h in heights)
    assert max_lat == pytest.approx(51.64, abs=0.4)


def test_epoch_changes_the_earth_rotation_for_walker_shells():
    cfg = WalkerConfig(planes=6, sats_per_plane=8)
    j = datetime_to_jd(EPOCH)
    legacy, dated = Constellation(cfg), Constellation(cfg, epoch_jd=j)
    assert legacy.epoch_jd is None
    assert np.allclose(dated.positions_eci(0), legacy.positions_eci(0))
    assert np.allclose(dated.positions_ecef(0), rotate_z(dated.positions_eci(0), gmst(j)))
    assert np.allclose(np.linalg.norm(dated.positions_ecef(100), axis=1), dated.radius)


def test_synthetic_walker_tle_set_matches_the_analytic_shell():
    shell = TleShell(parse_tle_text(walker_tle_text(6, 8, 550.0, 53.0, phasing=1, epoch=EPOCH)))
    tle_c = Constellation(shell)
    walker = Constellation(WalkerConfig(altitude_km=550, inclination_deg=53, planes=6,
                                        sats_per_plane=8, phasing=1))
    assert shell.n_sats == 48 and shell.dropped == 0
    r = np.linalg.norm(tle_c.positions_eci(0), axis=1)
    assert np.all(np.abs(r - walker.radius) < 40_000)                    # within 40 km
    for t in (0.0, 600.0):
        gap = np.linalg.norm(tle_c.positions_eci(t) - walker.positions_eci(t), axis=1)
        assert gap.max() < 90_000, gap.max()                             # SGP4 adds J2 effects


def test_walker_and_tle_shells_in_one_constellation():
    tle = TleShell(parse_tle_text(walker_tle_text(4, 6, 800.0, 60.0, epoch=EPOCH)))
    c = Constellation([WalkerConfig(planes=6, sats_per_plane=8), tle])
    assert c.n_sats == 72 and c.n_planes == 6
    assert (c.plane[48:] == -1).all() and (c.shell_of[48:] == 1).all()
    pairs, _ = build_isl_topology(c)
    assert len(pairs) == 96 and pairs.max() < 48                         # ISLs only inside the Walker shell
    assert c.epoch_jd == pytest.approx(tle.epoch_jd)
    ecef = c.positions_ecef(0)
    assert ecef.shape == (72, 3) and np.isfinite(ecef).all()


def test_a_tle_only_constellation_has_no_isl_pairs():
    pairs, cross = build_isl_topology(Constellation(TleShell(parse_tle_text(ISS))))
    assert pairs.shape == (0, 2) and cross.shape == (0,)


def test_coverage_with_a_tle_shell_matches_the_walker_equivalent():
    tle_model = LinkModel(Constellation(TleShell(parse_tle_text(
        walker_tle_text(6, 8, 550.0, 53.0, epoch=EPOCH)))))
    walker_model = LinkModel(Constellation(WalkerConfig(planes=6, sats_per_plane=8)))
    params = CoverageParams(6.0, 2.0, 180.0)
    a, b = compute_coverage(tle_model, params), compute_coverage(walker_model, params)
    assert abs(a["summary"]["global_mean_visible"] - b["summary"]["global_mean_visible"]) < 0.05
    assert abs(a["summary"]["global_availability"] - b["summary"]["global_availability"]) < 0.1