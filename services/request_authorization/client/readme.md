# request-auth-client

Python client for the Request Authorization gRPC permit service.

## Installation

Install from the local package directory:

```bash
pip install ./client
```

Or from PyPI:

```bash
pip install dwilson-request-auth-client
```

**Requires:** Python 3.11+, `grpcio>=1.80.0`, `protobuf>=6.31.1`

---

## Quick start

```python
from request_auth_client import RequestAuthClient

client = RequestAuthClient("localhost:9000")

try:
    with client.acquire("example.com") as permit:
        # run request here
        permit.set_status(200)
finally:
    client.close()
```

### Explicit release

```python
permit = client.acquire("example.com")
try:
    # run request here
    permit.release(200)
except Exception:
    permit.release(0)
```
