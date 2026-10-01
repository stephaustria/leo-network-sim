import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, FlowSample, TickMetric
from app.db.session import get_db, get_session_factory
from app.main import app


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: Session
    yield TestClient(app), Session     # no `with`: skips the Postgres lifespan hook
    app.dependency_overrides.clear()


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
    assert all(l["load_gbps"] > 0 for l in links["links"])

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