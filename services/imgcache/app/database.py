from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

_engine = None
_SessionLocal = None

def override_engine(engine):
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        from app.config import settings
        kwargs = {}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(settings.database_url, **kwargs)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine

def get_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
