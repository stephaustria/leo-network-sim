import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TleSet
from app.db.session import get_db
from app.sim.frames import jd_to_datetime
from app.sim.tle import TleError, normalize_tle_text, parse_tle_text

router = APIRouter(prefix="/tle-sets", tags=["tle"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class TleSetIn(BaseModel):
    name: Name
    text: str = Field(min_length=20, max_length=3_000_000)


class TleFetchIn(BaseModel):
    group: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$")
    name: Name | None = None
    max_age_hours: float = Field(2.0, ge=0, le=168)      # reuse a fetch of the same group newer than this


def fetch_celestrak(group: str, timeout: float = 30.0) -> str:
    url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={urllib.parse.quote(group)}&FORMAT=tle"
    request = urllib.request.Request(url, headers={"User-Agent": "leo-network-sim/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def get_fetcher() -> Callable[[str], str]:
    """Dependency, so tests can replace the network call."""
    return fetch_celestrak


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _brief(row: TleSet) -> dict:
    return {"id": row.id, "name": row.name, "source": row.source, "n_sats": row.n_sats,
            "epoch": row.epoch, "created_at": row.created_at}


def _store(db: Session, name: str, source: str, text: str) -> TleSet:
    try:
        records = parse_tle_text(text)
    except TleError as exc:
        raise HTTPException(422, str(exc))
    epoch = jd_to_datetime(statistics.median(r.epoch_jd for r in records))
    row = TleSet(name=name, source=source, n_sats=len(records), epoch=epoch,
                 text=normalize_tle_text(records))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("")
def list_sets(db: Session = Depends(get_db)):
    return [_brief(r) for r in db.scalars(select(TleSet).order_by(TleSet.id.desc()).limit(100))]


@router.post("", status_code=201)
def create_set(req: TleSetIn, db: Session = Depends(get_db)):
    return _brief(_store(db, req.name, "paste", req.text))


@router.post("/fetch")
def fetch_set(req: TleFetchIn, response: Response, db: Session = Depends(get_db),
              fetch: Callable[[str], str] = Depends(get_fetcher)):
    """Fetch a CelesTrak group (for example starlink, iridium-NEXT, stations) and store it.
    A fetch of the same group newer than `max_age_hours` is reused instead (CelesTrak asks
    clients not to poll more often than every couple of hours)."""
    source = f"celestrak:{req.group.lower()}"
    recent = db.scalars(select(TleSet).where(TleSet.source == source)
                        .order_by(TleSet.id.desc()).limit(1)).first()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=req.max_age_hours)
    if recent is not None and _aware(recent.created_at) >= cutoff:
        response.status_code = 200
        return {**_brief(recent), "reused": True}

    try:
        text = fetch(req.group)
    except Exception as exc:                                    # network errors, HTTP errors, timeouts
        raise HTTPException(502, f"could not fetch from CelesTrak: {exc}")
    try:
        row = _store(db, req.name or f"CelesTrak {req.group}", source, text)
    except HTTPException as exc:
        raise HTTPException(502, f"unexpected response from CelesTrak: {exc.detail}")
    response.status_code = 201
    return {**_brief(row), "reused": False}


@router.get("/{set_id}")
def get_set(set_id: int, db: Session = Depends(get_db)):
    row = db.get(TleSet, set_id)
    if row is None:
        raise HTTPException(404, "TLE set not found")
    records = parse_tle_text(row.text)
    return {
        **_brief(row),
        "satellites": [{"name": r.name, "norad_id": r.norad_id,
                        "inclination_deg": round(r.inclination_deg, 2),
                        "mean_motion_rev_day": round(r.mean_motion_rev_day, 4)} for r in records[:50]],
        "truncated": len(records) > 50,
    }