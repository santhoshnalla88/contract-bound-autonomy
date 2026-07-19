import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, XCircle, Radio, ShieldCheck, ShieldAlert, Activity } from 'lucide-react';
import { api, ApiError, eventStreamUrl } from '../lib/api';
import { useAuth } from '../auth/AuthContext';
import type { IncidentStatus, WorkflowEvent } from '../lib/types';
import { statusColor } from '../lib/ui';

export default function IncidentDetail() {
  const { id = '' } = useParams();
  const { hasRole } = useAuth();
  const [snap, setSnap] = useState<IncidentStatus | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const seen = useRef<Set<string>>(new Set());

  const loadSnapshot = useCallback(async () => {
    try {
      setSnap(await api<IncidentStatus>(`/api/incidents/${encodeURIComponent(id)}`));
    } catch (e) {
      if (e instanceof ApiError && e.status !== 404) setError(e.message);
    }
  }, [id]);

  // Live event stream (SSE). Cleanup closes the connection on unmount.
  useEffect(() => {
    seen.current = new Set();
    setEvents([]);
    const es = new EventSource(eventStreamUrl(id));
    setLive(true);
    es.onmessage = (msg) => {
      let ev: WorkflowEvent;
      try {
        ev = JSON.parse(msg.data);
      } catch {
        return;
      }
      const key = `${ev.type}|${ev.timestamp}|${ev.message}`;
      if (seen.current.has(key)) return;
      seen.current.add(key);
      setEvents((prev) => [...prev, ev]);
      // Refresh the snapshot when governance/state changes.
      if (['guardrail_evaluated', 'risk_evaluated', 'approval_required', 'actions_executed', 'finalized', 'escalated', 'postconditions_validated'].includes(ev.type)) {
        loadSnapshot();
      }
      if (ev.terminal) {
        setLive(false);
        es.close();
      }
    };
    es.onerror = () => setLive(false);
    return () => es.close();
  }, [id, loadSnapshot]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  async function decide(decision: 'APPROVED' | 'REJECTED') {
    setActing(true);
    try {
      await api(`/api/approvals/${encodeURIComponent(id)}`, {
        method: 'POST',
        body: JSON.stringify({ decision, reasoning: 'via control plane' }),
      });
      await loadSnapshot();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Approval failed');
    } finally {
      setActing(false);
    }
  }

  const inc = snap?.incident;
  const plan = snap?.proposed_plan;
  const contract = snap?.retrieved_contract;

  return (
    <div className="animate-in">
      <Link to="/incidents" style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: '1rem' }}>
        <ArrowLeft size={15} /> Back to incidents
      </Link>

      <header className="page-header" style={{ marginBottom: '1.5rem' }}>
        <div>
          <h1 className="page-title" style={{ fontFamily: 'monospace' }}>{id}</h1>
          <p className="page-subtitle">{inc?.service ?? '—'} · {inc?.environment ?? '—'}</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <span style={{ color: statusColor(snap?.status), fontWeight: 700, fontSize: '1.1rem' }}>{snap?.status ?? '…'}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end', color: live ? 'var(--status-success)' : 'var(--text-secondary)', fontSize: '0.75rem' }}>
            <Radio size={13} /> {live ? 'live' : 'idle'}
          </div>
        </div>
      </header>

      {error && <div className="glass-panel" style={{ padding: '1rem', color: 'var(--status-error)', marginBottom: '1rem' }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* LEFT: governance detail */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* metrics */}
          <section className="dashboard-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <Metric label="Risk" value={snap?.risk_level ?? '—'} />
            <Metric label="Guardrail" value={snap?.guardrail_status ?? '—'} />
            <Metric label="Retries" value={String(snap?.retry_count ?? 0)} />
          </section>

          {/* approval */}
          {snap?.awaiting_approval && (
            <section className="glass-panel" style={{ padding: '1.25rem', borderColor: 'var(--accent-secondary)' }}>
              <h3 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: 8 }}><ShieldAlert size={18} color="var(--accent-secondary)" /> Human approval required</h3>
              <p style={{ color: 'var(--text-secondary)', margin: '0 0 1rem' }}>{plan?.summary ?? 'Review the proposed plan.'}</p>
              {hasRole('approver') ? (
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button className="btn btn-primary" onClick={() => decide('APPROVED')} disabled={acting} style={{ background: 'var(--status-success)' }}>
                    <CheckCircle2 size={16} style={{ marginRight: 6 }} /> Approve
                  </button>
                  <button className="btn btn-secondary" onClick={() => decide('REJECTED')} disabled={acting}>
                    <XCircle size={16} style={{ marginRight: 6 }} /> Reject
                  </button>
                </div>
              ) : (
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Your role can't approve — an <b>approver</b> or <b>admin</b> must decide.</div>
              )}
            </section>
          )}

          {/* proposed plan */}
          <section className="glass-panel" style={{ padding: '1.25rem' }}>
            <h3 style={{ margin: '0 0 0.75rem' }}>Proposed Plan</h3>
            {plan?.actions?.length ? (
              <>
                <div style={{ color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>{plan.summary}</div>
                {plan.actions.map((a, i) => (
                  <div key={i} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border-subtle)' }}>
                    <code style={{ background: 'rgba(255,255,255,0.08)', padding: '2px 6px', borderRadius: 4 }}>{a.action}</code>
                    {a.rationale && <span style={{ color: 'var(--text-secondary)', marginLeft: 8, fontSize: '0.85rem' }}>{a.rationale}</span>}
                  </div>
                ))}
              </>
            ) : (
              <div style={{ color: 'var(--text-secondary)' }}>No plan generated yet (needs an LLM key; otherwise the run fail-safe escalates).</div>
            )}
          </section>

          {/* effective contract */}
          <section className="glass-panel" style={{ padding: '1.25rem' }}>
            <h3 style={{ margin: '0 0 0.75rem', display: 'flex', alignItems: 'center', gap: 8 }}><ShieldCheck size={18} color="var(--accent-primary)" /> Effective Contract</h3>
            {contract ? (
              <div style={{ fontSize: '0.85rem', lineHeight: 1.8 }}>
                <div><span style={{ color: 'var(--text-secondary)' }}>Allowed:</span> {contract.allowed_actions.map((a) => <code key={a} style={chip('rgba(16,185,129,0.15)')}>{a}</code>)}</div>
                <div><span style={{ color: 'var(--text-secondary)' }}>Forbidden:</span> {contract.forbidden_actions.map((a) => <code key={a} style={chip('rgba(239,68,68,0.15)')}>{a}</code>)}</div>
                {contract.limits && <div><span style={{ color: 'var(--text-secondary)' }}>Max restarts:</span> {contract.limits.max_pod_restarts_per_incident}</div>}
              </div>
            ) : <div style={{ color: 'var(--text-secondary)' }}>Not resolved yet.</div>}
          </section>

          {/* violations / summary */}
          {snap?.violations?.length ? (
            <section className="glass-panel" style={{ padding: '1.25rem', borderColor: 'var(--status-error)' }}>
              <h3 style={{ margin: '0 0 0.5rem', color: 'var(--status-error)' }}>Violations</h3>
              {snap.violations.map((v, i) => <div key={i} style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>• {v}</div>)}
            </section>
          ) : null}
          {snap?.executive_summary && (
            <section className="glass-panel" style={{ padding: '1.25rem' }}>
              <h3 style={{ margin: '0 0 0.5rem' }}>Executive Summary</h3>
              <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem', lineHeight: 1.6 }}>{snap.executive_summary}</p>
            </section>
          )}
        </div>

        {/* RIGHT: live timeline */}
        <section className="glass-panel" style={{ padding: '1.25rem', position: 'sticky', top: '1rem' }}>
          <h3 style={{ margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: 8 }}><Activity size={18} color="var(--accent-primary)" /> Workflow Timeline</h3>
          <div style={{ maxHeight: '65vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {events.length === 0 && <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Waiting for events…</div>}
            {events.map((ev, i) => (
              <div key={i} style={{ display: 'flex', gap: '0.6rem' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', marginTop: 6, background: ev.terminal ? 'var(--status-warning)' : 'var(--accent-primary)', flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>{ev.message}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                    {new Date(ev.timestamp).toLocaleTimeString()}{ev.node ? ` · ${ev.node}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-card glass-panel">
      <span className="stat-title">{label}</span>
      <span className="stat-value" style={{ fontSize: '1.5rem' }}>{value}</span>
    </div>
  );
}

const chip = (bg: string): React.CSSProperties => ({ background: bg, padding: '2px 6px', borderRadius: 4, marginRight: 6, marginLeft: 6, fontSize: '0.75rem' });
