import httpx
from config import settings

_clients: dict[str, httpx.AsyncClient] = {}

CACHE_URLS = {
    "web": settings.webcache_url,
    "image": settings.imgcache_url,
    "file": settings.filecache_url,
    "video": settings.vidcache_url,
}


async def startup():
    for cache_type, base_url in CACHE_URLS.items():
        _clients[cache_type] = httpx.AsyncClient(base_url=base_url, timeout=30.0)


async def shutdown():
    for client in _clients.values():
        await client.aclose()
    _clients.clear()


def get_client(cache_type: str) -> httpx.AsyncClient:
    client = _clients.get(cache_type)
    if client is None:
        raise KeyError(f"No client registered for cache type '{cache_type}'")
    return client
