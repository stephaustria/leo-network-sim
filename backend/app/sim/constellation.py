from dataclasses import dataclass

import numpy as np

from .constants import MU_EARTH, R_EARTH


@dataclass(frozen=True)
class WalkerConfig:
    altitude_km: float = 550.0
    inclination_deg: float = 53.0
    planes: int = 24
    sats_per_plane: int = 22
    phasing: int = 1  # Walker "F" parameter


class Constellation:
    """Walker Delta constellation on circular orbits."""

    def __init__(self, cfg: WalkerConfig = WalkerConfig()):
        self.cfg = cfg
        self.n_planes = cfg.planes
        self.per_plane = cfg.sats_per_plane
        self.n_sats = cfg.planes * cfg.sats_per_plane

        self.radius = R_EARTH + cfg.altitude_km * 1000.0
        self.mean_motion = np.sqrt(MU_EARTH / self.radius**3)  # rad/s
        self.inc = np.radians(cfg.inclination_deg)

        idx = np.arange(self.n_sats)
        self.plane = idx // self.per_plane
        self.slot = idx % self.per_plane

        self.raan = 2 * np.pi * self.plane / self.n_planes
        self.u0 = (
            2 * np.pi * self.slot / self.per_plane
            + 2 * np.pi * cfg.phasing * self.plane / self.n_sats
        )

    @property
    def period_s(self) -> float:
        return 2 * np.pi / self.mean_motion

    def sat_index(self, plane: int, slot: int) -> int:
        """Index for (plane, slot), wrapping both around."""
        return (plane % self.n_planes) * self.per_plane + (slot % self.per_plane)

    def positions_eci(self, t: float) -> np.ndarray:
        """ECI positions in meters, shape (N, 3), at t seconds after epoch."""
        u = self.u0 + self.mean_motion * t
        cu, su = np.cos(u), np.sin(u)
        co, so = np.cos(self.raan), np.sin(self.raan)
        ci, si = np.cos(self.inc), np.sin(self.inc)

        x = self.radius * (co * cu - so * ci * su)
        y = self.radius * (so * cu + co * ci * su)
        z = self.radius * (si * su)
        return np.column_stack([x, y, z])

    def positions_ecef(self, t: float) -> np.ndarray:
        from .frames import eci_to_ecef
        return eci_to_ecef(self.positions_eci(t), t)