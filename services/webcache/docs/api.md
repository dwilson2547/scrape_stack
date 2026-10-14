# WebCache API Reference

Base URL: `http://localhost:8000`

---

## Health

### `GET /health`
Returns service status.

**Response 200**
```json
{ "status": "ok" }
```

---

## Cache

### `POST /cache`
Store a web page. Content is compressed with LZ4 and written to storage.
A BLAKE2b hash of the content is used as the file name, ensuring identical
content is never written more than once.

**Request body**
| Field | Type | Description |
|---|---|---|
| `url` | string | Full URL of the page (including query parameters) |
| `content` | string | Raw page content (HTML, XML, etc.) |
| `client_name` | string | Identifier for the scraper that fetched the page |
| `lookup_time` | datetime (ISO 8601) | When the client fetched the page from origin |

**Responses**
| Code | Meaning |
|---|---|
| 201 | Entry stored successfully |
| 200 | Identical content already cached (no write performed) |
| 422 | Validation error |

---

### `GET /cache?url={url}`
Retrieve the most recent cached entry for an exact URL.  Includes decompressed content.

**Query parameters**
| Parameter | Description |
|---|---|
| `url` | Exact URL to look up |

**Responses**
| Code | Meaning |
|---|---|
| 200 | Entry found; body includes `content` field |
| 404 | No entry for that URL |

---

### `GET /cache/search?url_contains={substring}`
Search for all cached entries whose URL contains `substring`.
Returns metadata only (no content). Useful for querying a base URL
across many query-parameter variants.

**Example:** `GET /cache/search?url_contains=example.com/products`
matches `https://example.com/products?page=1`, `…?page=2`, etc.

**Responses**
| Code | Meaning |
|---|---|
| 200 | Array of matching metadata objects (may be empty) |

---

### `GET /cache/{content_hash}`
Retrieve a specific cached entry by its BLAKE2b content hash.

**Responses**
| Code | Meaning |
|---|---|
| 200 | Entry found; body includes `content` field |
| 404 | Hash not found |

---

### `DELETE /cache/{content_hash}`
Delete a cached entry and its associated storage file.

**Responses**
| Code | Meaning |
|---|---|
| 204 | Deleted |
| 404 | Hash not found |

---

## Response schema — `CacheEntryMeta`

```json
{
  "url": "https://example.com/page",
  "content_hash": "a3f1…",
  "client_name": "my_scraper",
  "lookup_time": "2024-01-01T12:00:00",
  "created_at": "2024-01-01T12:01:00"
}
```

`CacheEntryFull` adds a `content` field (string) containing the decompressed page.

---

## Bucket retention

Buckets are implicit (any store with a `bucket` value creates one). A bucket
**config** caps a bucket with a rolling "latest N" window: after every store,
the oldest entries beyond the limits are evicted (DB row + storage file).

A storage file is only deleted once no remaining entry references the same
`(bucket, content_hash, prefix)` — identical content stored under two URLs
shares one file.

### `GET /buckets`
List all bucket configs with live stats (`entries`, `total_bytes`).

### `PUT /buckets/{bucket}`
Create or update a config and enforce it immediately.

```json
{"max_entries": 1000, "max_total_bytes": null}
```

Either limit may be `null` (disabled); both `null` keeps the config but
disables eviction. Values must be >= 1.

### `POST /buckets/{bucket}/enforce`
Manually evict down to the configured limits — useful after lowering a limit
on a bucket that is already over it. Returns `{"bucket": ..., "evicted": n}`.

### `DELETE /buckets/{bucket}`
Remove the config only. Entries are **not** deleted.

**Responses**
| Code | Meaning |
|---|---|
| 200/201 | Config returned with `stats` |
| 404 | No config for this bucket (enforce/delete) |
| 422 | Invalid limits or empty bucket name |

