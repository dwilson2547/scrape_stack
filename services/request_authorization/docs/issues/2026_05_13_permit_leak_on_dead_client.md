# Permits leak indefinitely when gRPC client dies without a clean TCP close

**Date:** 2026-05-13  
**Component:** `server/app/main.go` — `main`; `tests/load_sim.py` — `main`  
**Severity:** High — permits held by a dead client block the entire domain pool; at 1 req/3 s this can stall scraping for hours with no operator-visible error

---

## Observed symptom

Grafana dashboards showed active permits for a domain remaining held for hours after the client
process that acquired them had exited. During `load_sim.py` testing, stopping the simulator with
Ctrl+C consistently left 1–N permits in the `active` state on the server, never returning to 0.
The condition resolved only after the permits had been held for 2+ hours.

---

## Root cause

### No gRPC-level keepalive configured on the server

The server was created with `grpc.NewServer()` and no options. When a client process dies without
sending a gRPC `GOAWAY` frame (e.g. SIGKILL, process crash, or a race during shutdown), the server
has no application-level mechanism to detect the dead connection. It falls back entirely on the OS
TCP keepalive defaults:

- First keepalive probe: after **2 hours** of idle
- 9 probes at 75 s intervals: ~11 additional minutes
- Total detection time: **~2 hours 11 minutes**

During that window, the `defer DisconnectClient(clientID)` in `PermitStream` never fires, so all
permits held by the dead client remain in `pool.held` and are never returned.

### `load_sim.py` shutdown race closes the channel before consumer threads release permits

The original shutdown sequence was:

```python
stop.set()
client.close()   # channel closed immediately
# main thread exits → daemon threads killed by OS
```

`stop.set()` signals consumers to stop looping, but threads mid-cycle (inside the
`with client.acquire(domain) as permit:` block, sleeping in the hold phase) are not interrupted.
`client.close()` immediately closes the gRPC channel, destroying the send queue before those
threads can send their `PermitReturn` messages. The main thread then exits, and the OS kills all
daemon threads. The server receives a TCP RST rather than a clean `GOAWAY`, triggering the 2-hour
TCP keepalive timeout described above.

---

## Troubleshooting steps taken

1. **Reviewed `PermitStream` defer** — confirmed `DisconnectClient` is correctly wired and does
   return all held permits for a client on stream close. Ruled out a server-side logic bug.

2. **Reviewed `pool.DisconnectClient`** — confirmed it returns held permits and cancels queued
   waiters correctly. Ruled out incorrect cleanup logic.

3. **Checked `main.go` gRPC server construction** — found `grpc.NewServer()` with zero options.
   No keepalive parameters configured. Identified as the primary server-side gap.

4. **Reviewed `load_sim.py` shutdown path** — found `client.close()` called immediately after
   `stop.set()` with no thread join. Identified as the proximate cause of the dirty disconnects
   seen during testing.

5. **Checked Python gRPC client keepalive** — `RequestAuthClient` also has no keepalive options,
   but this is secondary; fixing the server-side detection and the shutdown race resolves the
   observed issue.

---

## Fix

### `server/app/main.go` — configure gRPC keepalive on server startup

Added `keepalive.ServerParameters` and `keepalive.EnforcementPolicy` to the gRPC server. The
server now sends HTTP/2 PING frames to detect dead connections within ~40 seconds regardless of
TCP keepalive settings.

Before:
```go
grpcSrv := grpc.NewServer()
```

After:
```go
grpcSrv := grpc.NewServer(
    grpc.KeepaliveParams(keepalive.ServerParameters{
        MaxConnectionIdle: 5 * time.Minute,
        Time:              30 * time.Second,
        Timeout:           10 * time.Second,
    }),
    grpc.KeepaliveEnforcementPolicy(keepalive.EnforcementPolicy{
        MinTime:             10 * time.Second,
        PermitWithoutStream: true,
    }),
)
```

`PermitWithoutStream: true` is required so pings are sent even when a client is holding a permit
but has no active RPC streams in flight — the exact scenario during a long scrape hold.

Detection time reduced from ~2 hours 11 minutes to ~40 seconds (`Time` + `Timeout`).

### `tests/load_sim.py` — join consumer threads before closing the client

Added a `join` loop between `stop.set()` and `client.close()` so all in-flight permit cycles
complete cleanly before the channel is torn down.

Before:
```python
stop.set()
client.close()
```

After:
```python
stop.set()
for t in threads:
    t.join(timeout=10.0)
client.close()
```

The 10 s timeout per thread is a safety net for threads blocked waiting on a grant that may not
arrive (e.g. server under load). Under normal conditions threads finish well within the hold
time range.

---

## Files changed

- `server/app/main.go` — `main`
- `tests/load_sim.py` — `main`
