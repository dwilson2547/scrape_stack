# imgcache API Reference

## Base URL
`http://localhost:8010`

---

## Endpoints

### `POST /images`
Store a new image in the cache.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | ✅ | Binary image data |
| `url` | string | ✅ | Source URL of the image |
| `client_name` | string | ✅ | Identifier for the calling client |
| `lookup_time` | string (ISO 8601) | ✅ | When the client first looked this up |

**Responses**

| Status | Meaning |
|--------|---------|
| `201 Created` | Image stored successfully |
| `200 OK` | Duplicate — image already exists (returns same metadata) |

**Example**
```bash
curl -X POST http://localhost:8010/images \
  -F "file=@/path/to/image.png" \
  -F "url=https://example.com/image.png" \
  -F "client_name=my-scraper" \
  -F "lookup_time=2024-01-15T12:00:00"
```

**Response body**
```json
{
  "url": "https://example.com/image.png",
  "content_hash": "a1b2c3d4...",
  "content_type": "image/png",
  "file_size_bytes": 12345,
  "original_filename": "image.png",
  "width": 800,
  "height": 600,
  "perceptual_hash": "f8c0e0e0f0e0c080",
  "client_name": "my-scraper",
  "lookup_time": "2024-01-15T12:00:00",
  "created_at": "2024-01-15T12:00:01Z"
}
```

---

### `GET /images/{content_hash}`
Retrieve the raw binary content of a stored image.

**Path Parameters**

| Parameter | Description |
|-----------|-------------|
| `content_hash` | BLAKE2b-32 hex digest of the image data |

**Responses**

| Status | Meaning |
|--------|---------|
| `200 OK` | Returns image bytes with correct `Content-Type` |
| `404 Not Found` | No image with that hash |

**Example**
```bash
curl http://localhost:8010/images/a1b2c3d4... -o output.png
```

---

### `GET /images/meta/{content_hash}`
Retrieve metadata for a stored image without downloading the binary.

**Path Parameters**

| Parameter | Description |
|-----------|-------------|
| `content_hash` | BLAKE2b-32 hex digest |

**Responses**

| Status | Meaning |
|--------|---------|
| `200 OK` | Returns `ImageEntryMeta` JSON |
| `404 Not Found` | No image with that hash |

**Example**
```bash
curl http://localhost:8010/images/meta/a1b2c3d4...
```

---

### `GET /images/lookup`
Look up the most recent metadata entry for a given source URL.

**Query Parameters**

| Parameter | Description |
|-----------|-------------|
| `url` | Exact source URL to look up |

**Responses**

| Status | Meaning |
|--------|---------|
| `200 OK` | Returns `ImageEntryMeta` JSON |
| `404 Not Found` | URL not in cache |

**Example**
```bash
curl "http://localhost:8010/images/lookup?url=https://example.com/image.png"
```

---

### `GET /images/search`
Search cached entries by partial URL match.

**Query Parameters**

| Parameter | Description |
|-----------|-------------|
| `url_contains` | Substring to match against stored URLs |

**Responses**

| Status | Meaning |
|--------|---------|
| `200 OK` | Returns array of `ImageEntryMeta` (may be empty) |

**Example**
```bash
curl "http://localhost:8010/images/search?url_contains=example.com"
```

---

### `GET /images/similar`
Find images with a similar perceptual hash (Hamming distance).

**Query Parameters**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `perceptual_hash` | — | 16-char hex dHash string |
| `max_hamming_distance` | `4` | Maximum bit distance |

**Responses**

| Status | Meaning |
|--------|---------|
| `200 OK` | Returns array of `ImageEntryMeta` |

**Example**
```bash
curl "http://localhost:8010/images/similar?perceptual_hash=f8c0e0e0f0e0c080&max_hamming_distance=8"
```

---

### `DELETE /images/{content_hash}`
Delete an image and its metadata.

**Path Parameters**

| Parameter | Description |
|-----------|-------------|
| `content_hash` | BLAKE2b-32 hex digest |

**Responses**

| Status | Meaning |
|--------|---------|
| `204 No Content` | Successfully deleted |
| `404 Not Found` | No image with that hash |

**Example**
```bash
curl -X DELETE http://localhost:8010/images/a1b2c3d4...
```

---

### `GET /health`
Health check endpoint.

**Response**
```json
{"status": "ok"}
```

---

### `GET /metrics`
Prometheus metrics output.

**Response** — `text/plain; version=0.0.4` (Prometheus exposition format)

**Available metrics**

| Metric | Type | Description |
|--------|------|-------------|
| `imgcache_store_total` | Counter | Images stored (labels: `result=created\|duplicate`) |
| `imgcache_lookup_total` | Counter | Lookup requests (labels: `result=hit\|miss`) |
| `imgcache_image_bytes` | Histogram | Size distribution of stored images |
| `imgcache_perceptual_hash_computed` | Counter | Perceptual hash attempts (labels: `result=ok\|failed`) |
| `imgcache_similar_search_total` | Counter | Similar-image search requests |

**Example**
```bash
curl http://localhost:8010/metrics
```

---

## ImageEntryMeta Schema

```json
{
  "url": "string",
  "content_hash": "string (64-char hex)",
  "content_type": "string (MIME type)",
  "file_size_bytes": "integer",
  "original_filename": "string | null",
  "width": "integer | null",
  "height": "integer | null",
  "perceptual_hash": "string (16-char hex) | null",
  "client_name": "string",
  "lookup_time": "datetime (ISO 8601)",
  "created_at": "datetime (ISO 8601)"
}
```
