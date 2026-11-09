# imgcache-client

Python client for the [imgcache](../readme.md) REST API — a centralized image cache with perceptual hashing and duplicate detection.

## Installation

Install directly from the local package:

```bash
pip install ./client
```

Or add it to a `requirements.txt`:

```
dwilson-imgcache-client>=0.2.0
```

**Requires:** Python 3.11+, `httpx>=0.27.0`

---

## Quick start

```python
from imgcache_client import ImgCacheClient

client = ImgCacheClient("http://localhost:8010")

# Store an image
with open("photo.jpg", "rb") as f:
    entry = client.store(url="https://example.com/photo.jpg", file_bytes=f.read(), client_name="my_scraper")

print(entry["content_hash"])   # BLAKE2b hash / storage key
print(entry["perceptual_hash"]) # pHash for similarity search

# Retrieve raw bytes
img_bytes = client.get_bytes(entry["content_hash"])

# Retrieve metadata only
meta = client.get_meta(entry["content_hash"])

# Look up by source URL
meta = client.lookup("https://example.com/photo.jpg")

# Search by URL substring
results = client.search(url_contains="example.com")

# Find visually similar images
similar = client.similar(perceptual_hash=entry["perceptual_hash"], max_hamming_distance=4)

# Delete
client.delete(entry["content_hash"])

client.close()  # or use as a context manager (see below)
```

Use as a context manager to close the HTTP connection automatically:

```python
with ImgCacheClient("http://localhost:8010") as client:
    entry = client.store(url=url, file_bytes=img_bytes, client_name="my_scraper")
```

---

## API reference

### `ImgCacheClient(base_url, timeout=30.0)`

| Parameter | Type | Description |
|---|---|---|
| `base_url` | `str` | Base URL of the imgcache service, e.g. `http://localhost:8010` |
| `timeout` | `float` | Request timeout in seconds (default `30.0`) |

---

### `store(url, file_bytes, client_name, lookup_time=None, filename=None) → dict`

Store an image in the cache.

| Parameter | Type | Description |
|---|---|---|
| `url` | `str` | Source URL of the image |
| `file_bytes` | `bytes` | Raw binary image data |
| `client_name` | `str` | Identifier for the scraper submitting the image |
| `lookup_time` | `datetime` *(optional)* | When the image was fetched from origin; defaults to `utcnow()` |
| `filename` | `str` *(optional)* | Original filename hint (used for `Content-Type` detection) |

Returns the full entry metadata dict. HTTP 201 means newly stored; HTTP 200 means an identical image already existed.

---

### `get_bytes(content_hash) → bytes`

Download the raw binary content of a stored image by its BLAKE2b content hash.

---

### `get_meta(content_hash) → dict | None`

Retrieve metadata for a stored image without downloading the binary. Returns `None` if not found.

---

### `lookup(url) → dict | None`

Retrieve metadata for the most recent cached entry matching an exact source URL. Returns `None` if not found.

---

### `search(url_contains) → list[dict]`

Return metadata for all cached entries whose source URL contains the given substring. Useful for finding all cached variants of a URL.

```python
# Matches https://example.com/products/img1.jpg, /img2.jpg, etc.
results = client.search(url_contains="example.com/products")
for entry in results:
    print(entry["url"], entry["content_hash"])
```

---

### `similar(perceptual_hash, max_hamming_distance=4) → list[dict]`

Find visually similar images by comparing perceptual hashes. `max_hamming_distance` controls how strict the match is — lower values mean more similar results.

```python
similar = client.similar(perceptual_hash="f8c0e0e0f0e0c080", max_hamming_distance=4)
```

---

### `delete(content_hash) → None`

Delete a cached image and its associated storage file by content hash.

---

### `health() → dict`

Check that the service is reachable. Returns `{"status": "ok"}` when healthy.

---

### `close() → None`

Close the underlying HTTP connection. Called automatically when used as a context manager.

---

## Entry schema

Fields returned by `store`, `get_meta`, `lookup`, `search`, and `similar`:

| Field | Type | Description |
|---|---|---|
| `url` | `str` | Source URL the image was fetched from |
| `content_hash` | `str` | BLAKE2b hash of the raw image bytes (storage key) |
| `content_type` | `str` | MIME type, e.g. `image/jpeg` |
| `file_size_bytes` | `int` | Size of the stored image in bytes |
| `original_filename` | `str \| null` | Filename hint supplied at store time |
| `width` | `int \| null` | Image width in pixels |
| `height` | `int \| null` | Image height in pixels |
| `perceptual_hash` | `str \| null` | pHash for similarity comparisons |
| `client_name` | `str` | Scraper that submitted the entry |
| `lookup_time` | `str` (ISO 8601) | When the image was fetched from origin |
| `created_at` | `str` (ISO 8601) | When the entry was stored in the cache |

`get_bytes` returns raw `bytes` rather than a metadata dict.
