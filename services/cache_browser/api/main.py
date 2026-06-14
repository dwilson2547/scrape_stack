import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import clients
from config import settings
from routers import browse, search

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await clients.startup()
    yield
    await clients.shutdown()


app = FastAPI(title="Cache Browser API", lifespan=lifespan)
app.include_router(browse.router)
app.include_router(search.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=False)
