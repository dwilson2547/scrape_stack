from contextlib import asynccontextmanager
from fastapi import FastAPI
from . import database as db_module
from .routes import buckets, config, domains, robots, status


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_module.Base.metadata.create_all(bind=db_module.engine)
    yield


app = FastAPI(
    title="Request Authorization API",
    description="Management API for the request authorization permit service.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(domains.router, prefix="/api")
app.include_router(buckets.router, prefix="/api")
app.include_router(robots.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(status.router, prefix="/api")


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}
