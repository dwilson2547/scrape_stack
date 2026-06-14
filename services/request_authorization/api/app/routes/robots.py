from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RobotsTxtCache
from ..schemas import RobotsOverrideRequest, RobotsRead

router = APIRouter(prefix="/robots", tags=["robots"])


def _get_or_404(domain: str, db: Session) -> RobotsTxtCache:
    entry = db.query(RobotsTxtCache).filter_by(domain=domain).first()
    if not entry:
        raise HTTPException(404, f"no robots.txt cache entry for {domain!r}")
    return entry


@router.get("/{domain}", response_model=RobotsRead)
def get_robots(domain: str, db: Session = Depends(get_db)):
    return _get_or_404(domain, db)


@router.post("/{domain}/override", response_model=RobotsRead)
def override_robots(domain: str, body: RobotsOverrideRequest, db: Session = Depends(get_db)):
    entry = db.query(RobotsTxtCache).filter_by(domain=domain).first()
    if not entry:
        entry = RobotsTxtCache(domain=domain)
        db.add(entry)

    if not entry.is_overridden:
        entry.original_crawl_delay_ms = entry.crawl_delay_ms

    entry.is_overridden = True
    entry.override_delay_ms = body.override_delay_ms
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{domain}/revert", response_model=RobotsRead)
def revert_robots(domain: str, db: Session = Depends(get_db)):
    entry = _get_or_404(domain, db)
    if not entry.is_overridden:
        raise HTTPException(400, "entry is not overridden")
    entry.is_overridden = False
    entry.crawl_delay_ms = entry.original_crawl_delay_ms
    entry.override_delay_ms = None
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{domain}/refresh", status_code=202)
def refresh_robots(domain: str, db: Session = Depends(get_db)):
    """Mark the robots.txt entry as expired so the gRPC server re-fetches it."""
    entry = db.query(RobotsTxtCache).filter_by(domain=domain).first()
    if entry:
        entry.expires_at = None
        entry.fetched_at = None
        db.commit()
    return {"status": "refresh scheduled"}
