from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .constants import MU_EARTH, R_EARTH


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
    def period_s(self) -> float:
        return 2 * np.pi / self.mean_motion

    def sat_index(self, plane: int, slot: int) -> int:
        """Shell-local index for (plane, slot), wrapping both around."""
        return (plane % self.n_planes) * self.per_plane + (slot % self.per_plane)

    def positions_eci(self, t: float) -> np.ndarray:
        """ECI positions in meters, shape (n_sats, 3), at t seconds after epoch."""
        u = self.u0 + self.mean_motion * t
        cu, su = np.cos(u), np.sin(u)
        co, so = np.cos(self.raan), np.sin(self.raan)
        ci, si = np.cos(self.inc), np.sin(self.inc)

        x = self.radius * (co * cu - so * ci * su)
        y = self.radius * (so * cu + co * ci * su)
        z = self.radius * (si * su)
        return np.column_stack([x, y, z])


class Constellation:
    """One or more Walker shells. Satellites are numbered shell by shell.

    Single-shell attributes (cfg, per_plane, radius, period_s, mean_motion, sat_index)
    describe the FIRST shell, so code written for one shell keeps working.
    `plane` holds global plane ids: shell 0's planes first, then shell 1's, and so on.
    """

    def __init__(self, shells: WalkerConfig | Sequence[WalkerConfig] = WalkerConfig()):
        configs = [shells] if isinstance(shells, WalkerConfig) else list(shells)
        if not configs:
            raise ValueError("a constellation needs at least one shell")

        self.shells: list[Shell] = []
        sat_offset = plane_offset = 0
        for i, cfg in enumerate(configs):
            shell = Shell(cfg, i, sat_offset, plane_offset)
            self.shells.append(shell)
            sat_offset += shell.n_sats
            plane_offset += shell.n_planes

        self.n_sats = sat_offset
        self.n_planes = plane_offset                       # total planes across all shells
        self.plane = np.concatenate([s.plane_local + s.plane_offset for s in self.shells])
        self.slot = np.concatenate([s.slot for s in self.shells])
        self.shell_of = np.concatenate([np.full(s.n_sats, s.index) for s in self.shells])

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

    # ----- multi-shell helpers -----
    def shell_of_plane(self, plane: int) -> Shell:
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
        """ECI positions in meters, shape (N, 3), at t seconds after epoch."""
        return np.concatenate([s.positions_eci(t) for s in self.shells])

    def positions_ecef(self, t: float) -> np.ndarray:
        from .frames import eci_to_ecef
        return eci_to_ecef(self.positions_eci(t), t)