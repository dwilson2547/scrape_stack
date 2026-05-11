"""Shared fixtures for integration tests against the live k8s cluster.

Set environment variables to override the default ingress hostnames:

  WEBCACHE_URL       http://webcache.scrapestack.local
  IMGCACHE_URL       http://imgcache.scrapestack.local
  VIDCACHE_URL       http://vidcache.scrapestack.local
  FILECACHE_URL      http://filecache.scrapestack.local
  REQUEST_AUTH_GRPC  request-auth-server.scrapestack.local:9000
  REQUEST_AUTH_API   http://auth.scrapestack.local
"""

import base64
import os
import time

import httpx
import pytest

from cache_client import FileCacheClient, ImgCacheClient, VidCacheClient, WebCacheClient

WEBCACHE_URL = os.getenv("WEBCACHE_URL", "http://webcache.scrapestack.local")
IMGCACHE_URL = os.getenv("IMGCACHE_URL", "http://imgcache.scrapestack.local")
VIDCACHE_URL = os.getenv("VIDCACHE_URL", "http://vidcache.scrapestack.local")
FILECACHE_URL = os.getenv("FILECACHE_URL", "http://filecache.scrapestack.local")
REQUEST_AUTH_GRPC = os.getenv("REQUEST_AUTH_GRPC", "request-auth-server.scrapestack.local:9000")
REQUEST_AUTH_API = os.getenv("REQUEST_AUTH_API", "http://auth.scrapestack.local")

# Unique prefix so parallel/repeated runs don't collide in the shared DB.
RUN_ID = str(int(time.time()))

# Minimal valid image / video fixtures ------------------------------------------------

# 1×1 red pixel PNG
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADklEQVQI12P4z8BQDwAEgAF/QualIQAAAABJRU5ErkJggg=="
)

# Minimal 1×1 white GIF (vidcache accepts GIFs as videos)
GIF_1x1 = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@pytest.fixture(scope="module")
def webcache():
    with WebCacheClient(WEBCACHE_URL) as c:
        yield c


@pytest.fixture(scope="module")
def imgcache():
    with ImgCacheClient(IMGCACHE_URL) as c:
        yield c


@pytest.fixture(scope="module")
def vidcache():
    with VidCacheClient(VIDCACHE_URL) as c:
        yield c


@pytest.fixture(scope="module")
def filecache():
    with FileCacheClient(FILECACHE_URL) as c:
        yield c


@pytest.fixture(scope="module")
def auth_api():
    with httpx.Client(base_url=REQUEST_AUTH_API, timeout=10.0) as c:
        yield c
