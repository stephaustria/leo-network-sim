def test_coverage_endpoint(env):
    client, _ = env
    r = client.get("/coverage?res_deg=10&window_hours=2&step_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grid"]["n_lat"] == 18 and d["grid"]["n_lon"] == 36
    for key in ("availability", "mean_visible", "mean_latency_ms", "p95_latency_ms", "longest_gap_min"):
        assert len(d[key]) == 18 * 36
    assert len(d["by_latitude"]) == 18 and len(d["stations"]) == 6
    assert 0 < d["summary"]["global_availability"] < 1


def test_coverage_follows_scenario_id(env):
    client, _ = env
    sid = client.post("/scenarios", json={"name": "small", "config": {
        "constellation": {"planes": 6, "sats_per_plane": 8}}}).json()["id"]
    query = "res_deg=15&window_hours=2&step_s=300"
    small = client.get(f"/coverage?{query}&scenario_id={sid}").json()
    default = client.get(f"/coverage?{query}").json()
    assert small["params"]["n_sats"] == 48 and default["params"]["n_sats"] == 528
    assert small["summary"]["global_availability"] < default["summary"]["global_availability"]


def test_coverage_validation(env):
    client, _ = env
    assert client.get("/coverage?res_deg=7").status_code == 422                       # does not tile
    assert client.get("/coverage?res_deg=1&window_hours=48&step_s=30").status_code == 422   # too heavy
    assert client.get("/coverage?scenario_id=999").status_code == 404

def test_coverage_preview_for_an_unsaved_config(env):
    client, _ = env
    body = {"config": {"constellation": {"planes": 6, "sats_per_plane": 8}},
            "res_deg": 15, "window_hours": 2, "step_s": 300}
    r = client.post("/coverage/preview", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["params"]["n_sats"] == 48

    assert client.post("/coverage/preview",
                       json={"config": {"constellation": {"planes": 2}}}).status_code == 422
    assert client.post("/coverage/preview", json={"res_deg": 7}).status_code == 422
    heavy = {"res_deg": 1, "window_hours": 48, "step_s": 30}
    assert client.post("/coverage/preview", json=heavy).status_code == 422