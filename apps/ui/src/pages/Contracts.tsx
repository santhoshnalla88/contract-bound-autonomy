import { useEffect, useState } from 'react';
import { FileText, Shield } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import type { Contract } from '../lib/types';

interface ContractSummary {
  contract_id: string;
  service: string;
  environment: string;
  version: string;
  allowed_actions: string[];
  forbidden_actions: string[];
}

export default function Contracts() {
  const [list, setList] = useState<ContractSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Contract | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ contracts: ContractSummary[] }>('/api/contracts')
      .then((r) => {
        setList(r.contracts);
        if (r.contracts[0]) setSelected(r.contracts[0].service);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load contracts'));
  }, []);

  useEffect(() => {
    if (!selected) return;
    api<Contract>(`/api/contracts/${encodeURIComponent(selected)}`)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load contract'));
  }, [selected]);

  return (
    <div className="animate-in" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <header className="page-header" style={{ marginBottom: '1.5rem' }}>
        <div>
          <h1 className="page-title text-gradient">Operational Contracts</h1>
          <p className="page-subtitle">The machine-readable authority for every agent action</p>
        </div>
      </header>

      {error && <div className="glass-panel" style={{ padding: '1rem', color: 'var(--status-error)', marginBottom: '1rem' }}>{error}</div>}

      <div style={{ display: 'flex', gap: '1.5rem', flex: 1, minHeight: 0 }}>
        <div className="glass-panel" style={{ width: 300, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-subtle)', fontWeight: 600 }}>All Contracts ({list.length})</div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {list.map((c) => (
              <div
                key={c.contract_id}
                onClick={() => setSelected(c.service)}
                className="table-row-hover"
                style={{
                  padding: '1rem',
                  borderBottom: '1px solid var(--border-subtle)',
                  cursor: 'pointer',
                  borderLeft: selected === c.service ? '3px solid var(--accent-primary)' : '3px solid transparent',
                  background: selected === c.service ? 'rgba(59,130,246,0.1)' : 'transparent',
                }}
              >
                <strong style={{ color: 'var(--text-primary)' }}>{c.contract_id}</strong>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>{c.service} (v{c.version})</div>
              </div>
            ))}
            {list.length === 0 && <div style={{ padding: '1rem', color: 'var(--text-secondary)' }}>No contracts found.</div>}
          </div>
        </div>

        <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Shield size={20} color="var(--accent-secondary)" />
            <h3 style={{ fontSize: '1.1rem', margin: 0 }}>{detail ? `${detail.contract_id} — ${detail.service}` : 'Select a contract'}</h3>
          </div>
          <div style={{ flex: 1, background: '#0d0d12', padding: '1.5rem', overflowY: 'auto', fontFamily: 'monospace', color: '#e2e8f0', fontSize: '0.85rem', lineHeight: 1.6 }}>
            {detail ? (
              <pre style={{ margin: 0 }}>{JSON.stringify(detail, null, 2)}</pre>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)' }}><FileText size={16} /> Loading…</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
