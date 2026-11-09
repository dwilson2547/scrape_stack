import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Bucket, BucketCreate, BucketDetail, BucketUpdate } from '../api/types'

export function Buckets() {
  const [buckets, setBuckets] = useState<Bucket[]>([])
  const [selected, setSelected] = useState<BucketDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Bucket | null>(null)
  const [addDomain, setAddDomain] = useState('')

  async function load() {
    try {
      setBuckets(await api.buckets.list())
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function loadDetail(name: string) {
    try {
      setSelected(await api.buckets.get(name))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(body: BucketCreate) {
    await api.buckets.create(body)
    setCreating(false)
    load()
  }

  async function handleUpdate(name: string, body: BucketUpdate) {
    await api.buckets.update(name, body)
    setEditing(null)
    load()
    if (selected?.name === name) loadDetail(name)
  }

  async function handleDelete(name: string) {
    if (!confirm(`Delete bucket "${name}"?`)) return
    await api.buckets.delete(name)
    if (selected?.name === name) setSelected(null)
    load()
  }

  async function handleAddDomain(bucketName: string) {
    if (!addDomain.trim()) return
    await api.buckets.addDomain(bucketName, addDomain.trim())
    setAddDomain('')
    loadDetail(bucketName)
  }

  async function handleRemoveDomain(bucketName: string, hostname: string) {
    await api.buckets.removeDomain(bucketName, hostname)
    loadDetail(bucketName)
  }

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Buckets</h1>
        <button style={styles.btn} onClick={() => setCreating(true)}>+ New Bucket</button>
      </div>
      {error && <div style={styles.error}>{error}</div>}
      {creating && <BucketForm onSubmit={handleCreate} onCancel={() => setCreating(false)} />}
      {editing && (
        <BucketForm
          initial={editing}
          onSubmit={(b) => handleUpdate(editing.name, b)}
          onCancel={() => setEditing(null)}
        />
      )}
      <div style={styles.layout}>
        <div style={styles.list}>
          {buckets.map(b => (
            <div
              key={b.id}
              style={{ ...styles.listItem, ...(selected?.name === b.name ? styles.listItemActive : {}) }}
              onClick={() => loadDetail(b.name)}
            >
              <span style={styles.listName}>{b.name}</span>
              <div style={styles.listActions}>
                <button style={styles.btnSm} onClick={e => { e.stopPropagation(); setEditing(b) }}>Edit</button>
                <button style={{ ...styles.btnSm, ...styles.btnDanger }} onClick={e => { e.stopPropagation(); handleDelete(b.name) }}>Del</button>
              </div>
            </div>
          ))}
          {buckets.length === 0 && <p style={styles.empty}>No buckets yet.</p>}
        </div>

        {selected && (
          <div style={styles.detail}>
            <h2 style={styles.detailTitle}>{selected.name}</h2>
            <div style={styles.configGrid}>
              <ConfigVal label="Pool Size" value={selected.pool_size} />
              <ConfigVal label="Base Delay" value={selected.base_delay_ms != null ? `${selected.base_delay_ms} ms` : null} />
              <ConfigVal label="Multiplier" value={selected.backoff_multiplier} />
              <ConfigVal label="Max Delay" value={selected.max_delay_ms != null ? `${selected.max_delay_ms} ms` : null} />
              <ConfigVal label="Recovery" value={selected.recovery_threshold} />
            </div>
            <h3 style={styles.sectionTitle}>Domains ({selected.domains.length})</h3>
            <div style={styles.addRow}>
              <input
                style={styles.input}
                value={addDomain}
                onChange={e => setAddDomain(e.target.value)}
                placeholder="example.com"
                onKeyDown={e => e.key === 'Enter' && handleAddDomain(selected.name)}
              />
              <button style={styles.btn} onClick={() => handleAddDomain(selected.name)}>Add</button>
            </div>
            {selected.domains.map(d => (
              <div key={d.id} style={styles.domainRow}>
                <span style={styles.domainName}>{d.hostname}</span>
                <button
                  style={{ ...styles.btnSm, ...styles.btnDanger }}
                  onClick={() => handleRemoveDomain(selected.name, d.hostname)}
                >Remove</button>
              </div>
            ))}
            {selected.domains.length === 0 && <p style={styles.empty}>No domains in this bucket.</p>}
          </div>
        )}
      </div>
    </div>
  )
}

function BucketForm({ initial, onSubmit, onCancel }: {
  initial?: Bucket
  onSubmit: (body: BucketCreate) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [poolSize, setPoolSize] = useState(initial?.pool_size?.toString() ?? '')
  const [baseDelay, setBaseDelay] = useState(initial?.base_delay_ms?.toString() ?? '')
  const [multiplier, setMultiplier] = useState(initial?.backoff_multiplier?.toString() ?? '')
  const [maxDelay, setMaxDelay] = useState(initial?.max_delay_ms?.toString() ?? '')
  const [recovery, setRecovery] = useState(initial?.recovery_threshold?.toString() ?? '')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({
      name,
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
        <label style={styles.label}>Name</label>
        <input style={styles.input} value={name} onChange={e => setName(e.target.value)} required disabled={!!initial} />
      </div>
      <div style={styles.formGrid}>
        {[
          ['Pool Size', poolSize, setPoolSize],
          ['Base Delay (ms)', baseDelay, setBaseDelay],
          ['Multiplier', multiplier, setMultiplier],
          ['Max Delay (ms)', maxDelay, setMaxDelay],
          ['Recovery Threshold', recovery, setRecovery],
        ].map(([label, val, set]) => (
          <div key={label as string}>
            <label style={styles.label}>{label as string}</label>
            <input style={styles.input} type="number" value={val as string}
              onChange={e => (set as (v: string) => void)(e.target.value)} placeholder="inherit" />
          </div>
        ))}
      </div>
      <div style={styles.formActions}>
        <button type="submit" style={styles.btn}>{initial ? 'Update' : 'Create'}</button>
        <button type="button" style={styles.btnSecondary} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

function ConfigVal({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <div style={styles.label}>{label}</div>
      <div style={{ color: value != null ? '#cdd6f4' : '#6c7086', fontSize: '0.9rem' }}>
        {value ?? 'inherit'}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: '1.5rem' },
  header: { display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' },
  title: { margin: 0, color: '#cdd6f4', fontSize: '1.4rem' },
  error: { background: '#45475a', color: '#f38ba8', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' },
  layout: { display: 'grid', gridTemplateColumns: '260px 1fr', gap: '1.5rem', alignItems: 'start' },
  list: { background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8, overflow: 'hidden' },
  listItem: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.65rem 1rem', cursor: 'pointer', borderBottom: '1px solid #313244' },
  listItemActive: { background: '#313244' },
  listName: { color: '#cdd6f4', fontSize: '0.9rem' },
  listActions: { display: 'flex', gap: '0.25rem' },
  detail: { background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8, padding: '1rem' },
  detailTitle: { margin: '0 0 1rem', color: '#89b4fa', fontSize: '1.1rem' },
  configGrid: { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' },
  sectionTitle: { color: '#a6adc8', fontSize: '0.85rem', margin: '0 0 0.5rem', textTransform: 'uppercase' },
  addRow: { display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' },
  domainRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.4rem 0', borderBottom: '1px solid #313244' },
  domainName: { color: '#cdd6f4', fontSize: '0.9rem' },
  empty: { color: '#6c7086', fontSize: '0.85rem', margin: '0.5rem 0' },
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
