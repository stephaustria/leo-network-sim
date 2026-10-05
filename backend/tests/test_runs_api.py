from sqlalchemy import func, select

from app.db.models import FlowSample, TickMetric


def make_run(client, **overrides):
    body = {"duration": 300, "dt": 60, "load_scale": 3.0, **overrides}
    r = client.post("/runs", json=body)
    assert r.status_code == 202
    return r.json()["id"]


def test_run_lifecycle(env):
    client, _ = env
    run_id = make_run(client)               # background task finishes before the call returns

    run = client.get(f"/runs/{run_id}").json()
    assert run["status"] == "completed" and run["n_ticks"] == 6

    tl = client.get(f"/runs/{run_id}/timeline").json()
    assert [row["t"] for row in tl] == [0, 60, 120, 180, 240, 300]

    flows = client.get(f"/runs/{run_id}/flows?t=130").json()   # nearest tick -> 120
    assert flows["t"] == 120 and len(flows["flows"]) == 15

    links = client.get(f"/runs/{run_id}/links").json()          # latest tick
    assert links["t"] == 300
    assert all(l["load_gbps"] > 0 or l["kind"] == "ground" for l in links["links"])

    ho = client.get(f"/runs/{run_id}/handoffs?include_acquired=true").json()
    assert any(h["reason"] == "acquired" for h in ho)

    assert client.get("/runs").json()[0]["id"] == run_id


def test_validation_rejects_too_many_ticks(env):
    client, _ = env
    r = client.post("/runs", json={"duration": 7200, "dt": 10})
    assert r.status_code == 422


def test_delete_removes_everything(env):
    client, Session = env
    run_id = make_run(client, duration=120)
    assert client.delete(f"/runs/{run_id}").status_code == 204
    assert client.get(f"/runs/{run_id}").status_code == 404
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(TickMetric)) == 0
        assert db.scalar(select(func.count()).select_from(FlowSample)) == 0


def test_unknown_run_is_404(env):
    client, _ = env
    assert client.get("/runs/999/timeline").status_code == 404

def test_run_with_policy_and_failures(env):
    client, _ = env
    run_id = make_run(client, duration=120, policy="min_hop",
                      failures=[{"kind": "station", "target": 0}])

    run = client.get(f"/runs/{run_id}").json()
    assert run["params"]["policy"] == "min_hop"
    assert run["params"]["failures"][0]["kind"] == "station"

    tl = client.get(f"/runs/{run_id}/timeline").json()
    assert all(row["flows_reachable"] <= 10 for row in tl)   # station 0's 5 flows are down
    assert all("route_changes" in row and "mean_hops" in row for row in tl)


def test_run_rejects_bad_policy_and_failures(env):
    client, _ = env
    assert client.post("/runs", json={"policy": "random"}).status_code == 422
    assert client.post("/runs", json={"failures": [{"kind": "satellite", "target": 99999}]}).status_code == 422