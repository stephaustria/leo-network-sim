from collections import Counter

NEAR = {
    "constellation": {"planes": 12, "sats_per_plane": 12, "altitude_km": 1000, "inclination_deg": 55},
    "isl": {"mode": "nearest", "max_degree": 4},
}


def collect_until_done(ws, limit=50):
    frames = []
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == "frame":
            frames.append(m)
        elif m["type"] == "done":
            return frames
        elif m["type"] == "error":
            raise AssertionError(m)
    raise AssertionError("no done message")


def test_nearest_scenario_streams_its_changing_isl_topology(env):
    client, _ = env
    sid = client.post("/scenarios", json={"name": "near", "config": NEAR}).json()["id"]
    with client.websocket_connect(f"/ws/live?scenario_id={sid}") as ws:
        init = ws.receive_json()
        assert init["isl_dynamic"] is True and init["isl_pairs"] == []
        ws.receive_json()
        ws.send_json({"cmd": "start", "dt": 60, "duration": 60, "speed": 20})
        frames = collect_until_done(ws)
    assert frames
    for f in frames:
        degree = Counter(x for pair in f["isl"] for x in pair)
        assert degree and max(degree.values()) <= 4 and max(degree) < 144


def test_replay_recomputes_the_isl_topology(env):
    client, _ = env
    sid = client.post("/scenarios", json={"name": "near", "config": NEAR}).json()["id"]
    run_id = client.post("/runs", json={"scenario_id": sid, "duration": 60}).json()["id"]
    with client.websocket_connect(f"/ws/replay/{run_id}") as ws:
        assert ws.receive_json()["isl_dynamic"] is True
        ws.send_json({"cmd": "speed", "speed": 60})
        frames = collect_until_done(ws)
    assert frames and all(f["isl"] for f in frames)


def test_grid_scenarios_do_not_send_isl_lists(env):
    client, _ = env
    with client.websocket_connect("/ws/live") as ws:
        assert ws.receive_json()["isl_dynamic"] is False
        ws.receive_json()
        ws.send_json({"cmd": "start", "dt": 60, "duration": 60, "speed": 20})
        frames = collect_until_done(ws)
    assert frames and all("isl" not in f for f in frames)


def test_invalid_isl_settings_are_rejected(env):
    client, _ = env

    def post(isl):
        return client.post("/scenarios", json={"name": "x", "config": {"isl": isl}})

    assert post({"mode": "bogus"}).status_code == 422
    assert post({"max_degree": 0}).status_code == 422
    assert post({"inter_shell_degree": 3}).status_code == 422
    assert post({"replan_s": -5}).status_code == 422
    assert post({"replan_s": 4000}).status_code == 422


def test_seam_cut_preset_needs_grid_links(env):
    client, _ = env
    sid = client.post("/scenarios", json={"name": "near", "config": NEAR}).json()["id"]
    r = client.post("/experiments", json={"preset": "plane_seam_cut", "scenario_id": sid,
                                          "duration": 60, "dt": 60})
    assert r.status_code == 422