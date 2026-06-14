# filecache-client

Python client for the [filecache](../readme.md) REST API.

## Installation

Install from the local package:

```bash
pip install ./client
```

Or from PyPI:

```bash
pip install dwilson-filecache-client
```

**Requires:** Python 3.11+, `httpx>=0.27.0`

---

## Quick start

```python
from filecache_client import FileCacheClient

with FileCacheClient("http://localhost:8030") as client:
    # Two-phase ingest (download in client process, stream to filecache)
    result = client.ingest_from_url(
        url="https://example.com/report.pdf",
        bucket="documents",
        filename="report.pdf",
    )
    print(result["status"], result["hash"])

    # Lookup and download
    entry = client.lookup("https://example.com/report.pdf")
    if entry:
        client.download_to_file(entry["hash"], "./report-copy.pdf")
```

---

## Common operations

### Server-side download (with request_auth permits)

```python
result = client.server_download(
    url="https://example.com/protected.zip",
    bucket="archives",
    filename="protected.zip",
    headers={"Authorization": "Bearer <token>"},
)
```

### Manual two-phase upload

```python
init = client.upload_init(
    url="https://example.com/file.bin",
    bucket="artifacts",
    filename="file.bin",
)

if init["status"] == "pending":
    with open("file.bin", "rb") as f:
        result = client.upload_stream(init["upload_id"], f)
```

### Search and metadata

```python
results = client.search(url_contains="example.com", bucket="documents")
meta = client.get_meta(results[0]["hash"]) if results else None
```

### Stream file bytes

```python
with client.stream_file("<content_hash>") as chunks:
    for chunk in chunks:
        ...
```
