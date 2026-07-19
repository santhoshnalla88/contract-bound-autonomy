import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ShieldCheck, Clock, CheckCircle2, AlertTriangle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { api, ApiError } from '../lib/api';
import type { IncidentListItem, PendingApproval } from '../lib/types';
import { isActive, statusColor, timeAgo } from '../lib/ui';

export default function Dashboard() {
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [pending, setPending] = useState<PendingApproval[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [inc, pend] = await Promise.all([
        api<{ incidents: IncidentListItem[] }>('/api/incidents'),
        api<{ pending: PendingApproval[] }>('/api/approvals/pending'),
      ]);
      setIncidents(inc.incidents);
      setPending(pend.pending);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load dashboard');
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const active = incidents.filter((i) => isActive(i.status)).length;
  const resolved = incidents.filter((i) => i.status === 'SUCCESS').length;
  const successRate = incidents.length ? Math.round((resolved / incidents.length) * 100) : 0;

  // Real status distribution for the chart.
  const counts: Record<string, number> = {};
  for (const i of incidents) counts[i.status] = (counts[i.status] ?? 0) + 1;
  const chartData = Object.entries(counts).map(([status, count]) => ({ status: status.replace(/_/g, ' '), count, color: statusColor(status) }));

  return (
    <div className="animate-in">
      <header className="page-header">
        <div>
          <h1 className="page-title text-gradient">System Overview</h1>
          <p className="page-subtitle">Live governance telemetry across all incidents</p>
        </div>
      </header>

      {error && <div className="glass-panel" style={{ padding: '1rem', color: 'var(--status-error)', marginBottom: '1rem' }}>{error}</div>}

      <div className="dashboard-grid" style={{ marginBottom: '2rem' }}>
        <Stat title="Total Incidents" value={String(incidents.length)} icon={<Activity size={16} />} />
        <Stat title="Active Now" value={String(active)} icon={<Clock size={16} />} color="var(--accent-primary)" />
        <Stat title="Pending Approvals" value={String(pending.length)} icon={<ShieldCheck size={16} />} color="var(--status-warning)" />
        <Stat title="Autonomous Success" value={`${successRate}%`} icon={<CheckCircle2 size={16} />} color="var(--status-success)" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1.5rem' }}>
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h2 style={{ fontSize: '1.15rem', margin: '0 0 1.5rem' }}>Incident Status Distribution</h2>
          <div style={{ height: 300 }}>
            {chartData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="status" stroke="var(--text-secondary)" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                  <YAxis allowDecimals={false} stroke="var(--text-secondary)" tick={{ fill: 'var(--text-secondary)' }} />
                  <Tooltip contentStyle={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: 8 }} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: 'var(--text-secondary)' }}>
                No incidents yet — submit one from the Incidents page.
              </div>
            )}
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h2 style={{ fontSize: '1.15rem', margin: '0 0 1rem' }}>Recent Incidents</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {incidents.slice(0, 6).map((i) => (
              <Link key={i.incident_id} to={`/incidents/${i.incident_id}`} className="table-row-hover" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.6rem 0.75rem', borderRadius: 8, textDecoration: 'none' }}>
                <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)' }}>{i.incident_id}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: statusColor(i.status), fontSize: '0.85rem' }}>
                  {(i.status === 'FAILED' || i.status === 'ESCALATED') && <AlertTriangle size={13} />}
                  {i.status.replace(/_/g, ' ')}
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 6 }}>{timeAgo(i.updated_at)}</span>
                </span>
              </Link>
            ))}
            {incidents.length === 0 && <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Nothing yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ title, value, icon, color }: { title: string; value: string; icon: React.ReactNode; color?: string }) {
  return (
    <div className="stat-card glass-panel interactive-card">
      <span className="stat-title">{title}</span>
      <span className="stat-value" style={{ color: color ?? 'var(--text-primary)' }}>{value}</span>
      <div className="stat-trend" style={{ color: 'var(--text-secondary)' }}>{icon}</div>
    </div>
  );
}
