import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { Dashboard } from './pages/Dashboard'
import { Domains } from './pages/Domains'
import { Buckets } from './pages/Buckets'
import { Robots } from './pages/Robots'
import { Config } from './pages/Config'

export function App() {
  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', background: '#181825', color: '#cdd6f4', fontFamily: 'system-ui, sans-serif' }}>
        <NavBar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/domains" element={<Domains />} />
          <Route path="/buckets" element={<Buckets />} />
          <Route path="/robots" element={<Robots />} />
          <Route path="/config" element={<Config />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
