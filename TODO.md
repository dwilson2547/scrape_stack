# TODO

Backlog imported from the retired todo store, 2026-07-06.

## Urgent

- [x] **Replace scrape-stack Kubernetes deployment with prod Helm chart** — Done (verified 2026-10-11): every Deployment/Service/Ingress in namespace `scrape-stack` is owned by Argo app `scrape-stack`, rendered from `helm/scrape-stack` on `main`, Synced/Healthy.
- [ ] **Migrate scrape-stack services to AiStor S3 storage** — Move the scrape-stack services to the AiStor S3-compatible storage on 192.168.0.10 so object storage is centralized off the current local backends.

## High

- [ ] **Bump the other scrapers to request-auth client 0.1.4** — ~37 projects still pin `dwilson2547-request-auth-client==0.1.3`, whose stream never reconnects after the server restarts (GOAWAY), so a mid-run request-auth restart hangs the scraper (harley-20261030162403, 2026-10-30). Only parts-direct is on 0.1.4. Until done, restart request-auth only when no scraper is running.
- [ ] **Back off on 403 and 503, not only 429** — `pool/backoff.go` reacts only to 429 and 2xx decays it, so Cloudflare blocks (403) and overload (503) never slow a domain down. Decide how hard each should back off (a 403 burst is usually a ban on the exit, not a rate).
- [ ] **Test vidcache deduplication end-to-end** — Do full testing around the vidcache deduplication requirement and determine whether the current bug is true duplicate storage or duplicate metadata entries pointing at the same backend file.
- [ ] **Split request-auth into sync and async client packages** — Split the request-auth library into separate sync and async packages so HTTPX-based scrapers can use the same permit and rate-limit infrastructure cleanly.

## Medium

- [ ] **Jitter on request-auth delays** — permits are paced on a fixed base delay, so the request cadence is regular; add random jitter so it looks less machine-like to Cloudflare.
- [ ] **Sync `services/request_authorization/grafana-dashboard.json` with the provisioned dashboard** — the live copy in infra/cluster-config (`monitoring/manifests/scrape-stack-dashboards.yaml`, f35e6a8) now filters on `exported_job="$job"`; the repo copy still says `job=`. Prometheus scrapes the collector, so `job` is always `otel-collector`.
- [ ] **Request-auth UI: live pool cards still shuffle** — server `AllStatuses()` and the Dashboard both sort by domain now (4a614bf), UI rolled out 2026-10-12, but the user still sees cards jump on refresh. Prod request-auth-server not restarted yet (scrapers were running), so the server-side sort isn't live; re-check after a restart before digging further.
- [ ] **Add optional Kubernetes VPN proxy wiring for scraper deployments** — Add a deployment option so scraper workloads in Kubernetes can be routed through the existing VPN proxy when needed.
- [ ] **Add S3-compatible backend support to vidcache** — Update vidcache so it can use an S3-compatible object store instead of only supporting the local filesystem backend.
- [ ] **Test imgcache deduplication end-to-end** — Do full testing around the imgcache deduplication requirement and verify it behaves as expected under repeated uploads and retrievals.
- [ ] **Test filecache deduplication end-to-end** — Do full testing around the filecache deduplication requirement and verify repeated uploads and server-side downloads resolve to a single deduplicated backend object.
