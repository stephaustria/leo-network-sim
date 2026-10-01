import pytest
from starlette.websockets import WebSocketDisconnect


def make_run(client, **overrides):
    body = {"duration": 180, "dt": 60, "load_scale": 3.0, **overrides}
    r = client.post("/runs", json=body)
    assert r.status_code == 202
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


def test_live_stream(env):
    client, _ = env
    with client.websocket_connect("/ws/live") as ws:
        init = ws.receive_json()
        assert init["type"] == "init"
        assert init["constellation"]["n_sats"] == 528
        assert len(init["isl_pairs"]) == 1056 and len(init["stations"]) == 6

        assert ws.receive_json()["type"] == "state"
        ws.send_json({"cmd": "start", "dt": 60, "duration": 120, "speed": 20, "load_scale": 3})
        frames = collect_until_done(ws)

    assert [f["t"] for f in frames] == [0, 60, 120]
    f = frames[0]
    assert f["mode"] == "live" and f["progress"] == {"tick": 0, "of": 3}
    assert len(f["sats"]) == 528
    assert len(f["ground_links"]) <= 6
    assert {"station", "sat", "utilization"} <= set(f["ground_links"][0]) if f["ground_links"] else True
    assert len(f["flows"]) == 15 and "metrics" in f


def test_bad_commands_return_errors(env):
    client, _ = env
    with client.websocket_connect("/ws/live") as ws:
        ws.receive_json()   # init
        ws.receive_json()   # initial state
        ws.send_json({"cmd": "bogus"})
        assert ws.receive_json()["type"] == "error"
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"cmd": "set", "speed": "fast"})
        assert ws.receive_json()["type"] == "error"


def test_pause_is_acknowledged(env):
    client, _ = env
    with client.websocket_connect("/ws/live") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"cmd": "pause"})
        msg = ws.receive_json()
        assert msg["type"] == "state" and msg["paused"] is True


def test_replay_streams_stored_run_and_seeks(env):
    client, _ = env
    run_id = make_run(client)                    # ticks at 0, 60, 120, 180

    with client.websocket_connect(f"/ws/replay/{run_id}") as ws:
        assert ws.receive_json()["type"] == "init"
        ws.send_json({"cmd": "speed", "speed": 60})
        frames = collect_until_done(ws)

        assert [f["t"] for f in frames] == [0, 60, 120, 180]
        assert all(f["mode"] == "replay" for f in frames)
        assert frames[-1]["progress"] == {"tick": 3, "of": 4}
        assert len(frames[0]["sats"]) == 528 and len(frames[0]["flows"]) == 15
        assert any(f["ground_links"] for f in frames)

        ws.send_json({"cmd": "seek", "t": 65})   # nearest stored tick is t=60
        while True:
            m = ws.receive_json()
            if m["type"] == "frame":
                assert m["t"] == 60
                break


def test_replay_unknown_run(env):
    client, _ = env
    with client.websocket_connect("/ws/replay/999") as ws:
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()