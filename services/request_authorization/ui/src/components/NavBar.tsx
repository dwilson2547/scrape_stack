import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/domains', label: 'Domains' },
  { to: '/buckets', label: 'Buckets' },
  { to: '/robots', label: 'Robots.txt' },
  { to: '/config', label: 'Config' },
]

export function NavBar() {
  return (
    <nav style={styles.nav}>
      <span style={styles.brand}>Request Auth</span>
      <div style={styles.links}>
        {links.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({ ...styles.link, ...(isActive ? styles.active : {}) })}
          >
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

const styles: Record<string, React.CSSProperties> = {
  nav: {
    display: 'flex',
    alignItems: 'center',
    gap: '2rem',
    padding: '0.75rem 1.5rem',
    background: '#1e1e2e',
    borderBottom: '1px solid #313244',
  },
  brand: { fontWeight: 700, fontSize: '1.1rem', color: '#cdd6f4' },
  links: { display: 'flex', gap: '1.25rem' },
  link: { color: '#a6adc8', textDecoration: 'none', fontSize: '0.9rem' },
  active: { color: '#89b4fa', fontWeight: 600 },
}
