"""VidCacheClient — client for the vidcache service."""
from __future__ import annotations

from ._streaming_base import StreamingCacheClient


class VidCacheClient(StreamingCacheClient):
    """Python client for the vidcache REST API.

    Inherits all upload/download/streaming methods from
    :class:`~cache_client._streaming_base.StreamingCacheClient`.

    The ``stream_video`` method is an alias for ``stream_content`` for
    readability in video-handling code.  Use ``byte_range`` for partial
    content / adaptive streaming.

    Usage::

        from cache_client import VidCacheClient

        with VidCacheClient("http://localhost:8030") as client:
            result = client.server_download(
                "https://cdn.example.com/clip.mp4",
                bucket="raw",
                filename="clip.mp4",
            )
            with client.stream_video(result["hash"]) as chunks:
                for chunk in chunks:
                    …
    """

    def stream_video(self, content_hash: str, byte_range=None):
        """Stream a stored video as chunks — alias for :meth:`stream_content`."""
        return self.stream_content(content_hash, byte_range=byte_range)
