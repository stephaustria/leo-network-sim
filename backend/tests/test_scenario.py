import pytest
from pydantic import ValidationError

from app.sim.engine import Simulation
from app.sim.scenario import ScenarioConfig, build_world, describe


def test_default_scenario_builds_the_current_world():
    model = build_world(ScenarioConfig())
    assert model.c.n_sats == 528 and len(model.stations) == 6
    assert len(model.pairs) == 2 * 528


def test_custom_scenario_builds_and_simulates():
    cfg = ScenarioConfig(
        constellation={"planes": 6, "sats_per_plane": 8, "altitude_km": 800,
                       "inclination_deg": 60, "phasing": 2},
        stations=[{"name": "A", "lat": 0, "lon": 0}, {"name": "B", "lat": 40, "lon": 100}],
        link_params={"ground_capacity_gbps": 50},
    )
    model = build_world(cfg)
    assert model.c.n_sats == 48 and len(model.pairs) == 96
    assert model.params.ground_capacity_gbps == 50.0
    res = Simulation(model).tick(0)
    assert res.metrics["flows_total"] == 1            # two stations -> one pair


@pytest.mark.parametrize("bad", [
    {"constellation": {"planes": 2}},
    {"constellation": {"sats_per_plane": 2}},
    {"constellation": {"planes": 72, "sats_per_plane": 23}},        # 1,656 > 1,600
    {"constellation": {"planes": 6, "phasing": 6}},
    {"constellation": {"altitude_km": 100}},
    {"constellation": {"inclination_deg": 120}},
    {"stations": [{"name": "A", "lat": 0, "lon": 0}]},              # needs two
    {"stations": [{"name": "A", "lat": 0, "lon": 0}, {"name": "a", "lat": 1, "lon": 1}]},
    {"stations": [{"name": "A", "lat": 95, "lon": 0}, {"name": "B", "lat": 1, "lon": 1}]},
    {"link_params": {"bogus": 1}},
    {"flow_demand_gbps": 0},
])
def test_invalid_scenarios_rejected(bad):
    with pytest.raises(ValidationError):
        ScenarioConfig(**bad)


def test_describe_default_scenario():
    d = describe(ScenarioConfig())
    assert d["n_sats"] == 528 and d["n_stations"] == 6 and d["n_flows"] == 15
    assert 94 < d["period_min"] < 97
    assert 1900 < d["intra_plane_spacing_km"] < 2050
    assert 900 < d["footprint_radius_km"] < 1000
    assert 2.5 < d["mean_sats_in_view_estimate"] < 3.3