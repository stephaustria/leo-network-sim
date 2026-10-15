import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import coverage as coverage_api
from app.db.models import Base, TleSet
from app.db.session import get_db, get_session_factory
from app.main import app
from app.sim import worlds


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

    def load_tle(set_id: int) -> str:
        with Session() as db:
            row = db.get(TleSet, set_id)
            if row is None:
                raise ValueError(f"TLE set {set_id} not found")
            return row.text

    previous = worlds._tle_loader
    worlds.set_tle_loader(load_tle)              # also clears cached worlds
    coverage_api._cached.cache_clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: Session
    yield TestClient(app), Session               # no `with`: skips lifespan hooks
    app.dependency_overrides.clear()
    worlds.set_tle_loader(previous)
    coverage_api._cached.cache_clear()