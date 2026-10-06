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
        return [{"kind": "isl", "target": [int(a), int(b)], **window}
                for a, b in pairs
                if {int(c.plane[a]), int(c.plane[b])} == {p, p + 1}]
    raise ValueError(f"unknown preset {preset!r}; choose from {PRESETS}")