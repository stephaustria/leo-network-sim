from dataclasses import dataclass

import numpy as np

from .links import GroundLinks


@dataclass
class HandoffEvent:
    t: float
    station: int
    from_sat: int | None
    to_sat: int | None
    reason: str   # acquired | better | lost | outage

    def to_dict(self) -> dict:
        return {"t": self.t, "station": self.station, "from_sat": self.from_sat,
                "to_sat": self.to_sat, "reason": self.reason}

DEFAULT_HYSTERESIS_DEG = 15.0

class ServingTracker:
    """Keeps one serving satellite per station, with hysteresis to avoid flapping."""

    def __init__(self, hysteresis_deg: float = DEFAULT_HYSTERESIS_DEG):
        self.hysteresis_deg = hysteresis_deg
        self.serving: dict[int, int | None] = {}

    def update(self, t: float, ground: GroundLinks, n_stations: int) -> list[HandoffEvent]:
        events: list[HandoffEvent] = []
        for g in range(n_stations):
            m = ground.station == g
            sats, elev = ground.sat[m], ground.elevation_deg[m]
            cur = self.serving.get(g)

            if len(sats) == 0:
                if cur is not None:
                    events.append(HandoffEvent(t, g, cur, None, "outage"))
                self.serving[g] = None
                continue

            best = int(np.argmax(elev))
            best_sat, best_el = int(sats[best]), float(elev[best])

            if cur is not None and np.any(sats == cur):
                if best_sat == cur:
                    continue                      # already on the best satellite
                cur_el = float(elev[sats == cur][0])
                if best_el - cur_el < self.hysteresis_deg:
                    continue                      # keep current satellite
                reason = "better"
            else:
                reason = "lost" if cur is not None else "acquired"

            self.serving[g] = best_sat
            events.append(HandoffEvent(t, g, cur, best_sat, reason))
        return events