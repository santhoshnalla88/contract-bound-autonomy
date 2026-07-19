import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../lib/api';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@local');
  const [password, setPassword] = useState('changeme123');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed — is the API running?');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100vh', padding: '1rem' }}>
      <form onSubmit={onSubmit} className="glass-panel animate-in" style={{ width: '100%', maxWidth: 380, padding: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <div className="brand-icon"><ShieldCheck size={18} /></div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>GAAP Control Plane</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Governed Autonomous AI</div>
          </div>
        </div>

        <label style={labelStyle}>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="username" style={inputStyle} />

        <label style={labelStyle}>Password</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" style={inputStyle} />

        {error && <div style={{ color: 'var(--status-error)', fontSize: '0.85rem', marginBottom: '0.75rem' }}>{error}</div>}

        <button type="submit" className="btn btn-primary" disabled={busy} style={{ width: '100%', justifyContent: 'center' }}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginTop: '1rem', textAlign: 'center' }}>
          Role-based access · every action is audited
        </p>
      </form>
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' };
const inputStyle: React.CSSProperties = {
  width: '100%',
  marginBottom: '1rem',
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-sm)',
  padding: '0.6rem 0.8rem',
  color: 'white',
  outline: 'none',
};
