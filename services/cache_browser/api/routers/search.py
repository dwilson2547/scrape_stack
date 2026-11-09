import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from clients import get_client, CACHE_URLS

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    date_from: str | None = None,
    date_to: str | None = None,
    client_name: str | None = None,
    cache_types: list[str] | None = Query(default=None),
):
    resolved_types = cache_types if cache_types is not None else list(CACHE_URLS.keys())
    # validate cache_types
    invalid = [ct for ct in resolved_types if ct not in CACHE_URLS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown cache types: {invalid}")

    params = {"limit": limit}
    if q is not None:
        params["q"] = q
    if date_from is not None:
        params["date_from"] = date_from
    if date_to is not None:
        params["date_to"] = date_to
    if client_name is not None:
        params["client_name"] = client_name

    async def fetch_one(cache_type: str):
        client = get_client(cache_type)
        try:
            # Upstream caches expose search via /browse?q=... (no separate /search route)
            resp = await client.get("/browse", params=params)
            resp.raise_for_status()
            return cache_type, resp.json().get("items", []), None
        except Exception as exc:
            log.warning("search failed for %s: %s", cache_type, exc)
            return cache_type, [], str(exc)

    results = await asyncio.gather(*[fetch_one(ct) for ct in resolved_types])

    all_items = []
    errors = {}
    for cache_type, items, error in results:
        all_items.extend(items)
        if error:
            errors[cache_type] = error

    return {
        "items": all_items,
        "cache_types_searched": resolved_types,
        "errors": errors if errors else None,
    }
