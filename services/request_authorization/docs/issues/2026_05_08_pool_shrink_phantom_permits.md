# Pool shrink creates phantom permits, doubling throughput after live config change

**Date:** 2026-05-08  
**Component:** `server/app/pool/pool.go` — `UpdateConfig`, `Return`  
**Severity:** High — rate limiting silently ineffective after live pool-size reduction

---

## Observed symptom

After changing a domain's config live from an open setting (pool=10, delay=1ms, multiplier=1x) to a
restrictive one (pool=1, delay=1000ms, multiplier=3x), the expected throughput was ~1 RPS but both
Grafana (`permit_issued_total` rate) and the load simulator client reported ~7.5 RPS — roughly
double what the new config should allow. The old config was yielding 17 RPS with 5 concurrent
workers.

---

## Root cause

### The pool invariant

At construction, the pool maintains:

```
available + len(held) == PoolSize
```

With pool=10 and 5 active workers: `held=5, available=5`.

### `UpdateConfig` does not adjust `available`

When a live config reload reduces `PoolSize` from 10 to 1, `UpdateConfig` replaces `p.config` but
leaves `p.available` unchanged:

```go
// pool.go — before fix
func (p *Pool) UpdateConfig(cfg Config) {
    p.mu.Lock()
    p.config = cfg   // PoolSize → 1
    p.mu.Unlock()    // available is still 5
    ...
}
```

### Workers immediately consume the phantom slots

`Acquire` checks only `p.available > 0` with no upper bound against `PoolSize`. After the config
change, each of the 5 workers returns its old permit and immediately re-acquires without any delay,
draining `available` from 5 to 0. This creates a second cohort of in-flight permits that are
completely invisible to the new pool-size constraint.

### Two cohorts → double throughput

This results in two parallel groups of AfterFuncs that independently service waiters every
`hold_time + delay` milliseconds:

- **Cohort A**: AfterFuncs from the pre-change holds, fires at t ≈ return_time + 1000ms  
- **Cohort B**: AfterFuncs from the phantom holds, fires at t ≈ return_time + hold_time + 1000ms

Each cohort cycles 5 workers at `5 / (hold_ms + 1000ms)`. With a measured hold of ~294ms:

```
2 cohorts × (5 / 1294ms) = 10 / 1294ms ≈ 7.7 RPS  ✓  (observed: 7.5 RPS)
```

### `Return`'s AfterFunc has no pool-size upper bound

Even if `available` were clamped at `UpdateConfig` time, the already-scheduled Cohort B AfterFuncs
would still fire later and unconditionally re-issue permits via `p.available++` (when no waiters are
present), re-inflating the pool back past the new `PoolSize`.

---

## Troubleshooting steps taken

1. **Verified there is only one domain and one load source** — ruled out the initial hypothesis that
   the Grafana `sum(rate(permit_issued_total[...]))` panel was aggregating other domains.

2. **Confirmed both client and server metrics agree** — the load simulator itself reported 7.5 RPS,
   ruling out a metric labelling or aggregation issue.

3. **Traced the pool invariant** — noted that `p.available` is set to `PoolSize` at construction
   but `UpdateConfig` only replaces `p.config`, not `p.available`.

4. **Modelled the two-cohort effect** — worked through the AfterFunc scheduling timeline to show
   that 5 phantom permits create a second parallel batch of 5 workers, exactly doubling the
   throughput and matching the 7.5 RPS figure.

5. **Identified the AfterFunc gap** — realised that even fixing `UpdateConfig` alone is
   insufficient; the already-queued AfterFuncs must also respect the new `PoolSize` or they will
   silently re-inflate `available`.

---

## Fix

### `UpdateConfig` — clamp `available` on pool shrink

```go
func (p *Pool) UpdateConfig(cfg Config) {
    p.mu.Lock()
    if maxAvail := cfg.PoolSize - len(p.held) - p.backoffCount; p.available > maxAvail {
        if maxAvail < 0 {
            maxAvail = 0
        }
        p.available = maxAvail
    }
    p.config = cfg
    p.mu.Unlock()
    p.backoff.UpdateConfig(...)
}
```

`maxAvail` is the number of slots not already consumed by held permits or pending AfterFuncs. Any
surplus `available` is discarded immediately.

### `Return` AfterFunc — respect current `PoolSize` before re-issuing

```go
time.AfterFunc(delay, func() {
    p.mu.Lock()
    p.backoffCount--
    inFlight := len(p.held) + p.backoffCount
    if len(p.waiters) > 0 && inFlight < p.config.PoolSize {
        // Service next waiter — we are within the current pool budget.
        ...
    } else if len(p.waiters) == 0 && p.available < p.config.PoolSize {
        p.available++
        p.mu.Unlock()
    } else {
        // Excess permit from a pool shrink — drain without re-issuing.
        p.mu.Unlock()
    }
})
```

`inFlight` counts permits that are currently held plus permits whose delay is still running.
Together they represent the full "budget" consumed by the pool at the moment the AfterFunc fires.
If that budget already meets or exceeds the new `PoolSize`, the permit is dropped rather than
handed to a waiter, naturally draining the excess cohort over one full cycle.

---

## Files changed

- `server/app/pool/pool.go` — `UpdateConfig` and `Return`
