from datetime import datetime, timezone

from app.api.tle import get_fetcher
from app.main import app
from app.sim.tle import walker_tle_text

EPOCH = datetime(2026, 10, 13, tzinfo=timezone.utc)
WALKER_TLE = walker_tle_text(6, 8, 550.0, 53.0, epoch=EPOCH)


def upload(client, name, text):
    return client.post("/tle-sets", json={"name": name, "text": text})


def test_tle_set_crud(env):
    client, _ = env
    r = upload(client, "walker 6x8", WALKER_TLE)
    assert r.status_code == 201, r.text
    assert r.json()["n_sats"] == 48
    sid = r.json()["id"]

    assert client.get("/tle-sets").json()[0]["id"] == sid
    got = client.get(f"/tle-sets/{sid}").json()
    assert got["n_sats"] == 48 and len(got["satellites"]) == 48
    epoch = datetime.fromisoformat(got["epoch"].replace("Z", "+00:00"))
    if epoch.tzinfo is None:
        epoch = epoch.replace(tzinfo=timezone.utc)
    assert abs((epoch - EPOCH).total_seconds()) < 1.0

    assert upload(client, "bad", "this is not a tle, there is nothing to parse here").status_code == 422
    assert client.get("/tle-sets/999").status_code == 404


def test_fetch_stores_and_reuses_recent_sets(env):
    client, _ = env
    calls = []

    def fake_fetch(group):
        calls.append(group)
        return WALKER_TLE

    app.dependency_overrides[get_fetcher] = lambda: fake_fetch
    first = client.post("/tle-sets/fetch", json={"group": "walker-test"})
    assert first.status_code == 201, first.text
    assert first.json()["source"] == "celestrak:walker-test" and first.json()["reused"] is False

    second = client.post("/tle-sets/fetch", json={"group": "walker-test"})
    assert second.status_code == 200 and second.json()["reused"] is True
    assert second.json()["id"] == first.json()["id"] and calls == ["walker-test"]

    forced = client.post("/tle-sets/fetch", json={"group": "walker-test", "max_age_hours": 0})
    assert forced.status_code == 201 and len(calls) == 2
    assert client.post("/tle-sets/fetch", json={"group": "bad group!"}).status_code == 422


def test_fetch_errors_become_502(env):
    client, _ = env

    def broken(group):
        raise RuntimeError("network down")

    app.dependency_overrides[get_fetcher] = lambda: broken
    assert client.post("/tle-sets/fetch", json={"group": "x1"}).status_code == 502

    app.dependency_overrides[get_fetcher] = lambda: (lambda group: "No GP data found")
    assert client.post("/tle-sets/fetch", json={"group": "x2"}).status_code == 502


def test_scenarios_with_tle_shells(env):
    client, _ = env
    sid = upload(client, "walker 6x8", WALKER_TLE).json()["id"]

    both = client.post("/scenarios", json={"name": "walker + tle", "config": {
        "constellation": {"planes": 6, "sats_per_plane": 8},
        "tle_shells": [{"tle_set_id": sid}], "epoch": "2026-10-13T00:00:00Z"}})
    assert both.status_code == 201, both.text
    assert both.json()["n_sats"] == 96
    assert both.json()["config"]["epoch"] == "2026-10-13T00:00:00Z"

    only = client.post("/scenarios", json={"name": "tle only", "config": {
        "constellation": None,
        "tle_shells": [{"tle_set_id": sid, "name_contains": "WALKER-0", "limit": 10}]}})
    assert only.status_code == 201, only.text
    tid = only.json()["id"]
    assert only.json()["n_sats"] == 10
    assert only.json()["summary"]["shells"][0]["kind"] == "tle"

    info = client.get(f"/constellation/info?scenario_id={tid}").json()
    assert info["n_sats"] == 10 and info["planes"] == 0 and info["shells"][0]["kind"] == "tle"

    cov = client.get(f"/coverage?scenario_id={tid}&res_deg=30&window_hours=2&step_s=300").json()
    assert cov["params"]["n_sats"] == 10

    run = client.post("/runs", json={"scenario_id": tid, "duration": 60})
    assert run.status_code == 202, run.text
    assert client.get(f"/runs/{run.json()['id']}").json()["status"] == "completed"

    with client.websocket_connect(f"/ws/live?scenario_id={tid}") as ws:
        init = ws.receive_json()
        assert init["constellation"]["n_sats"] == 10
        assert init["constellation"]["shells"][0]["kind"] == "tle"
        assert init["isl_pairs"] == []


def test_invalid_tle_scenarios_are_rejected(env):
    client, _ = env
    sid = upload(client, "walker 6x8", WALKER_TLE).json()["id"]

    def post(name, config):
        return client.post("/scenarios", json={"name": name, "config": config})

    assert post("missing", {"tle_shells": [{"tle_set_id": 999}]}).status_code == 422
    assert post("nothing", {"constellation": None}).status_code == 422          # no shells at all
    assert post("epoch", {"epoch": "tomorrow"}).status_code == 422
    assert post("filter", {"tle_shells": [{"tle_set_id": sid, "name_contains": "NOPE"}]}).status_code == 422

    # failure presets need orbital planes, which TLE satellites do not have
    tle_only = post("tle only", {"constellation": None, "tle_shells": [{"tle_set_id": sid}]}).json()["id"]
    r = client.post("/experiments", json={"preset": "plane_outage", "scenario_id": tle_only,
                                          "duration": 60, "dt": 60})
    assert r.status_code == 422