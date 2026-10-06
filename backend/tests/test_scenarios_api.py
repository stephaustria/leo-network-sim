def body(name="s1", **cfg):
    return {"name": name, "description": "test", "config": cfg}


def test_scenario_crud(env):
    client, _ = env
    r = client.post("/scenarios", json=body("small", constellation={"planes": 6, "sats_per_plane": 8}))
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["summary"]["n_sats"] == 48

    assert client.post("/scenarios", json=body("small")).status_code == 409

    got = client.get(f"/scenarios/{sid}").json()
    assert got["config"]["constellation"]["planes"] == 6
    assert len(got["config"]["stations"]) == 6            # defaults filled in

    listing = client.get("/scenarios").json()
    assert [s["name"] for s in listing] == ["small"] and listing[0]["n_sats"] == 48

    r = client.put(f"/scenarios/{sid}",
                   json=body("renamed", constellation={"planes": 8, "sats_per_plane": 10}))
    assert r.status_code == 200
    assert r.json()["name"] == "renamed" and r.json()["summary"]["n_sats"] == 80

    other = client.post("/scenarios", json=body("other")).json()["id"]
    assert client.put(f"/scenarios/{other}", json=body("renamed")).status_code == 409

    assert client.delete(f"/scenarios/{sid}").status_code == 204
    assert client.get(f"/scenarios/{sid}").status_code == 404
    assert client.delete(f"/scenarios/{sid}").status_code == 404


def test_default_and_preview_routes(env):
    client, _ = env
    d = client.get("/scenarios/default").json()               # not parsed as an id
    assert d["summary"]["n_sats"] == 528 and len(d["config"]["stations"]) == 6

    p = client.post("/scenarios/preview",
                    json={"config": {"constellation": {"planes": 12, "sats_per_plane": 12}}})
    assert p.status_code == 200 and p.json()["summary"]["n_sats"] == 144
    bad = client.post("/scenarios/preview", json={"config": {"constellation": {"planes": 2}}})
    assert bad.status_code == 422


def test_invalid_scenarios_are_rejected(env):
    client, _ = env
    assert client.post("/scenarios", json={"name": "   ", "config": {}}).status_code == 422
    assert client.post("/scenarios", json=body("x", link_params={"bogus": 1})).status_code == 422
    assert client.post("/scenarios", json=body("y", constellation={"planes": 72, "sats_per_plane": 23})
                       ).status_code == 422