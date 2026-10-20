from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .constants import MU_EARTH, R_EARTH
from .frames import eci_to_ecef, gmst, jd_to_datetime, rotate_z


@dataclass(frozen=True)
class WalkerConfig:
    altitude_km: float = 550.0
    inclination_deg: float = 53.0
    planes: int = 24
    sats_per_plane: int = 22
    phasing: int = 1  # Walker "F" parameter


class Shell:
    """One Walker Delta shell on circular orbits.

    Satellite k of the shell has local index k = plane * sats_per_plane + slot.
    `offset` is the global index of the shell's first satellite and `plane_offset`
    the global id of its first plane.
    """

    kind = "walker"
    uniform_radius = True            # every satellite shares one altitude

    def __init__(self, cfg: WalkerConfig, index: int = 0, offset: int = 0, plane_offset: int = 0):
        self.cfg = cfg
        self.index = index
        self.offset = offset
        self.plane_offset = plane_offset
        self.n_planes = cfg.planes
        self.per_plane = cfg.sats_per_plane
        self.n_sats = cfg.planes * cfg.sats_per_plane

        self.radius = R_EARTH + cfg.altitude_km * 1000.0
        self.mean_motion = np.sqrt(MU_EARTH / self.radius**3)  # rad/s
        self.inc = np.radians(cfg.inclination_deg)

        idx = np.arange(self.n_sats)
        self.plane_local = idx // self.per_plane
        self.slot = idx % self.per_plane
        self.raan = 2 * np.pi * self.plane_local / self.n_planes
        self.u0 = (
            2 * np.pi * self.slot / self.per_plane
            + 2 * np.pi * cfg.phasing * self.plane_local / self.n_sats
        )

    @property
    def plane_ids(self) -> np.ndarray:
        return self.plane_local + self.plane_offset

    @property
    def period_s(self) -> float:
        return 2 * np.pi / self.mean_motion

    def sat_index(self, plane: int, slot: int) -> int:
        """Shell-local index for (plane, slot), wrapping both around."""
        return (plane % self.n_planes) * self.per_plane + (slot % self.per_plane)

    def positions_eci(self, t: float, epoch_jd: float | None = None) -> np.ndarray:
        """ECI positions in meters, shape (n_sats, 3), at t seconds after epoch."""
        u = self.u0 + self.mean_motion * t
        cu, su = np.cos(u), np.sin(u)
        co, so = np.cos(self.raan), np.sin(self.raan)
        ci, si = np.cos(self.inc), np.sin(self.inc)

        x = self.radius * (co * cu - so * ci * su)
        y = self.radius * (so * cu + co * ci * su)
        z = self.radius * (si * su)
        return np.column_stack([x, y, z])

    def summary(self) -> dict:
        return {
            "kind": "walker", "index": self.index, "n_sats": self.n_sats, "offset": self.offset,
            "planes": self.n_planes, "plane_offset": self.plane_offset,
            "sats_per_plane": self.per_plane, "altitude_km": self.cfg.altitude_km,
            "inclination_deg": self.cfg.inclination_deg,
            "period_min": round(float(self.period_s) / 60, 2),
        }


class Constellation:
    """Walker shells and/or TLE shells. Satellites are numbered shell by shell.

    Single-shell attributes (cfg, per_plane, radius, period_s, mean_motion, sat_index)
    describe the FIRST shell and need it to be a Walker shell, which keeps code written
    for one shell working. `plane` holds global plane ids (-1 for TLE satellites).

    `epoch_jd` is the Julian date of simulation time 0. Without it, Earth's rotation angle is
    rate x t (the simplified model). With it, the angle is the real sidereal time. A TLE shell
    needs an epoch, and defaults to the shell's own median TLE epoch.
    """

    def __init__(self, shells=WalkerConfig(), epoch_jd: float | None = None):
        single = isinstance(shells, WalkerConfig) or hasattr(shells, "positions_eci")
        items = [shells] if single else list(shells)
        if not items:
            raise ValueError("a constellation needs at least one shell")

        self.shells: list = []
        sat_offset = plane_offset = 0
        for i, item in enumerate(items):
            if isinstance(item, WalkerConfig):
                shell = Shell(item, i, sat_offset, plane_offset)
            else:
                shell = item.place(i, sat_offset, plane_offset)
            self.shells.append(shell)
            sat_offset += shell.n_sats
            plane_offset += shell.n_planes

        self.n_sats = sat_offset
        self.n_planes = plane_offset                       # total planes across Walker shells
        self.plane = np.concatenate([s.plane_ids for s in self.shells])
        self.slot = np.concatenate([s.slot for s in self.shells])
        self.shell_of = np.concatenate([np.full(s.n_sats, s.index) for s in self.shells])

        tle_epochs = [s.epoch_jd for s in self.shells if s.kind == "tle"]
        self.epoch_jd = epoch_jd if epoch_jd is not None else (tle_epochs[0] if tle_epochs else None)

    # ----- first-shell views (backward compatible) -----
    @property
    def cfg(self) -> WalkerConfig:
        return self.shells[0].cfg

    @property
    def per_plane(self) -> int:
        return self.shells[0].per_plane

    @property
    def radius(self) -> float:
        return self.shells[0].radius

    @property
    def mean_motion(self) -> float:
        return self.shells[0].mean_motion

    @property
    def period_s(self) -> float:
        return self.shells[0].period_s

    def sat_index(self, plane: int, slot: int) -> int:
        return self.shells[0].sat_index(plane, slot)

    @property
    def epoch(self):
        return None if self.epoch_jd is None else jd_to_datetime(self.epoch_jd)

    # ----- multi-shell helpers -----
    def shell_of_plane(self, plane: int):
        for shell in self.shells:
            if shell.plane_offset <= plane < shell.plane_offset + shell.n_planes:
                return shell
        raise ValueError(f"plane {plane} out of range (0..{self.n_planes - 1})")

    def sats_in_plane(self, plane: int) -> np.ndarray:
        """Global satellite indices of one plane (global plane id)."""
        return np.nonzero(self.plane == plane)[0]

    def next_plane(self, plane: int) -> int:
        """Global id of the neighbouring plane in the same shell, wrapping inside the shell."""
        shell = self.shell_of_plane(plane)
        local = (plane - shell.plane_offset + 1) % shell.n_planes
        return shell.plane_offset + local

    # ----- positions -----
    def positions_eci(self, t: float) -> np.ndarray:
        """Inertial positions in meters, shape (N, 3), at t seconds after the epoch."""
        return np.concatenate([s.positions_eci(t, self.epoch_jd) for s in self.shells])

    def positions_ecef(self, t: float) -> np.ndarray:
        eci = self.positions_eci(t)
        if self.epoch_jd is None:
            return eci_to_ecef(eci, t)
        return rotate_z(eci, gmst(self.epoch_jd + t / 86400.0))