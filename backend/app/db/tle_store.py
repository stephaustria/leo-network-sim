from app.db.models import TleSet
from app.db.session import SessionLocal


def load_tle_text(set_id: int) -> str:
    with SessionLocal() as db:
        row = db.get(TleSet, set_id)
        if row is None:
            raise ValueError(f"TLE set {set_id} not found")
        return row.text