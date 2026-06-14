import os
from dataclasses import dataclass


@dataclass
class Settings:
    webcache_url: str = os.environ.get("WEBCACHE_URL", "http://webcache:8000")
    imgcache_url: str = os.environ.get("IMGCACHE_URL", "http://imgcache:8010")
    filecache_url: str = os.environ.get("FILECACHE_URL", "http://filecache:8030")
    vidcache_url: str = os.environ.get("VIDCACHE_URL", "http://vidcache:8020")
    port: int = int(os.environ.get("PORT", "8040"))


settings = Settings()
