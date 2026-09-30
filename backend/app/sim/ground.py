from dataclasses import dataclass

import numpy as np

from .frames import geodetic_to_ecef


@dataclass(frozen=True)
class GroundStation:
    name: str
    lat: float
    lon: float


DEFAULT_STATIONS = [
    GroundStation("San Francisco", 37.77, -122.42),
    GroundStation("London", 51.51, -0.13),
    GroundStation("Tokyo", 35.68, 139.69),
    GroundStation("Sydney", -33.87, 151.21),
    GroundStation("Sao Paulo", -23.55, -46.63),
    GroundStation("Johannesburg", -26.20, 28.05),
]


def stations_ecef(stations=DEFAULT_STATIONS) -> np.ndarray:
    lat = np.array([s.lat for s in stations])
    lon = np.array([s.lon for s in stations])
    return geodetic_to_ecef(lat, lon)