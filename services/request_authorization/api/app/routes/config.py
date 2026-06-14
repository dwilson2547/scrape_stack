from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GlobalConfig
from ..schemas import ConfigRead, ConfigUpdate

router = APIRouter(prefix="/config", tags=["config"])

_KEYS = [
    "default_pool_size", "default_base_delay_ms", "default_backoff_multiplier",
    "default_max_delay_ms", "default_recovery_threshold",
    "robots_txt_ttl_hours", "robots_txt_retry_hours", "config_reload_interval_seconds",
]


def _read_config(db: Session) -> dict:
    rows = db.query(GlobalConfig).filter(GlobalConfig.key.in_(_KEYS)).all()
    return {r.key: r.value for r in rows}


@router.get("", response_model=ConfigRead)
def get_config(db: Session = Depends(get_db)):
    m = _read_config(db)
    return ConfigRead(
        default_pool_size=int(m.get("default_pool_size", 1)),
        default_base_delay_ms=int(m.get("default_base_delay_ms", 1000)),
        default_backoff_multiplier=float(m.get("default_backoff_multiplier", 3.0)),
        default_max_delay_ms=int(m.get("default_max_delay_ms", 60000)),
        default_recovery_threshold=int(m.get("default_recovery_threshold", 10)),
        robots_txt_ttl_hours=int(m.get("robots_txt_ttl_hours", 24)),
        robots_txt_retry_hours=int(m.get("robots_txt_retry_hours", 24)),
        config_reload_interval_seconds=int(m.get("config_reload_interval_seconds", 30)),
    )


@router.patch("", response_model=ConfigRead)
def update_config(body: ConfigUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        row = db.get(GlobalConfig, key)
        if row:
            row.value = str(value)
        else:
            db.add(GlobalConfig(key=key, value=str(value)))
    db.commit()
    return get_config(db)
