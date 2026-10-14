SCEN = {
    "constellation": {"planes": 6, "sats_per_plane": 8, "altitude_km": 550},
    "extra_shells": [{"planes": 4, "sats_per_plane": 6, "altitude_km": 1100, "inclination_deg": 70}],
}


def test_two_shell_scenario_end_to_end(env):
    client, _ = env
    r = client.post("/scenarios", json={"name": "two shells", "config": SCEN})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["n_sats"] == 72 and r.json()["summary"]["n_sats"] == 72

    info = client.get(f"/constellation/info?scenario_id={sid}").json()
    assert info["n_sats"] == 72 and info["planes"] == 10 and len(info["shells"]) == 2
    sats = client.get(f"/constellation/positions?scenario_id={sid}&t=0").json()["satellites"]
    assert {s["shell"] for s in sats} == {0, 1}

    ok = client.post("/runs", json={"scenario_id": sid, "duration": 60,
                                    "failures": [{"kind": "plane", "target": 7}]})   # plane of shell 2
    assert ok.status_code == 202, ok.text
    assert client.get(f"/runs/{ok.json()['id']}").json()["status"] == "completed"
    bad = client.post("/runs", json={"scenario_id": sid, "failures": [{"kind": "plane", "target": 10}]})
    assert bad.status_code == 422

    with client.websocket_connect(f"/ws/live?scenario_id={sid}") as ws:
        init = ws.receive_json()
        assert init["constellation"]["n_sats"] == 72
        assert len(init["constellation"]["shells"]) == 2