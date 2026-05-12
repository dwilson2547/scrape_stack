# scrape-stack Helm chart

Deploys the scrape stack Kubernetes resources as a chart, without modifying the legacy `k8s/` directory.

## Usage

```bash
helm upgrade --install scrape-stack ./helm/scrape-stack -n scrape-stack --create-namespace
```

## Common toggles

- `ingress.enabled` (default: `true`)
- `requestAuth.externalGrpc.enabled` (default: `true`)
- `monitoring.otelCollector.enabled` (default: `true`)
- `monitoring.serviceMonitor.enabled` (default: `false`)
- `monitoring.grafanaIngress.enabled` (default: `false`)
- `dnsLocal.enabled` (default: `false`)

## Domain + prefix templating

Ingress hosts and `dnsLocal` zone records are generated from:

- `domains.stack` (default: `scrapestack.local`)
- `domains.monitoring` (default: `monitoring.local`)
- `ingress.prefixes.*` (service host prefixes)

For example, `ingress.prefixes.webcache=webcache` + `domains.stack=scrapestack.local`
renders `webcache.scrapestack.local` in both ingress and DNS config.

Set credentials and storage class overrides in your own values file before production use.
