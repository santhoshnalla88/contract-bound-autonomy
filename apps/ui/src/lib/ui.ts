import type { IncidentData } from './types';

export const TERMINAL_STATUSES = ['SUCCESS', 'DENIED', 'FAILED', 'ESCALATED'];

export function isActive(status: string): boolean {
  return !TERMINAL_STATUSES.includes(status);
}

export function statusColor(status?: string | null): string {
  switch (status) {
    case 'SUCCESS':
      return 'var(--status-success)';
    case 'DENIED':
    case 'FAILED':
      return 'var(--status-error)';
    case 'ESCALATED':
      return 'var(--status-warning)';
    case 'AWAITING_APPROVAL':
      return 'var(--accent-secondary)';
    default:
      return 'var(--accent-primary)'; // IN_PROGRESS / open
  }
}

export function severityBadgeClass(sev?: string): string {
  switch (sev) {
    case 'CRITICAL':
      return 'badge badge-critical';
    case 'HIGH':
      return 'badge badge-high';
    case 'MEDIUM':
      return 'badge badge-medium';
    default:
      return 'badge badge-low';
  }
}

// Build a demo incident with a schema-valid id (^INC-\d+$).
export function makeDemoIncident(severity: IncidentData['severity'] = 'HIGH'): IncidentData {
  return {
    incident_id: `INC-${Date.now()}`,
    service: 'inventory-service',
    environment: 'production',
    severity,
    logs: 'Readiness probes failing, connection pool exhausted.',
    metrics: { error_rate: 12.4, healthy_pods: 2, total_pods: 5 },
    active_checkout_connections: true,
  };
}

export function timeAgo(iso?: string | null): string {
  if (!iso) return '';
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${Math.floor(secs)}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}
