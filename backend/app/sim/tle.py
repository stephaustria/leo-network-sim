import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sgp4.api import Satrec, SatrecArray

from .constants import MU_EARTH, R_EARTH
from .frames import jd_to_datetime

PROBE_DAYS = (0.0, 2.0)      # satellites SGP4 cannot propagate this far are dropped
MIN_RADIUS_M = 6.4e6         # below this a "satellite" has decayed into the Earth


class TleError(ValueError):
    """A TLE problem the user can fix (bad checksum, wrong length, ...)."""


def checksum(line: str) -> int:
    """TLE checksum: digits count as their value, '-' counts as 1, over the first 68 characters."""
    total = 0
    for ch in line[:68]:
        if "0" <= ch <= "9":
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10


@dataclass(frozen=True)
class TleRecord:
    name: str
    line1: str
    line2: str
    norad_id: int
    epoch_jd: float
    inclination_deg: float
    mean_motion_rev_day: float

    @property
    def epoch(self) -> datetime:
        return jd_to_datetime(self.epoch_jd)


def _make_record(name: str, line1: str, line2: str) -> TleRecord:
    for label, line in (("line 1", line1), ("line 2", line2)):
        if len(line) != 69:
            raise TleError(f"{name}: {label} must be 69 characters long (got {len(line)})")
        if not ("0" <= line[68] <= "9") or int(line[68]) != checksum(line):
            raise TleError(f"{name}: bad checksum on {label}")
    if line1[2:7] != line2[2:7]:
        raise TleError(f"{name}: catalog numbers on line 1 and line 2 differ")
    try:
        sat = Satrec.twoline2rv(line1, line2)
    except (ValueError, TypeError) as exc:
        raise TleError(f"{name}: could not parse the elements ({exc})") from exc
    if sat.error != 0:
        raise TleError(f"{name}: SGP4 rejected the elements (error code {sat.error})")
    return TleRecord(
        name=name, line1=line1, line2=line2, norad_id=int(sat.satnum),
        epoch_jd=float(sat.jdsatepoch + sat.jdsatepochF),
        inclination_deg=math.degrees(sat.inclo),
        mean_motion_rev_day=sat.no_kozai * 1440.0 / (2.0 * math.pi),
    )


def parse_tle_text(text: str) -> list[TleRecord]:
    """Parse 2-line or 3-line (name + 2 lines) TLE text. Raises TleError on the first problem."""
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n") if ln.strip()]
    records: list[TleRecord] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            line1, line2 = lines[i], lines[i + 1]
            name = f"NORAD {line1[2:7].strip()}"
            i += 2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name = lines[i].strip()
            if name.startswith("0 "):                      # Space-Track 3LE style
                name = name[2:].strip()
            line1, line2 = lines[i + 1], lines[i + 2]
            i += 3
        else:
            raise TleError(
                f"line {i + 1}: expected a satellite name followed by TLE lines starting '1 ' and '2 '")
        records.append(_make_record(name, line1, line2))
    if not records:
        raise TleError("no TLE data found")
    return records


def normalize_tle_text(records: list[TleRecord]) -> str:
    return "".join(f"{r.name}\n{r.line1}\n{r.line2}\n" for r in records)


def _propagate(array: SatrecArray, totals: np.ndarray):
    """SGP4 at Julian dates `totals`. Returns (error codes (n,k), TEME positions in meters (n,k,3))."""
    jd = np.floor(totals - 0.5) + 0.5
    fr = totals - jd
    e, r, _ = array.sgp4(jd, fr)
    return np.asarray(e), np.asarray(r) * 1000.0


