import { useEffect, useState, type ReactNode } from 'react'
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { fetchDetail, fetchVoters } from './api'
import { SUPPORT_COLORS, SUPPORT_LABELS, type DADetail, type Voter } from './types'

const OUTCOME_COLORS = ['#2563eb', '#0891b2', '#ca8a04', '#dc2626', '#7c3aed', '#0f766e', '#a1a1aa']

/** Tall enough that the slice labels, which Recharts draws outside the pie,
 *  are not clipped above and below it. */
const PIE_HEIGHT = 300
const PIE_RADIUS = 80

/** Pie charts stop being readable past a handful of slices. The outcome tail is
 *  very long and very thin -- "No Answer" and "Answered" alone are ~99% of rows --
 *  so everything past the top few is folded into one bucket. */
function topN<T extends { attempts: number }>(rows: T[], n: number, label: (r: T) => string) {
  const sorted = [...rows].sort((a, b) => b.attempts - a.attempts)
  const head = sorted.slice(0, n).map((r) => ({ name: label(r), value: r.attempts }))
  const tail = sorted.slice(n).reduce((sum, r) => sum + r.attempts, 0)
  return tail > 0 ? [...head, { name: 'Other', value: tail }] : head
}

export function DetailPanel({ dauid }: { dauid: string }) {
  const [detail, setDetail] = useState<DADetail | null>(null)
  const [voters, setVoters] = useState<Voter[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingVoters, setLoadingVoters] = useState(false)

  useEffect(() => {
    setDetail(null)
    setVoters(null)
    setError(null)
    fetchDetail(dauid).then(setDetail).catch((e) => setError(String(e)))
  }, [dauid])

  if (error) return <div className="panel"><p className="error">{error}</p></div>
  if (!detail) return <div className="panel"><p className="muted">Loading…</p></div>

  const { census } = detail
  const supportData = detail.support_levels.map((row) => ({
    name: row.support_level === null ? 'No response' : SUPPORT_LABELS[row.support_level],
    value: row.doors,
    key: row.support_level === null ? 'none' : String(row.support_level),
  }))
  const outcomeData = topN(detail.outcome_combinations, 5, (r) => r.combination || '—')

  return (
    <div className="panel">
      <h2>DA {dauid}</h2>

      <Collapsible title="Canvass data">
        <dl className="stats">
          <Stat label="Doors knocked" value={detail.doors_knocked.toLocaleString()} />
          <Stat label="Dwellings" value={census.total_private_dwellings.toLocaleString()} />
        </dl>

        <h4>Support level</h4>
        <p className="muted small">One slice per door, using the latest recorded support.</p>
        <ResponsiveContainer width="100%" height={PIE_HEIGHT}>
          <PieChart>
            <Pie data={supportData} dataKey="value" nameKey="name" outerRadius={PIE_RADIUS} label>
              {supportData.map((entry) => (
                <Cell key={entry.key} fill={SUPPORT_COLORS[entry.key]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>

        <h4>Outcomes</h4>
        <p className="muted small">
          One slice per attempt, so these sum to 100%. A door logged as both
          “Answered” and “Not Interested” is a single combined slice.
        </p>
        <ResponsiveContainer width="100%" height={PIE_HEIGHT}>
          <PieChart>
            <Pie data={outcomeData} dataKey="value" nameKey="name" outerRadius={PIE_RADIUS} label>
              {outcomeData.map((entry, index) => (
                <Cell key={entry.name} fill={OUTCOME_COLORS[index % OUTCOME_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>

        <details>
          <summary>Per-outcome totals</summary>
          <p className="muted small">
            One attempt can appear in several rows, so these do not sum to 100%.
          </p>
          <table className="mini">
            <tbody>
              {detail.outcome_atoms.map((row) => (
                <tr key={row.outcome}>
                  <td>{row.outcome}</td>
                  <td>{row.attempts.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>

        <div className="voters">
          {voters === null ? (
            <button
              className="primary"
              disabled={loadingVoters}
              onClick={() => {
                setLoadingVoters(true)
                fetchVoters(dauid)
                  .then(setVoters)
                  .catch((e) => setError(String(e)))
                  .finally(() => setLoadingVoters(false))
              }}
            >
              {loadingVoters ? 'Loading…' : 'Show voter list'}
            </button>
          ) : (
            <>
              <h4>Voters ({voters.length})</h4>
              <p className="footnote">Access to this list is logged.</p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th><th>Address</th><th>Unit</th>
                      <th>Email</th><th>Phone</th><th>Support</th>
                    </tr>
                  </thead>
                  <tbody>
                    {voters.map((voter) => (
                      <tr key={voter.id}>
                        <td>{voter.name ?? <span className="muted">—</span>}</td>
                        <td>{voter.address.split(',')[0]}</td>
                        <td>{voter.unit || '—'}</td>
                        <td>{voter.email ?? '—'}</td>
                        <td>{voter.phone ?? '—'}</td>
                        <td>
                          {voter.support_level
                            ? SUPPORT_LABELS[voter.support_level]
                            : <span className="muted">No response</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </Collapsible>

      <Collapsible title="Census data">
        <dl className="stats">
          <Stat label="Population" value={census.population.toLocaleString()} />
          <Stat label="Dwellings" value={census.total_private_dwellings.toLocaleString()} />
          <Stat label="Avg household" value={census.average_household_size.toFixed(1)} />
          <Stat label="Low income" value={`${census.low_income_prevalence}%`} />
          <Stat label="Owner / renter" value={`${census.owner} / ${census.renter}`} />
        </dl>

        <h4>Commute mode</h4>
        <dl className="stats">
          <Stat label="Car" value={census.commute_car} />
          <Stat label="Transit" value={census.commute_transit} />
          <Stat label="Walk" value={census.commute_walk} />
          <Stat label="Bike" value={census.commute_bike} />
        </dl>

        <h4>Leaves for work</h4>
        <dl className="stats">
          <Stat label="5–6am" value={census.leave_0500} />
          <Stat label="6–7am" value={census.leave_0600} />
          <Stat label="7–8am" value={census.leave_0700} />
          <Stat label="8–9am" value={census.leave_0800} />
          <Stat label="9–12pm" value={census.leave_0900} />
          <Stat label="12–5pm" value={census.leave_1200} />
        </dl>
        <p className="footnote">
          Commute and departure counts come from the 25% long-form sample and do not
          sum against population. Counts are randomly rounded to 5.
        </p>
      </Collapsible>
    </div>
  )
}

/** A panel section that folds away. Native <details> gives keyboard support
 *  and the open/closed state for free. Both sections start open. */
function Collapsible({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="section" open>
      <summary><h3>{title}</h3></summary>
      <div className="section-body">{children}</div>
    </details>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{typeof value === 'number' ? value.toLocaleString() : value}</dd>
    </div>
  )
}
