import pytest

from app.sim.analysis import failure_window, percentile, summarize_arm, tick_goodput
from app.sim.constellation import Constellation
from app.sim.failures import FailureSchedule
from app.sim.links import LinkModel, validate_link_overrides, with_overrides
from app.sim.presets import preset_failures

FAIL = [{"kind": "plane", "target": 5, "t_start": 180, "t_end": 360}]


def params(failures=FAIL, load_scale=1.0):
    return {"dt": 60.0, "load_scale": load_scale, "failures": failures}


def tick(t, delivered, **kw):
    base = {"t": t, "flows_total": 10, "flows_reachable": 10, "delivered_gbps": delivered,
            "delivery_ratio": 1.0, "mean_latency_ms": 50.0, "mean_hops": 10.0,
            "route_changes": 0, "overloaded_links": 0, "max_link_util": 0.1, "handoffs": 0}
    base.update(kw)
    return base


def series(after_recovery=1.5):
    """Offered load is 10 flows x 0.15 Gbps = 1.5 Gbps."""
    out = []
    for t in range(0, 660, 60):
        if t < 180:
            d, lat = 1.5, 50.0
        elif t < 360:
            d, lat = 0.75, 80.0
        elif t < 420:
            d, lat = 1.0, 60.0
        else:
            d, lat = after_recovery, 50.0
        out.append(tick(t, d, mean_latency_ms=lat))
    return out


def test_failure_impact_and_recovery():
    s = summarize_arm(series(), params())
    f = s["failure"]
    assert f["baseline_goodput"] == pytest.approx(1.0)
    assert f["during_goodput"] == pytest.approx(0.5)
    assert f["goodput_drop"] == pytest.approx(0.5)
    assert f["latency_penalty_ms"] == pytest.approx(30.0)
    assert f["recovered"] is True and f["recovery_time_s"] == 60
    assert s["traffic_lost_gbit"] == pytest.approx(165.0)    # 3 x 45 + 30
    assert s["min_goodput"] == pytest.approx(0.5)


def test_never_recovering_is_reported():
    f = summarize_arm(series(after_recovery=0.75), params())["failure"]
    assert f["recovered"] is False and f["recovery_time_s"] is None


def test_permanent_failure_has_no_recovery():
    p = params([{"kind": "satellite", "target": 1, "t_start": 180}])
    f = summarize_arm(series(), p)["failure"]
    assert f["end"] is None and f["recovered"] is None and f["recovery_time_s"] is None


def test_failure_from_the_start_has_no_baseline():
    p = params([{"kind": "satellite", "target": 1, "t_start": 0, "t_end": 120}])
    f = summarize_arm(series(), p)["failure"]
    assert f["baseline_goodput"] is None and f["recovery_time_s"] is None


def test_no_failures_means_no_failure_section():
    assert summarize_arm(series(), params([]))["failure"] is None


def test_zero_load_does_not_divide_by_zero():
    assert tick_goodput(tick(0, 0.0), params(load_scale=0.0)) == 1.0


def test_percentile_and_window():
    assert percentile(list(range(1, 11)), 0.95) == 10
    assert percentile(list(range(1, 11)), 0.5) == 5
    assert failure_window(FAIL) == {"start": 180, "end": 360}
    assert failure_window([{"t_start": 5, "t_end": None}]) == {"start": 5, "end": None}


def test_presets_produce_valid_failures():
    c = Constellation()
    model = LinkModel(c)
    for preset in ("plane_outage", "adjacent_planes", "station_loss", "plane_seam_cut"):
        events = preset_failures(preset, 0.0, 1800.0, 60.0, c, model.pairs)
        assert events
        FailureSchedule.from_dicts(events, c, len(model.stations))     # validates
        assert all(e["t_end"] > e["t_start"] for e in events)
    seam = preset_failures("plane_seam_cut", 0.0, 1800.0, 60.0, c, model.pairs)
    assert len(seam) == c.per_plane                                    # one link per slot
    assert preset_failures("none", 0.0, 1800.0, 60.0, c, model.pairs) == []


def test_link_overrides():
    model = LinkModel(Constellation())
    fast = with_overrides(model, {"ground_capacity_gbps": 50})
    assert fast.params.ground_capacity_gbps == 50.0
    assert fast.c is model.c
    assert with_overrides(model, None) is model
    snap = fast.snapshot(0)
    assert snap.ground.capacity_gbps.max() > 10          # base model caps at 2 Gbps
    with pytest.raises(ValueError):
        validate_link_overrides({"bogus": 1})
    with pytest.raises(ValueError):
        validate_link_overrides({"ground_capacity_gbps": 0})