import pytest
from starlette.websockets import WebSocketDisconnect

SMALL = {
    "constellation": {"planes": 6, "sats_per_plane": 8},
    "stations": [{"name": "A", "lat": 0, "lon": 0}, {"name": "B", "lat": 40, "lon": 100},
                 {"name": "C", "lat": -30, "lon": 20}],
}


def make_scenario(client, name="small", **cfg):
    r = client.post("/scenarios", json={"name": name, "config": {**SMALL, **cfg}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


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


def test_run_uses_and_snapshots_its_scenario(env):
    client, _ = env
    sid = make_scenario(client)
    r = client.post("/runs", json={"duration": 120, "dt": 60, "scenario_id": sid})
    assert r.status_code == 202, r.text
    run_id = r.json()["id"]

    run = client.get(f"/runs/{run_id}").json()
    assert run["status"] == "completed"
    assert run["params"]["scenario"]["name"] == "small"
    assert run["params"]["scenario"]["config"]["constellation"]["planes"] == 6
    timeline = client.get(f"/runs/{run_id}/timeline").json()
    assert all(row["flows_total"] == 3 for row in timeline)          # 3 stations -> 3 pairs

    # editing the scenario afterwards must not change the stored run
    changed = {**SMALL, "constellation": {"planes": 8, "sats_per_plane": 8}}
    assert client.put(f"/scenarios/{sid}", json={"name": "small", "config": changed}).status_code == 200
    again = client.get(f"/runs/{run_id}").json()
    assert again["params"]["scenario"]["config"]["constellation"]["planes"] == 6


def test_run_scenario_errors(env):
    client, _ = env
    assert client.post("/runs", json={"scenario_id": 999}).status_code == 404

    sid = make_scenario(client)
    bad = {"scenario_id": sid, "failures": [{"kind": "plane", "target": 10}]}   # scenario has 6 planes
    assert client.post("/runs", json=bad).status_code == 422
    ok = {"duration": 60, "failures": [{"kind": "plane", "target": 10}]}         # default has 24
    assert client.post("/runs", json=ok).status_code == 202


def test_experiment_on_a_scenario(env):
    client, _ = env
    sid = make_scenario(client)
    r = client.post("/experiments", json={
        "name": "small world", "preset": "plane_outage", "duration": 120, "dt": 60,
        "load_scale": 2, "scenario_id": sid,
        "arms": [{"policy": "min_hop"}, {"policy": "congestion_aware"}]})
    assert r.status_code == 202, r.text

    detail = client.get(f"/experiments/{r.json()['experiment_id']}").json()
    assert detail["status"] == "completed"
    assert detail["scenario"]["name"] == "small"
    assert detail["failure_window"] is not None
    run = client.get(f"/runs/{r.json()['runs'][0]}").json()
    assert run["params"]["scenario"]["config"]["constellation"]["sats_per_plane"] == 8


def test_rest_endpoints_accept_scenario_id(env):
    client, _ = env
    sid = make_scenario(client)
    assert client.get(f"/constellation/info?scenario_id={sid}").json()["n_sats"] == 48
    assert client.get("/constellation/info").json()["n_sats"] == 528
    assert client.get("/constellation/info?scenario_id=999").status_code == 404

    links = client.get(f"/links/summary?scenario_id={sid}&t=0").json()
    assert links["isl"]["candidates"] == 96
    topology = client.get(f"/topology/summary?scenario_id={sid}").json()
    assert topology["nodes"] == 48 + 3


def test_live_stream_on_a_scenario(env):
    client, _ = env
    sid = make_scenario(client)
    with client.websocket_connect(f"/ws/live?scenario_id={sid}") as ws:
        init = ws.receive_json()
        assert init["constellation"]["n_sats"] == 48 and init["scenario"]["name"] == "small"
        assert len(init["stations"]) == 3 and len(init["flows"]) == 3
        ws.receive_json()                                            # initial state
        ws.send_json({"cmd": "start", "dt": 60, "duration": 60, "speed": 20})
        frames = collect_until_done(ws)
    assert frames and all(len(f["sats"]) == 48 for f in frames)


def test_live_unknown_scenario_is_an_error(env):
    client, _ = env
    with client.websocket_connect("/ws/live?scenario_id=999") as ws:
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_replay_uses_the_runs_scenario(env):
    client, _ = env
    sid = make_scenario(client)
    run_id = client.post("/runs", json={"duration": 60, "dt": 60, "scenario_id": sid}).json()["id"]
    with client.websocket_connect(f"/ws/replay/{run_id}") as ws:
        init = ws.receive_json()
        assert init["constellation"]["n_sats"] == 48 and init["scenario"]["name"] == "small"
        ws.send_json({"cmd": "speed", "speed": 60})
        frames = collect_until_done(ws)
    assert frames and all(len(f["sats"]) == 48 for f in frames)
    