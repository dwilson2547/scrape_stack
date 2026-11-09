import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/status", tags=["status"])

STATUS_URL = os.environ.get("GRPC_STATUS_URL", "http://localhost:9003/status")


@router.get("")
async def get_status():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(STATUS_URL)
            resp.raise_for_status()
            return resp.json()
    except httpx.RequestError as e:
        raise HTTPException(503, f"gRPC server unreachable: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"gRPC server error: {e}")
