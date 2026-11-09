# vidcache-client

Python client for the [vidcache](../readme.md) REST API — a content-addressed video cache service with BLAKE3 exact deduplication and perceptual hash matching.

## Installation

Install directly from the local package:

```bash
pip install ./client
```

Or add it to a `requirements.txt`:

```
dwilson-vidcache-client>=1.0.0
```

**Requires:** Python 3.11+, `httpx>=0.27.0`

---

## Quick start

```python
from vidcache_client import VidCacheClient

client = VidCacheClient("http://localhost:8020")

# Ingest a video URL — runs full dedup pipeline on the server
result = client.ingest(
    url="https://example.com/videos/abc123.mp4",
    bucket="videos",
    prefix="archive",
    meta={"title": "Cool video"},
)

print(result["hash"])    # BLAKE3 hex digest
print(result["status"])  # "new" | "duplicate" | "url_alias"

# Resolve a URL to its hash (no re-ingest)
entry = client.resolve("https://example.com/videos/abc123.mp4")

# Get metadata + all known source URLs
meta = client.get_meta(entry["hash"])
print(meta["duration_s"])
print(meta["aliases"])   # list of all ingested URLs for this video

# Download raw bytes (small files)
video_bytes = client.get_bytes(entry["hash"])

# Stream to a file (recommended for large files)
client.download_to_file(entry["hash"], "video.mp4")

# Stream with manual chunk iteration
with client.stream_video(entry["hash"]) as chunks:
    for chunk in chunks:
        process(chunk)

# Byte-range read (e.g. for seeking)
clip_bytes = client.get_bytes(entry["hash"], byte_range=(0, 1_000_000))

# Delete
client.delete(entry["hash"])

client.close()  # or use as a context manager
```

Use as a context manager to close the HTTP connection automatically:

```python
with VidCacheClient("http://localhost:8020") as client:
    result = client.ingest(url=url, bucket="videos")
```

---

## API reference

### `VidCacheClient(base_url, timeout=300.0, chunk_size=1_048_576)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `base_url` | `str` | Base URL of the vidcache service, e.g. `http://localhost:8020` |
| `timeout` | `float` | Request timeout in seconds (default `300.0` — video ingest can be slow) |
| `chunk_size` | `int` | Byte chunk size for streamed video responses (default 1 MB) |

---

### `ingest(url, bucket, prefix="", meta=None) → dict`

Submit a video URL for caching.  Runs the full dedup pipeline on the server
(URL lookup → BLAKE3 exact hash → perceptual hash).

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Source URL of the video |
| `bucket` | `str` | Storage bucket name |
| `prefix` | `str` *(optional)* | Path prefix inside the bucket |
| `meta` | `dict` *(optional)* | Arbitrary metadata to store with the video |

Returns dict with `hash`, `status` (`"new"` / `"duplicate"` / `"url_alias"`),
`file_path`, and optionally `phash_distance`.

---

### `resolve(url) → dict | None`

Look up whether a URL has been ingested before.  Returns `{"hash": …, "url": …}` or `None`.

---

### `get_meta(content_hash) → dict | None`

Retrieve full metadata for a stored video.  Includes `hash`, `size_bytes`,
`duration_s`, `first_seen`, `aliases` (all known source URLs), and any
client-supplied `meta`.  Returns `None` if not found.

---

### `get_bytes(content_hash, byte_range=None) → bytes`

Download a stored video as raw bytes.  Accepts an optional `(start, end)` inclusive byte range.

---

### `stream_video(content_hash, byte_range=None) → context manager`

Stream a stored video as an iterable of byte chunks.  Use as a context manager:

```python
with client.stream_video(hash) as chunks:
    for chunk in chunks:
        ...
```

---

### `download_to_file(content_hash, dest, byte_range=None) → int`

Stream a video directly to a local file.  Returns the number of bytes written.

---

### `delete(content_hash) → None`

Delete a cached video and all its URL aliases.

---

### `close() → None`

Close the underlying HTTP connection pool.  Called automatically when used as a context manager.
