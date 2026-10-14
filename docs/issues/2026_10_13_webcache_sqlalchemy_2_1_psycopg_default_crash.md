# Unpinned SQLAlchemy drift makes fresh webcache images crash-loop on Postgres (psycopg default changed in 2.1)

**Date:** 2026-10-13  
**Component:** `services/webcache/requirements.txt` — image build dependency resolution  
**Severity:** High — webcache (prod, `scrape-stack` namespace) was fully down (CrashLoopBackOff, ingress Bad Gateway) until a rebuilt image was rolled out; every other scraper in the stack depends on it.

---

## Observed symptom

After pushing a freshly built `dwilson2547/webcache:latest` (bucket-retention feature, ee499ae) and restarting the deployment, the pod crash-looped and `webcache.scrapestack.local` returned `502 Bad Gateway`:

```
File "/app/app/database.py", line 90, in get_engine
    _engine = create_engine(settings.database_url, connect_args=connect_args)
...
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/postgresql/psycopg.py", line 497, in import_dbapi
    import psycopg
ModuleNotFoundError: No module named 'psycopg'
```

The previous image had run the same `postgresql://` DATABASE_URL (helm `cache-services.yaml`) for 3d16h without issue.

---

## Root cause

### Unpinned `sqlalchemy>=2.0.0` resolved to 2.1.4 on rebuild

`requirements.txt` specified `sqlalchemy>=2.0.0`. The previous image was built when that resolved to a 2.0.x release, where the default driver for a bare `postgresql://` URL is psycopg2 (installed via `psycopg2-binary`). SQLAlchemy 2.1 had shipped in the meantime; the new build picked up 2.1.4, which changed the default dialect for `postgresql://` from psycopg2 to **psycopg (v3)** — which was never in requirements. Engine creation happens at app startup (`get_engine()` in the lifespan), so the whole app failed before serving.

The bucket-retention commit did not touch requirements or engine creation — this was latent drift, exposed by the first rebuild since SQLAlchemy 2.1's release.

---

## Troubleshooting steps taken

1. **Checked rollout and pod logs** — rollout reported "successfully rolled out" but the pod was in `Error` restart loop (0/1); logs showed the psycopg import failure at startup, ruling out ingress/service issues.

2. **Verified the image contents directly** (`docker run dwilson2547/webcache:latest`) — SQLAlchemy 2.1.4 present, psycopg2 imports fine, psycopg absent. Ruled out a broken psycopg2 install; confirmed the dialect-choice change.

3. **Confirmed URL → dialect resolution** — rebuilt with a pin and constructed an engine from a bare `postgresql://` URL inside the image, printing `engine.dialect.driver`: `psycopg2` after the fix, `psycopg` before it.

---

## Fix

### `services/webcache/requirements.txt` — pin SQLAlchemy below 2.1

```diff
-sqlalchemy>=2.0.0
+sqlalchemy>=2.0.0,<2.1
```

Minimal-risk restore of the exact prior behavior (psycopg2 dialect). A deliberate upgrade to SQLAlchemy 2.1 + `psycopg[binary]` (v3) is the forward path but is a separate, tested change — not something to land mid-outage.

Image rebuilt, pushed, deployment restarted; `/health` OK, `/openapi.json` reports 0.3.0 with the new `/buckets` endpoints. Bucket config `rockauto_revival` (max_entries 1000) created and verified with an end-to-end crawler run.

---

## Files changed

- `services/webcache/requirements.txt` — pinned `sqlalchemy>=2.0.0,<2.1`

---

## Follow-up

- Consider pinning or locking *all* scrape-stack service dependencies (the other cache services share this pattern — any of them could drift the same way on their next rebuild).
- Migrate webcache to SQLAlchemy 2.1 + psycopg3 deliberately, with tests, rather than whenever pip next resolves.
