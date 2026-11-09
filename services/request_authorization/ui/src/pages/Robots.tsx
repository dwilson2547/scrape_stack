import { useState } from 'react'
import { api } from '../api/client'
import type { RobotsTxt } from '../api/types'

export function Robots() {
  const [hostname, setHostname] = useState('')
  const [entry, setEntry] = useState<RobotsTxt | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [overrideMs, setOverrideMs] = useState('')

  async function lookup() {
    if (!hostname.trim()) return
    setError(null)
    setEntry(null)
    try {
      setEntry(await api.robots.get(hostname.trim()))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleOverride() {
    if (!entry || !overrideMs) return
    try {
      setEntry(await api.robots.override(entry.hostname, Number(overrideMs)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleRevert() {
    if (!entry) return
    try {
      setEntry(await api.robots.revert(entry.hostname))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleRefresh() {
    if (!entry) return
    try {
      setEntry(await api.robots.refresh(entry.hostname))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Robots.txt Cache</h1>
      <div style={styles.lookupRow}>
        <input
          style={styles.input}
          value={hostname}
          onChange={e => setHostname(e.target.value)}
          placeholder="example.com"
          onKeyDown={e => e.key === 'Enter' && lookup()}
        />
        <button style={styles.btn} onClick={lookup}>Look up</button>
      </div>
      {error && <div style={styles.error}>{error}</div>}
      {entry && (
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.cardDomain}>{entry.hostname}</span>
            {entry.is_overridden && <span style={styles.badge}>Overridden</span>}
            {entry.not_found && <span style={{ ...styles.badge, ...styles.badgeWarn }}>No robots.txt</span>}
          </div>
          <div style={styles.grid}>
            <Field label="Crawl Delay" value={entry.crawl_delay_ms != null ? `${entry.crawl_delay_ms} ms` : '—'} />
            <Field label="Override Delay" value={entry.override_delay_ms != null ? `${entry.override_delay_ms} ms` : '—'} />
            <Field label="Fetched At" value={entry.fetched_at ? new Date(entry.fetched_at).toLocaleString() : '—'} />
          </div>
          <div style={styles.actions}>
            <div style={styles.overrideRow}>
              <input
                style={{ ...styles.input, width: 160 }}
                type="number"
                value={overrideMs}
                onChange={e => setOverrideMs(e.target.value)}
                placeholder="Override delay (ms)"
              />
              <button style={styles.btn} onClick={handleOverride}>Set Override</button>
            </div>
            {entry.is_overridden && (
              <button style={styles.btnSecondary} onClick={handleRevert}>Revert to robots.txt</button>
            )}
            <button style={styles.btnSecondary} onClick={handleRefresh}>Refresh from web</button>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={styles.label}>{label}</div>
      <div style={styles.value}>{value}</div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: '1.5rem', maxWidth: 680 },
  title: { margin: '0 0 1.25rem', color: '#cdd6f4', fontSize: '1.4rem' },
  lookupRow: { display: 'flex', gap: '0.5rem', marginBottom: '1rem' },
  error: { background: '#45475a', color: '#f38ba8', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' },
  card: { background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8, padding: '1rem' },
  cardHeader: { display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' },
  cardDomain: { fontWeight: 600, color: '#89b4fa', fontSize: '1rem' },
  badge: { fontSize: '0.7rem', background: '#89b4fa', color: '#1e1e2e', borderRadius: 4, padding: '0.1rem 0.4rem', fontWeight: 700 },
  badgeWarn: { background: '#fab387', color: '#1e1e2e' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' },
  label: { fontSize: '0.75rem', color: '#6c7086', marginBottom: '0.2rem' },
  value: { color: '#cdd6f4', fontSize: '0.9rem' },
  actions: { display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' },
  overrideRow: { display: 'flex', gap: '0.5rem', alignItems: 'center' },
  input: { padding: '0.4rem 0.6rem', background: '#313244', border: '1px solid #45475a', borderRadius: 4, color: '#cdd6f4', fontSize: '0.9rem', width: '100%', boxSizing: 'border-box' },
  btn: { padding: '0.4rem 1rem', background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem', whiteSpace: 'nowrap' },
  btnSecondary: { padding: '0.4rem 0.75rem', background: '#313244', color: '#cdd6f4', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.85rem', whiteSpace: 'nowrap' },
}
