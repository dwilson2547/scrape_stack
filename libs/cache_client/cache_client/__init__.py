"""dwilson-cache-client — unified Python client for the scrape stack cache services.

Provides four service clients that share a common base:

    from cache_client import WebCacheClient, ImgCacheClient, FileCacheClient, VidCacheClient

All clients are synchronous wrappers around ``httpx``.
"""

from .filecache import FileCacheClient
from .imgcache import ImgCacheClient
from .vidcache import VidCacheClient
from .webcache import WebCacheClient

__all__ = [
    "WebCacheClient",
    "ImgCacheClient",
    "FileCacheClient",
    "VidCacheClient",
]
