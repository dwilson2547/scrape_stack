# Matching 5 s keep-alive timeouts on webcache and httpx let a scraper reuse a connection as it closed, failing the run with RemoteProtocolError

**Date:** 2026-11-08  
**Component:** `helm/scrape-stack/templates/cache-services.yaml` — webcache Deployment env; `libs/cache_client/cache_client/_base.py` — `httpx.Client` pool  
**Severity:** Medium. Intermittent, but it kills a whole scraper run: a long run has thousands of chances to hit it.

---

## Observed symptom

gyopart's u-pull-n-save run 20261108183939 failed after 12 minutes (exit 75):

```
File "/app/scraper.py", line 103, in _fetch_json
    web_cache.store(url, resp.text, CLIENT_NAME)
...
httpx.RemoteProtocolError: Server disconnected without sending a response.
```

The webcache pod had no restarts and no errors in its log. The POSTs just before the failure got 201.

---

## Root cause

### Both sides expire idle connections after the same 5 s

webcache runs `uvicorn app.main:app` with uvicorn's default `--timeout-keep-alive 5`. `WebCacheClient` builds
`httpx.Client(base_url=..., timeout=...)` with httpx's default pool `keepalive_expiry=5.0`. A scraper waits between
cache calls for its rate limit or request-auth permit. If a wait comes close to 5 s, httpx still thinks the pooled
connection is usable at the moment uvicorn closes it. The request goes out on a socket the server has just closed, and
httpx raises `RemoteProtocolError`.

### Nothing retries a cache store

`_fetch_json` calls `web_cache.store` directly. A failed cache write is treated like a failed fetch and ends the run.

---

## Troubleshooting steps taken

1. **Scraper traceback.** The failure was in the POST to webcache, not in the request to u-pullandsave.com. That ruled
   out the target site.
2. **webcache pod and logs.** 0 restarts, 23 h up, only 201s. That ruled out a crash or OOM.
3. **Server startup.** `/proc/1/cmdline` in the pod is `uvicorn app.main:app --host 0.0.0.0 --port 8000`, so the
   keep-alive timeout is the default 5 s. Uvicorn is 0.54.0; its `main.py` reads options from `UVICORN_*` environment
   variables (`auto_envvar_prefix`).
4. **Client pool.** `_base.py` passes no `limits`, so httpx's 5 s `keepalive_expiry` applies.

---

## Fix

### webcache Deployment: `UVICORN_TIMEOUT_KEEP_ALIVE=65`

The server now holds idle connections for 65 s, much longer than the client's 5 s, so the client always drops a
connection first. No image rebuild was needed. Checked in the pod after the rollout: a connection left idle for 10 s
then served a second request with a 200.

Commit f6bbfdb on main (prod).

### imgcache, filecache, vidcache (a146d54)

The other cache services ran uvicorn with the same 5 s default and got the same 65 s:

- imgcache starts from the `uvicorn` CLI, so it takes the same `UVICORN_TIMEOUT_KEEP_ALIVE` env var.
- filecache and vidcache call `uvicorn.run()` from `main.py`. That ignores `UVICORN_*` env vars (only the CLI reads
  them), so the code now passes `timeout_keep_alive=65`. This needed new images.

After the rollout, a connection left idle for 10 s got a 200 on its next request in both filecache and vidcache.
request-auth was not checked.

---

## Files changed

- `helm/scrape-stack/templates/cache-services.yaml` — webcache and imgcache container env
- `services/filecache/main.py`, `services/vidcache/main.py` — `uvicorn.run(..., timeout_keep_alive=65)`
