from dataclasses import dataclass, field, fields

import numpy as np

from .links import LinkSnapshot

KINDS = ("satellite", "plane", "station", "isl")


@dataclass
class FailureEvent:
    kind: str                              # satellite | plane | station | isl
    target: int | tuple[int, int]          # index, or (sat_a, sat_b) for isl
    t_start: float = 0.0
    t_end: float | None = None             # None = never recovers

    def active(self, t: float) -> bool:
        return self.t_start <= t and (self.t_end is None or t < self.t_end)

    def to_dict(self) -> dict:
        target = list(self.target) if isinstance(self.target, tuple) else self.target
        return {"kind": self.kind, "target": target, "t_start": self.t_start, "t_end": self.t_end}

    @classmethod
    def from_dict(cls, d: dict) -> "FailureEvent":
        kind = d.get("kind")
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        try:
            if kind == "isl":
                tgt = d.get("target")
                if not isinstance(tgt, (list, tuple)) or len(tgt) != 2:
                    raise ValueError("isl target must be [sat_a, sat_b]")
                target: int | tuple[int, int] = tuple(sorted(int(x) for x in tgt))
            else:
                target = int(d["target"])
            t_start = float(d.get("t_start", 0.0))
            t_end = d.get("t_end")
            t_end = None if t_end is None else float(t_end)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid failure event {d!r}: {exc}") from exc
        if t_end is not None and t_end <= t_start:
            raise ValueError("t_end must be after t_start")
        return cls(kind, target, t_start, t_end)


@dataclass
class FailureState:
    """Everything that is down at one instant."""
    sats: set[int] = field(default_factory=set)
    stations: set[int] = field(default_factory=set)
    isls: set[tuple[int, int]] = field(default_factory=set)

    @property
    def any(self) -> bool:
        return bool(self.sats or self.stations or self.isls)

    def to_dict(self) -> dict:
        return {"sats": sorted(self.sats), "stations": sorted(self.stations),
                "isls": [list(p) for p in sorted(self.isls)]}


class FailureSchedule:
    def __init__(self, events: list[FailureEvent] | None = None):
        self.events: list[FailureEvent] = list(events or [])

    @classmethod
    def from_dicts(cls, items, constellation=None, n_stations: int | None = None):
        sched = cls([FailureEvent.from_dict(d) for d in (items or [])])
        if constellation is not None:
            sched.validate(constellation, n_stations or 0)
        return sched

    def validate(self, c, n_stations: int) -> None:
        for e in self.events:
            if e.kind == "satellite" and not 0 <= e.target < c.n_sats:
                raise ValueError(f"satellite {e.target} out of range (0..{c.n_sats - 1})")
            if e.kind == "plane" and not 0 <= e.target < c.n_planes:
                raise ValueError(f"plane {e.target} out of range (0..{c.n_planes - 1})")
            if e.kind == "station" and not 0 <= e.target < n_stations:
                raise ValueError(f"station {e.target} out of range (0..{n_stations - 1})")
            if e.kind == "isl":
                a, b = e.target
                if a == b or not (0 <= a < c.n_sats and 0 <= b < c.n_sats):
                    raise ValueError(f"invalid isl target {e.target}")

    def add(self, event: FailureEvent) -> None:
        self.events.append(event)

    def recover_all(self, t: float) -> None:
        """End every failure that is active at time t (even ones with a later t_end)."""
        for e in self.events:
            if e.active(t):
                e.t_end = t

    def active_at(self, t: float, c) -> FailureState:
        state = FailureState()
        for e in self.events:
            if not e.active(t):
                continue
            if e.kind == "satellite":
                state.sats.add(e.target)
            elif e.kind == "plane":
                state.sats.update(range(e.target * c.per_plane, (e.target + 1) * c.per_plane))
            elif e.kind == "station":
                state.stations.add(e.target)
            else:
                state.isls.add(e.target)
        return state

    def to_dicts(self) -> list[dict]:
        return [e.to_dict() for e in self.events]


def _mask(obj, keep: np.ndarray):
    return type(obj)(**{f.name: getattr(obj, f.name)[keep] for f in fields(obj)})


def apply_failures(snap: LinkSnapshot, state: FailureState, n_sats: int) -> LinkSnapshot:
    """Return a copy of the link snapshot with failed links removed."""
    if not state.any:
        return snap

    isl, gl = snap.isl, snap.ground
    sats = np.array(sorted(state.sats), dtype=np.int64)
    stations = np.array(sorted(state.stations), dtype=np.int64)
    bad_keys = np.array([a * n_sats + b for a, b in sorted(state.isls)], dtype=np.int64)

    keys = isl.a.astype(np.int64) * n_sats + isl.b
    isl_keep = ~(np.isin(isl.a, sats) | np.isin(isl.b, sats) | np.isin(keys, bad_keys))
    gl_keep = ~(np.isin(gl.sat, sats) | np.isin(gl.station, stations))

    return LinkSnapshot(t=snap.t, n_isl_candidates=snap.n_isl_candidates,
                        isl=_mask(isl, isl_keep), ground=_mask(gl, gl_keep))