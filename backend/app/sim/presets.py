from .failures import KINDS, FailureSchedule

PRESETS = ("none", "plane_outage", "adjacent_planes", "station_loss", "plane_seam_cut")


def _window(t_start: float, duration: float, dt: float) -> tuple[float, float]:
    """Failure from ~25% to ~60% of the run, aligned to tick boundaries."""
    t0 = t_start + round(0.25 * duration / dt) * dt
    t1 = t_start + round(0.60 * duration / dt) * dt
    if t1 <= t0:
        t1 = t0 + dt
    return t0, t1


def preset_failures(preset: str, t_start: float, duration: float, dt: float, c, pairs) -> list[dict]:
    """Failure events (as dicts) for a named scenario. `pairs` is LinkModel.pairs."""
    if preset == "none":
        return []
    t0, t1 = _window(t_start, duration, dt)
    window = {"t_start": t0, "t_end": t1}
    p = min(5, c.n_planes - 2)

    if preset == "plane_outage":
        return [{"kind": "plane", "target": min(5, c.n_planes - 1), **window}]
    if preset == "adjacent_planes":
        return [{"kind": "plane", "target": q, **window} for q in (p, p + 1)]
    if preset == "station_loss":
        return [{"kind": "station", "target": 0, **window}]
    if preset == "plane_seam_cut":
        # remove every cross-plane link between two adjacent planes; no satellites are lost
        return seam_cut(c, pairs, p, t0, t1)
    raise ValueError(f"unknown preset {preset!r}; choose from {PRESETS}")

def seam_cut(c, pairs, p: int, t_start: float, t_end: float | None = None) -> list[dict]:
    """ISL failure events for every cross-plane link between plane p and plane p+1."""
    planes = {p % c.n_planes, (p + 1) % c.n_planes}
    return [{"kind": "isl", "target": [int(a), int(b)], "t_start": t_start, "t_end": t_end}
            for a, b in pairs
            if {int(c.plane[a]), int(c.plane[b])} == planes]


def live_failure_events(msg: dict, t: float, c, pairs, n_stations: int):
    """Validated FailureEvent objects for a live 'fail' command starting at time t."""
    kind = msg.get("kind")
    duration = msg.get("duration")
    t_end = None if duration in (None, 0) else t + float(duration)
    if t_end is not None and t_end <= t:
        raise ValueError("duration must be positive")

    if kind == "seam":
        events = seam_cut(c, pairs, int(msg["target"]), t, t_end)
        if not events:
            raise ValueError("no cross-plane links found for that plane")
    elif kind in KINDS:
        events = [{"kind": kind, "target": msg.get("target"), "t_start": t, "t_end": t_end}]
    else:
        raise ValueError(f"kind must be one of {KINDS + ('seam',)}, got {kind!r}")
    return FailureSchedule.from_dicts(events, c, n_stations).events