import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .database import Base, get_engine, run_migrations
from .metrics import setup_metrics
from .routes.browse import router as browse_router
from .routes.cache import router as cache_router
from .routes.render import router as render_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    run_migrations(engine)
    Base.metadata.create_all(bind=engine)
    setup_metrics(service_name=os.environ.get("OTEL_SERVICE_NAME", "webcache"))
    yield


app = FastAPI(
    title="WebCache",
    description="Centralized web page cold-storage cache with LZ4 compression.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(browse_router)
app.include_router(cache_router)
app.include_router(render_router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}
