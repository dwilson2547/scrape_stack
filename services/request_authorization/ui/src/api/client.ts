import type {
  Bucket, BucketCreate, BucketDetail, BucketUpdate,
  Config,
  Domain, DomainCreate, DomainUpdate,
  RobotsTxt,
  StatusResponse,
} from './types'

const BASE = '/api'

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  domains: {
    list: () => req<Domain[]>('GET', '/domains'),
    create: (body: DomainCreate) => req<Domain>('POST', '/domains', body),
    get: (hostname: string) => req<Domain>('GET', `/domains/${hostname}`),
    update: (hostname: string, body: DomainUpdate) => req<Domain>('PATCH', `/domains/${hostname}`, body),
    delete: (hostname: string) => req<void>('DELETE', `/domains/${hostname}`),
  },
  buckets: {
    list: () => req<Bucket[]>('GET', '/buckets'),
    create: (body: BucketCreate) => req<Bucket>('POST', '/buckets', body),
    get: (name: string) => req<BucketDetail>('GET', `/buckets/${name}`),
    update: (name: string, body: BucketUpdate) => req<Bucket>('PATCH', `/buckets/${name}`, body),
    delete: (name: string) => req<void>('DELETE', `/buckets/${name}`),
    addDomain: (name: string, hostname: string) =>
      req<Bucket>('POST', `/buckets/${name}/domains`, { hostname }),
    removeDomain: (name: string, hostname: string) =>
      req<void>('DELETE', `/buckets/${name}/domains/${hostname}`),
  },
  robots: {
    get: (hostname: string) => req<RobotsTxt>('GET', `/robots/${hostname}`),
    override: (hostname: string, override_delay_ms: number) =>
      req<RobotsTxt>('POST', `/robots/${hostname}/override`, { override_delay_ms }),
    revert: (hostname: string) => req<RobotsTxt>('POST', `/robots/${hostname}/revert`),
    refresh: (hostname: string) => req<RobotsTxt>('POST', `/robots/${hostname}/refresh`),
  },
  config: {
    get: () => req<Config>('GET', '/config'),
    update: (body: Partial<Config>) => req<Config>('PATCH', '/config', body),
  },
  status: {
    get: () => req<StatusResponse>('GET', '/status'),
  },
}