class TleShell:
    """Real satellites propagated with SGP4. Same interface as a Walker `Shell`, but altitudes
    differ per satellite and there are no orbital planes (plane id and slot are -1)."""

    kind = "tle"
    uniform_radius = False

    def __init__(self, records: list[TleRecord], name: str = "TLE"):
        if not records:
            raise TleError("a TLE shell needs at least one satellite")
        satrecs = [Satrec.twoline2rv(r.line1, r.line2) for r in records]
        epoch = float(np.median([r.epoch_jd for r in records]))

        # drop satellites SGP4 cannot propagate over the probe window (decayed, bad elements)
        e, pos = _propagate(SatrecArray(satrecs), epoch + np.array(PROBE_DAYS))
        radius = np.linalg.norm(pos, axis=2)
        ok = (e == 0).all(axis=1) & np.isfinite(pos).all(axis=(1, 2)) & (radius > MIN_RADIUS_M).all(axis=1)
        if not ok.any():
            raise TleError("SGP4 could not propagate any satellite of this set")

        self.records = [r for r, keep in zip(records, ok) if keep]
        self.dropped = int(len(records) - ok.sum())
        self._array = SatrecArray([s for s, keep in zip(satrecs, ok) if keep])
        self._fallback = pos[ok, 0, :]                      # epoch positions, used if SGP4 fails later

        self.name = name
        self.epoch_jd = epoch
        self.n_sats = len(self.records)
        self.n_planes = 0
        self.per_plane = 0
        self.plane_ids = np.full(self.n_sats, -1)
        self.slot = np.full(self.n_sats, -1)
        self.names = [r.name for r in self.records]
        self.norad_ids = [r.norad_id for r in self.records]

        n = np.array([r.mean_motion_rev_day for r in self.records]) * 2 * np.pi / 86400.0   # rad/s
        a = (MU_EARTH / n**2) ** (1.0 / 3.0)
        self.altitude_km = float((a.mean() - R_EARTH) / 1000.0)
        self.radius = R_EARTH + self.altitude_km * 1000.0
        self.period_s = float(np.mean(2 * np.pi / n))
        self.inclination_deg = float(np.mean([r.inclination_deg for r in self.records]))

        self.index = 0
        self.offset = 0
        self.plane_offset = 0

    def place(self, index: int, offset: int, plane_offset: int) -> "TleShell":
        self.index, self.offset, self.plane_offset = index, offset, plane_offset
        return self

    def positions_eci(self, t: float, epoch_jd: float) -> np.ndarray:
        """TEME positions in meters at t seconds after the scenario epoch."""
        e, r = _propagate(self._array, np.array([epoch_jd + t / 86400.0]))
        pos = r[:, 0, :]
        bad = (e[:, 0] != 0) | ~np.isfinite(pos).all(axis=1)
        if bad.any():
            pos = pos.copy()
            pos[bad] = self._fallback[bad]
        return pos

    def summary(self) -> dict:
        return {
            "kind": "tle", "index": self.index, "name": self.name, "n_sats": self.n_sats,
            "offset": self.offset, "planes": 0, "plane_offset": self.plane_offset,
            "sats_per_plane": None, "altitude_km": round(self.altitude_km, 1),
            "inclination_deg": round(self.inclination_deg, 2),
            "period_min": round(self.period_s / 60, 2),
            "epoch": jd_to_datetime(self.epoch_jd).isoformat(), "dropped": self.dropped,
        }


# ------------------------------------------------------------------ synthetic TLEs

def format_tle(name: str, norad: int, epoch: datetime, inc: float, raan: float, ecc: float,
               argp: float, mean_anomaly: float, mean_motion: float, elset: int = 1) -> tuple[str, str]:
    """Build a valid TLE line pair from orbital elements (drag terms are zero).
    Angles in degrees, mean motion in revolutions per day."""
    ep = epoch.astimezone(timezone.utc) if epoch.tzinfo else epoch.replace(tzinfo=timezone.utc)
    day = (ep - datetime(ep.year, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400.0 + 1.0
    body1 = (f"1 {norad:05d}U 00000A   {ep.year % 100:02d}{day:012.8f}"
             f"  .00000000  00000-0  00000-0 0 {elset:4d}")
    body2 = (f"2 {norad:05d} {inc % 360:8.4f} {raan % 360:8.4f} {round(ecc * 1e7):07d} "
             f"{argp % 360:8.4f} {mean_anomaly % 360:8.4f} {mean_motion:11.8f}{1:5d}")
    assert len(body1) == 68 and len(body2) == 68, (len(body1), len(body2))
    return body1 + str(checksum(body1)), body2 + str(checksum(body2))


def walker_tle_text(planes: int, sats_per_plane: int, altitude_km: float, inclination_deg: float,
                    phasing: int = 1, epoch: datetime | None = None, name_prefix: str = "WALKER") -> str:
    """TLE text for a Walker Delta shell, using the same phasing rule as the analytic shell."""
    epoch = epoch or datetime(2026, 10, 13, tzinfo=timezone.utc)
    a = R_EARTH + altitude_km * 1000.0
    rev_per_day = math.sqrt(MU_EARTH / a**3) * 86400.0 / (2 * math.pi)
    total = planes * sats_per_plane
    out = []
    for p in range(planes):
        for s in range(sats_per_plane):
            k = p * sats_per_plane + s
            name = f"{name_prefix}-{p:02d}-{s:02d}"
            raan = 360.0 * p / planes
            anomaly = 360.0 * s / sats_per_plane + 360.0 * phasing * p / total
            l1, l2 = format_tle(name, 90000 + k, epoch, inclination_deg, raan, 0.0001, 0.0,
                                anomaly, rev_per_day)
            out += [name, l1, l2]
    return "\n".join(out) + "\n"