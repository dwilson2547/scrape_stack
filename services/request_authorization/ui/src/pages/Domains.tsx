import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Domain, DomainCreate, DomainUpdate } from '../api/types'

export function Domains() {
  const [domains, setDomains] = useState<Domain[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Domain | null>(null)
  const [creating, setCreating] = useState(false)

  async function load() {
    try {
      setDomains(await api.domains.list())
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => { load() }, [])

  async function handleDelete(hostname: string) {
    if (!confirm(`Delete ${hostname}?`)) return
    await api.domains.delete(hostname)
    load()
  }

  async function handleCreate(body: DomainCreate) {
    await api.domains.create(body)
    setCreating(false)
    load()
  }

  async function handleUpdate(hostname: string, body: DomainUpdate) {
    await api.domains.update(hostname, body)
    setEditing(null)
    load()
  }

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Domains</h1>
        <button style={styles.btn} onClick={() => setCreating(true)}>+ Add Domain</button>
      </div>
      {error && <div style={styles.error}>{error}</div>}
      {creating && (
        <DomainForm
          onSubmit={handleCreate}
          onCancel={() => setCreating(false)}
        />
      )}
      {editing && (
        <DomainForm
          initial={editing}
          onSubmit={(body) => handleUpdate(editing.hostname, body)}
          onCancel={() => setEditing(null)}
        />
      )}
      <table style={styles.table}>
        <thead>
          <tr>
            {['Hostname', 'Pool', 'Base Delay', 'Multiplier', 'Max Delay', 'Recovery', 'Bucket', ''].map(h => (
              <th key={h} style={styles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {domains.map(d => (
            <tr key={d.id} style={styles.tr}>
              <td style={styles.td}>{d.hostname}</td>
              <td style={styles.td}>{d.pool_size ?? '—'}</td>
              <td style={styles.td}>{d.base_delay_ms != null ? `${d.base_delay_ms} ms` : '—'}</td>
              <td style={styles.td}>{d.backoff_multiplier ?? '—'}</td>
              <td style={styles.td}>{d.max_delay_ms != null ? `${d.max_delay_ms} ms` : '—'}</td>
              <td style={styles.td}>{d.recovery_threshold ?? '—'}</td>
              <td style={styles.td}>{d.bucket_id ?? '—'}</td>
              <td style={styles.td}>
                <button style={styles.btnSm} onClick={() => setEditing(d)}>Edit</button>
                {' '}
                <button style={{ ...styles.btnSm, ...styles.btnDanger }} onClick={() => handleDelete(d.hostname)}>Del</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DomainForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: Domain
  onSubmit: (body: DomainCreate) => void
  onCancel: () => void
}) {
  const [hostname, setHostname] = useState(initial?.hostname ?? '')
  const [poolSize, setPoolSize] = useState(initial?.pool_size?.toString() ?? '')
  const [baseDelay, setBaseDelay] = useState(initial?.base_delay_ms?.toString() ?? '')
  const [multiplier, setMultiplier] = useState(initial?.backoff_multiplier?.toString() ?? '')
  const [maxDelay, setMaxDelay] = useState(initial?.max_delay_ms?.toString() ?? '')
  const [recovery, setRecovery] = useState(initial?.recovery_threshold?.toString() ?? '')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({
      hostname,
      pool_size: poolSize ? Number(poolSize) : null,
      base_delay_ms: baseDelay ? Number(baseDelay) : null,
      backoff_multiplier: multiplier ? Number(multiplier) : null,
      max_delay_ms: maxDelay ? Number(maxDelay) : null,
      recovery_threshold: recovery ? Number(recovery) : null,
    })
  }

  return (
    <form onSubmit={submit} style={styles.form}>
      <div style={styles.formRow}>
        <label style={styles.label}>Hostname</label>
        <input style={styles.input} value={hostname} onChange={e => setHostname(e.target.value)}
          placeholder="example.com" required disabled={!!initial} />
      </div>
      <div style={styles.formGrid}>
        <Field label="Pool Size" value={poolSize} onChange={setPoolSize} placeholder="inherit" />
        <Field label="Base Delay (ms)" value={baseDelay} onChange={setBaseDelay} placeholder="inherit" />
        <Field label="Multiplier" value={multiplier} onChange={setMultiplier} placeholder="inherit" />
        <Field label="Max Delay (ms)" value={maxDelay} onChange={setMaxDelay} placeholder="inherit" />
        <Field label="Recovery Threshold" value={recovery} onChange={setRecovery} placeholder="inherit" />
      </div>
      <div style={styles.formActions}>
        <button type="submit" style={styles.btn}>{initial ? 'Update' : 'Create'}</button>
        <button type="button" style={styles.btnSecondary} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

function Field({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div>
      <label style={styles.label}>{label}</label>
      <input style={styles.input} type="number" value={value}
        onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: '1.5rem' },
  header: { display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' },
  title: { margin: 0, color: '#cdd6f4', fontSize: '1.4rem' },
  error: { background: '#45475a', color: '#f38ba8', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { textAlign: 'left', padding: '0.5rem 0.75rem', color: '#6c7086', fontSize: '0.8rem', borderBottom: '1px solid #313244' },
  tr: { borderBottom: '1px solid #1e1e2e' },
  td: { padding: '0.5rem 0.75rem', color: '#cdd6f4', fontSize: '0.9rem' },
  form: { background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8, padding: '1rem', marginBottom: '1.25rem' },
  formRow: { marginBottom: '0.75rem' },
  formGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' },
  formActions: { display: 'flex', gap: '0.5rem' },
  label: { display: 'block', fontSize: '0.75rem', color: '#6c7086', marginBottom: '0.25rem' },
  input: { width: '100%', boxSizing: 'border-box', padding: '0.4rem 0.6rem', background: '#313244', border: '1px solid #45475a', borderRadius: 4, color: '#cdd6f4', fontSize: '0.9rem' },
  btn: { padding: '0.4rem 1rem', background: '#89b4fa', color: '#1e1e2e', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' },
  btnSecondary: { padding: '0.4rem 1rem', background: '#313244', color: '#cdd6f4', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.85rem' },
  btnSm: { padding: '0.2rem 0.5rem', background: '#313244', color: '#cdd6f4', border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: '0.8rem' },
  btnDanger: { color: '#f38ba8' },
}
