import httpx
from fastapi import APIRouter, HTTPException, Request

from clients import get_client, CACHE_URLS

router = APIRouter(prefix="/api/browse", tags=["browse"])


async def _proxy(cache_type: str, upstream_path: str, request: Request):
    if cache_type not in CACHE_URLS:
        raise HTTPException(status_code=404, detail="Unknown cache type")
    client = get_client(cache_type)
    try:
        resp = await client.get(upstream_path, params=dict(request.query_params))
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Upstream unavailable: {e}")


@router.get("/{cache_type}/buckets")
async def list_buckets(cache_type: str, request: Request):
    return await _proxy(cache_type, "/browse/buckets", request)


@router.get("/{cache_type}/prefixes")
async def list_prefixes(cache_type: str, request: Request):
    return await _proxy(cache_type, "/browse/prefixes", request)


@router.get("/{cache_type}")
async def browse(cache_type: str, request: Request):
    return await _proxy(cache_type, "/browse", request)
