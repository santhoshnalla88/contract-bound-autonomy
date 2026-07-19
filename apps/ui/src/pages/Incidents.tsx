import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, RefreshCw, CheckCircle2, Clock, AlertTriangle, ChevronRight } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import { useAuth } from '../auth/AuthContext';
import type { IncidentListItem } from '../lib/types';
import { makeDemoIncident, severityBadgeClass, statusColor, timeAgo } from '../lib/ui';

export default function Incidents() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api<{ incidents: IncidentListItem[] }>('/api/incidents');
      setIncidents(res.incidents);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000); // light polling to reflect background progress
    return () => clearInterval(t);
  }, [load]);

  async function simulate() {
    setSubmitting(true);
    try {
      const incident = makeDemoIncident('HIGH');
      await api('/api/incidents', { method: 'POST', body: JSON.stringify(incident) });
      await load();
      navigate(`/incidents/${incident.incident_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to submit incident');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="animate-in">
      <header className="page-header" style={{ marginBottom: '1.5rem' }}>
        <div>
          <h1 className="page-title text-gradient">Active Incidents</h1>
          <p className="page-subtitle">Live autonomous remediations governed by contracts</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={load}>
            <RefreshCw size={16} style={{ marginRight: 8 }} /> Refresh
          </button>
          {hasRole('operator') && (
            <button className="btn btn-primary" onClick={simulate} disabled={submitting}>
              <Zap size={16} style={{ marginRight: 8 }} /> {submitting ? 'Submitting…' : 'Simulate Incident'}
            </button>
          )}
        </div>
      </header>

      {error && <div className="glass-panel" style={{ padding: '1rem', color: 'var(--status-error)', marginBottom: '1rem' }}>{error}</div>}

      <div className="glass-panel" style={{ padding: '0.5rem 0' }}>
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>INCIDENT ID</th>
                <th>SERVICE</th>
                <th>SEVERITY</th>
                <th>STATUS</th>
                <th>SUBMITTED BY</th>
                <th>UPDATED</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Loading…</td></tr>
              )}
              {!loading && incidents.length === 0 && (
                <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No incidents yet. Click <strong>Simulate Incident</strong> to run one.
                </td></tr>
              )}
              {incidents.map((inc) => {
                const sev = inc.data?.severity;
                return (
                  <tr key={inc.incident_id} className="table-row-hover" style={{ cursor: 'pointer' }} onClick={() => navigate(`/incidents/${inc.incident_id}`)}>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{inc.incident_id}</td>
                    <td>{inc.data?.service ?? '—'}</td>
                    <td>{sev ? <span className={severityBadgeClass(sev)}>{sev}</span> : '—'}</td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', color: statusColor(inc.status), fontWeight: 500 }}>
                        {inc.status === 'SUCCESS' && <CheckCircle2 size={15} />}
                        {inc.status === 'AWAITING_APPROVAL' && <Clock size={15} />}
                        {(inc.status === 'FAILED' || inc.status === 'ESCALATED' || inc.status === 'DENIED') && <AlertTriangle size={15} />}
                        {inc.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)' }}>{inc.submitted_by ?? '—'}</td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>{timeAgo(inc.updated_at)}</td>
                    <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }}><ChevronRight size={16} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
