# TODO

Backlog imported from the retired todo store, 2026-07-06.

## Urgent

- [ ] **Replace scrape-stack Kubernetes deployment with prod Helm chart** — Tear down the existing scrape-stack deployment in Kubernetes and replace it with the production Helm chart. See notes: scrape-stack operations guide.
- [ ] **Migrate scrape-stack services to AiStor S3 storage** — Move the scrape-stack services to the AiStor S3-compatible storage on 192.168.0.10 so object storage is centralized off the current local backends.

## High

- [ ] **Test vidcache deduplication end-to-end** — Do full testing around the vidcache deduplication requirement and determine whether the current bug is true duplicate storage or duplicate metadata entries pointing at the same backend file.
- [ ] **Split request-auth into sync and async client packages** — Split the request-auth library into separate sync and async packages so HTTPX-based scrapers can use the same permit and rate-limit infrastructure cleanly.

## Medium

- [ ] **Add optional Kubernetes VPN proxy wiring for scraper deployments** — Add a deployment option so scraper workloads in Kubernetes can be routed through the existing VPN proxy when needed.
- [ ] **Add S3-compatible backend support to vidcache** — Update vidcache so it can use an S3-compatible object store instead of only supporting the local filesystem backend.
- [ ] **Test imgcache deduplication end-to-end** — Do full testing around the imgcache deduplication requirement and verify it behaves as expected under repeated uploads and retrievals.
- [ ] **Test filecache deduplication end-to-end** — Do full testing around the filecache deduplication requirement and verify repeated uploads and server-side downloads resolve to a single deduplicated backend object.
