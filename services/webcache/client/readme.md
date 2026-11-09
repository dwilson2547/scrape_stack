# webcache-client

Python client for the [WebCache](../readme.md) REST API.

## Installation

Install directly from the local package:

```bash
pip install ./client
```

Or add it to a `requirements.txt` alongside the webcache service:

```
dwilson-webcache-client>=0.2.0
```

**Requires:** Python 3.11+, `httpx>=0.27.0`

---

## Quick start

```python
from webcache_client import WebCacheClient

client = WebCacheClient("http://localhost:8000")

# Store a page
client.store(url="https://example.com/page", content="<html>…</html>", client_name="my_scraper")

# Retrieve by exact URL
entry = client.get("https://example.com/page")
print(entry["content"])

# Search by URL substring (returns metadata only, no content)
results = client.search(url_contains="example.com")

# Delete by content hash
client.delete(content_hash=entry["content_hash"])

client.close()
```

Use as a context manager to close the HTTP connection automatically:

```python
with WebCacheClient("http://localhost:8000") as client:
    client.store(url=url, content=html, client_name="my_scraper")
```

---

## API reference

### `WebCacheClient(base_url, timeout=30.0)`

| Parameter | Type | Description |
|---|---|---|
| `base_url` | `str` | Base URL of the WebCache service, e.g. `http://localhost:8000` |
| `timeout` | `float` | Request timeout in seconds (default `30.0`) |

---

### `store(url, content, client_name, lookup_time=None) → dict`

Cache a web page.

| Parameter | Type | Description |
|---|---|---|
| `url` | `str` | Full URL of the page, including any query parameters |
| `content` | `str` | Raw page content (HTML, XML, etc.) |
| `client_name` | `str` | Identifier for the scraper that fetched the page |
| `lookup_time` | `datetime` *(optional)* | When the page was fetched from origin; defaults to `utcnow()` |

Returns the stored entry's metadata dict. HTTP 201 means the page was newly stored; HTTP 200 means identical content already existed (no write performed).

---

### `get(url) → dict | None`

Retrieve the most recent cached entry for an exact URL. Returns the full entry dict including `content`, or `None` if not found.

---

### `get_by_hash(content_hash) → dict | None`

Retrieve a cached entry by its BLAKE2b content hash. Returns `None` if not found.

---

### `search(url_contains) → list[dict]`

Return metadata for all cached entries whose URL contains the given substring. Content is not included — call `get` or `get_by_hash` to fetch the full page.

```python
# Matches https://example.com/products?page=1, ?page=2, etc.
results = client.search(url_contains="example.com/products")
for entry in results:
    print(entry["url"], entry["content_hash"])
```

---

### `delete(content_hash) → None`

Delete a cached entry and its associated storage file by content hash.

---

### `health() → dict`

Check that the service is reachable. Returns `{"status": "ok"}` when healthy.

---

### `close() → None`

Close the underlying HTTP connection. Called automatically when used as a context manager.

---

## Entry schema

Fields returned by `store`, `get`, and `get_by_hash`:

| Field | Type | Description |
|---|---|---|
| `url` | `str` | The cached page URL |
| `content_hash` | `str` | BLAKE2b hash of the content (also the storage filename) |
| `client_name` | `str` | Scraper that submitted the entry |
| `lookup_time` | `str` (ISO 8601) | When the page was fetched from origin |
| `created_at` | `str` (ISO 8601) | When the entry was stored in the cache |
| `content` | `str` | Decompressed page content *(full-entry endpoints only)* |

`search` results omit the `content` field.
