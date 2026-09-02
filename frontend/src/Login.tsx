import { useState } from 'react'
import { supabase } from './api'

/** Sign-in only. Public signup is disabled in Supabase Auth -- accounts are
 *  created by invitation, because this application exposes voter PII. */
export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) setError(error.message)
    setBusy(false)
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>Ward 11 Canvass Map</h1>
        <p className="muted small">Access is by invitation.</p>
        <input
          type="email" placeholder="Email" value={email} required
          autoComplete="username" onChange={(e) => setEmail(e.target.value)}
        />
        <input
          type="password" placeholder="Password" value={password} required
          autoComplete="current-password" onChange={(e) => setPassword(e.target.value)}
        />
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}
