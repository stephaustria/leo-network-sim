def make_experiment(client, **overrides):
    body = {
        "name": "test", "preset": "plane_outage", "duration": 240, "dt": 60, "load_scale": 2.0,
        "arms": [{"policy": "min_hop"},
                 {"policy": "congestion_aware", "route_stickiness": 0.1}],
        **overrides,
    }
    r = client.post("/experiments", json=body)
    assert r.status_code == 202, r.text
    return r.json()


def test_experiment_lifecycle(env):
    client, _ = env
    exp = make_experiment(client)
    exp_id = exp["experiment_id"]
    assert len(exp["runs"]) == 2 and exp["ticks_per_run"] == 5

    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["status"] == "completed"
    assert detail["failure_window"] == {"start": 60, "end": 120}
    assert [a["label"] for a in detail["arms"]] == ["min_hop", "congestion_aware + stickiness 0.1"]
    for arm in detail["arms"]:
        s = arm["summary"]
        assert s["ticks"] == 5 and 0 <= s["mean_goodput"] <= 1
        assert s["failure"]["start"] == 60

    tl = client.get(f"/experiments/{exp_id}/timelines?metrics=goodput,mean_hops").json()
    assert tl["metrics"] == ["goodput", "mean_hops"]
    assert len(tl["arms"]) == 2
    for arm in tl["arms"]:
        assert len(arm["series"]) == 5
        assert set(arm["series"][0]) == {"t", "goodput", "mean_hops"}
    assert client.get(f"/experiments/{exp_id}/timelines?metrics=bogus").status_code == 422

    listing = client.get("/experiments").json()
    assert listing[0]["id"] == exp_id and listing[0]["status"] == "completed"

    assert client.delete(f"/experiments/{exp_id}").status_code == 204
    assert client.get(f"/experiments/{exp_id}").status_code == 404
    assert client.get(f"/runs/{exp['runs'][0]}").status_code == 404


def test_experiment_validation(env):
    client, _ = env
    one_arm = {"arms": [{"policy": "min_hop"}]}
    assert client.post("/experiments", json=one_arm).status_code == 422
    bad_failure = {"failures": [{"kind": "station", "target": 99}]}
    assert client.post("/experiments", json=bad_failure).status_code == 422
    assert client.post("/experiments", json={"link_params": {"bogus": 1}}).status_code == 422
    assert client.post("/experiments", json={"duration": 7200, "dt": 10}).status_code == 422

def test_arm_hysteresis_option(env):
    client, _ = env
    exp = make_experiment(client, preset="none", duration=120, arms=[
        {"policy": "min_hop", "hysteresis_deg": 5},
        {"policy": "min_hop", "hysteresis_deg": 40}])
    detail = client.get(f"/experiments/{exp['experiment_id']}").json()
    assert [a["label"] for a in detail["arms"]] == ["min_hop + hysteresis 5°", "min_hop + hysteresis 40°"]
    assert [a["hysteresis_deg"] for a in detail["arms"]] == [5, 40]
    run = client.get(f"/runs/{exp['runs'][0]}").json()
    assert run["params"]["hysteresis_deg"] == 5