import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { PoolStatus } from '../api/types'

export function Dashboard() {
  const [pools, setPools] = useState<PoolStatus[]>([])
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchStatus() {
    try {
      const data = await api.status.get()
      setPools(data.pools)
      setLastUpdated(new Date())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    fetchStatus()
    intervalRef.current = setInterval(fetchStatus, 3000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [])

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Live Pool Status</h1>
        {lastUpdated && (
          <span style={styles.updated}>Updated {lastUpdated.toLocaleTimeString()}</span>
        )}
      </div>
      {error && <div style={styles.error}>{error}</div>}
      {pools.length === 0 && !error && (
        <p style={styles.empty}>No active pools — server may be offline.</p>
      )}
      <div style={styles.grid}>
        {pools.map((p) => (
          <PoolCard key={p.domain} pool={p} />
        ))}
      </div>
    </div>
  )
}

function PoolCard({ pool }: { pool: PoolStatus }) {
  const utilization = pool.pool_size > 0 ? pool.active / pool.pool_size : 0
  const barColor = utilization > 0.8 ? '#f38ba8' : utilization > 0.5 ? '#fab387' : '#a6e3a1'

  return (
    <div style={styles.card}>
      <div style={styles.cardDomain}>{pool.domain}</div>
      <div style={styles.cardStats}>
        <Stat label="Active" value={`${pool.active} / ${pool.pool_size}`} />
        <Stat label="Queued" value={pool.queued} />
        <Stat label="Delay" value={`${pool.current_delay_ms} ms`} />
        <Stat label="Successes" value={pool.consecutive_successes} />
      </div>
      <div style={styles.barTrack}>
        <div style={{ ...styles.barFill, width: `${utilization * 100}%`, background: barColor }} />
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={styles.stat}>
      <span style={styles.statLabel}>{label}</span>
      <span style={styles.statValue}>{value}</span>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: '1.5rem' },
  header: { display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '1.25rem' },
  title: { margin: 0, color: '#cdd6f4', fontSize: '1.4rem' },
  updated: { color: '#6c7086', fontSize: '0.8rem' },
  error: { background: '#45475a', color: '#f38ba8', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem' },
  empty: { color: '#6c7086' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' },
  card: { background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8, padding: '1rem' },
  cardDomain: { fontWeight: 600, color: '#89b4fa', marginBottom: '0.75rem', wordBreak: 'break-all' },
  cardStats: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' },
  stat: { display: 'flex', flexDirection: 'column' },
  statLabel: { fontSize: '0.7rem', color: '#6c7086', textTransform: 'uppercase' },
  statValue: { fontSize: '0.95rem', color: '#cdd6f4' },
  barTrack: { height: 4, background: '#313244', borderRadius: 2 },
  barFill: { height: '100%', borderRadius: 2, transition: 'width 0.4s ease' },
}
