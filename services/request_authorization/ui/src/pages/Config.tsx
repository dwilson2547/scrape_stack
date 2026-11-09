import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Config } from '../api/types'

const FIELDS: { key: keyof Config; label: string; unit?: string }[] = [
  { key: 'default_pool_size', label: 'Default Pool Size' },
  { key: 'default_base_delay_ms', label: 'Default Base Delay', unit: 'ms' },
  { key: 'default_backoff_multiplier', label: 'Backoff Multiplier' },
  { key: 'default_max_delay_ms', label: 'Max Delay', unit: 'ms' },
  { key: 'default_recovery_threshold', label: 'Recovery Threshold' },
  { key: 'robots_txt_ttl_hours', label: 'Robots.txt TTL', unit: 'hr' },
  { key: 'robots_txt_retry_hours', label: 'Robots.txt Retry', unit: 'hr' },
  { key: 'config_reload_interval_seconds', label: 'Config Reload Interval', unit: 's' },
]

export function Config() {
  const [config, setConfig] = useState<Config | null>(null)
  const [draft, setDraft] = useState<Partial<Config>>({})
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.config.get().then(c => { setConfig(c); setDraft(c) }).catch(e => setError((e as Error).message))
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const updated = await api.config.update(draft)
      setConfig(updated)
      setDraft(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!config) return <div style={styles.page}><p style={{ color: '#6c7086' }}>Loading…</p></div>

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Global Config</h1>
      <p style={styles.hint}>These are the defaults applied when no domain or bucket override is set.</p>
      {error && <div style={styles.error}>{error}</div>}
      <form onSubmit={handleSave} style={styles.form}>
        <div style={styles.grid}>
          {FIELDS.map(({ key, label, unit }) => (
            <div key={key}>
              <label style={styles.label}>{label}{unit ? ` (${unit})` : ''}</label>
              <input
                style={styles.input}
                type="number"
                step="any"
                value={(draft[key] as number | undefined) ?? ''}
                onChange={e => setDraft(d => ({ ...d, [key]: e.target.value === '' ? undefined : Number(e.target.value) }))}
              />
            </div>
          ))}
        </div>
        <div style={styles.actions}>
          <button type="submit" style={styles.btn}>Save</button>
          {saved && <span style={styles.savedMsg}>Saved!</span>}
        </div>
      </form>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: '1.5rem', maxWidth: 720 },
  title: { margin: '0 0 0.5rem', color: '#cdd6f4', fontSize: '1.4rem' },
  hint: { color: '#6c7086', fontSize: '0.85rem', margin: '0 0 1.25rem' },
  error: { background: '#45475a', color: '#f38ba8', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' },
  form: { background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8, padding: '1.25rem' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1rem' },
  label: { display: 'block', fontSize: '0.75rem', color: '#6c7086', marginBottom: '0.25rem' },
  input: { width: '100%', boxSizing: 'border-box', padding: '0.4rem 0.6rem', background: '#313244', border: '1px solid #45475a', borderRadius: 4, color: '#cdd6f4', fontSize: '0.9rem' },
  actions: { display: 'flex', alignItems: 'center', gap: '1rem' },
  btn: { padding: '0.4rem 1.25rem', background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' },
  savedMsg: { color: '#a6e3a1', fontSize: '0.85rem' },
}
