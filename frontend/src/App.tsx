import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { fetchSummary, supabase } from './api'
import { DAMap } from './Map'
import { DetailPanel } from './DetailPanel'
import { Login } from './Login'
import type { DASummary } from './types'
import './styles.css'

export function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const [summary, setSummary] = useState<DASummary[]>([])
  const [metric, setMetric] = useState<'coverage' | 'support'>('coverage')
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])

  // All 161 DAs in one request -- a few KB, and it means the manager sees where
  // canvassing is thin without clicking through every area.
  useEffect(() => {
    if (!session) return
    fetchSummary().then(setSummary).catch((e) => setError(String(e)))
  }, [session])

  if (!ready) return null
  if (!session) return <Login />

  const totals = summary.reduce(
    (acc, da) => ({
      knocked: acc.knocked + da.doors_knocked,
      dwellings: acc.dwellings + da.total_private_dwellings,
    }),
    { knocked: 0, dwellings: 0 },
  )

  return (
    <div className="layout">
      <header>
        <strong>Ward 11 — University–Rosedale</strong>
        <div className="toggle">
          <button
            className={metric === 'coverage' ? 'active' : ''}
            onClick={() => setMetric('coverage')}
          >
            Coverage
          </button>
          <button
            className={metric === 'support' ? 'active' : ''}
            onClick={() => setMetric('support')}
          >
            Support
          </button>
        </div>
        <span className="muted small">
          {totals.knocked.toLocaleString()} doors knocked ·{' '}
          {totals.dwellings > 0
            ? `${((100 * totals.knocked) / totals.dwellings).toFixed(1)}% of dwellings`
            : '—'}
        </span>
        <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </header>

      <main>
        <div className="map-wrap">
          <DAMap
            summary={summary}
            metric={metric}
            selected={selected}
            onSelect={setSelected}
          />
        </div>
        <aside>
          {error && <p className="error">{error}</p>}
          {selected ? (
            <DetailPanel dauid={selected} />
          ) : (
            <div className="panel">
              <p className="muted">Select a dissemination area on the map.</p>
            </div>
          )}
        </aside>
      </main>
    </div>
  )
}
