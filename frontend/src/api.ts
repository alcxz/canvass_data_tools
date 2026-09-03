import { createClient } from '@supabase/supabase-js'
import type { DADetail, DASummary, Voter } from './types'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)

// The Function URL AWS prints ends in a slash and every path below starts with
// one. Trim so the two never join into "//api/...", which FastAPI would 404.
const API_URL: string = (import.meta.env.VITE_API_URL as string).replace(/\/+$/, '')

/** Every call carries the Supabase session JWT. The browser never talks to the
 *  database directly -- voter PII sits behind the API's auth check, not behind
 *  the anon key. */
async function authedFetch<T>(path: string): Promise<T> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error('Not signed in')

  const response = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export const fetchSummary = () =>
  authedFetch<{ das: DASummary[] }>('/api/das/summary').then((r) => r.das)

export const fetchDetail = (dauid: string) => authedFetch<DADetail>(`/api/das/${dauid}`)

export const fetchVoters = (dauid: string) =>
  authedFetch<{ voters: Voter[] }>(`/api/das/${dauid}/voters`).then((r) => r.voters)
