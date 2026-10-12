from app.sim.scenario import ScenarioConfig
from app.sim.worlds import get_world, world_for_params

SMALL = {
    "constellation": {"planes": 6, "sats_per_plane": 8},
    "stations": [{"name": "A", "lat": 0, "lon": 0}, {"name": "B", "lat": 40, "lon": 100},
                 {"name": "C", "lat": -30, "lon": 20}],
    "flow_demand_gbps": 0.3,
}


def test_worlds_are_cached_per_config():
    a = get_world(ScenarioConfig(**SMALL))
    b = get_world(ScenarioConfig(**SMALL))
    assert a is b
    assert a is not get_world(ScenarioConfig())


def test_world_flows_follow_the_scenario():
    flows = get_world(ScenarioConfig(**SMALL)).flows()
    assert len(flows) == 3 and all(f.demand_gbps == 0.3 for f in flows)


def test_world_for_params():
    assert world_for_params({}).model.c.n_sats == 528             # runs from before B2: default
    p = {"scenario": {"id": 1, "name": "small", "config": ScenarioConfig(**SMALL).model_dump()}}
    base = world_for_params(p)
    assert base.model.c.n_sats == 48

    tuned = world_for_params({**p, "link_params": {"ground_capacity_gbps": 50}})
    assert tuned.model.params.ground_capacity_gbps == 50.0
    assert tuned.model.c is base.model.c                          # constellation is shared