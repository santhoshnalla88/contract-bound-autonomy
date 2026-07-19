// Shared API types (mirror the FastAPI response shapes).

export type Role = 'viewer' | 'operator' | 'approver' | 'admin';

export interface User {
  email: string;
  role: Role;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: Role;
  email: string;
}

export interface IncidentMetrics {
  error_rate: number;
  healthy_pods: number;
  total_pods: number;
}

export interface IncidentData {
  incident_id: string;
  service: string;
  environment: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  logs?: string;
  metrics: IncidentMetrics;
  active_checkout_connections?: boolean;
}

export interface IncidentListItem {
  incident_id: string;
  data: Partial<IncidentData>;
  status: string;
  submitted_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PlannedAction {
  action: string;
  target?: string;
  parameters?: Record<string, unknown>;
  rationale?: string;
}

export interface RemediationPlan {
  summary: string;
  actions: PlannedAction[];
  estimated_impact?: string;
}

export interface Contract {
  contract_id: string;
  service: string;
  environment: string;
  version: string;
  allowed_actions: string[];
  forbidden_actions: string[];
  limits?: Record<string, number>;
  availability_constraints?: Record<string, unknown>;
  approval_requirements?: Record<string, boolean>;
  postconditions?: string[];
}

export interface IncidentStatus {
  incident_id: string;
  status: string;
  current_node?: string;
  awaiting_approval: boolean;
  retry_count: number;
  guardrail_status?: string | null;
  violations: string[];
  risk_level?: string | null;
  approval_required: boolean;
  approved_by?: string | null;
  service?: string | null;
  incident?: IncidentData | null;
  proposed_plan?: RemediationPlan | null;
  retrieved_contract?: Contract | null;
  execution_history: Array<Record<string, unknown>>;
  postcondition_results: Array<Record<string, unknown>>;
  final_status?: string | null;
  executive_summary?: string | null;
  compensation_history: Array<Record<string, unknown>>;
}

export interface WorkflowEvent {
  incident_id: string;
  type: string;
  message: string;
  node?: string | null;
  data: Record<string, unknown>;
  terminal: boolean;
  timestamp: string;
}

export interface PendingApproval {
  incident_id: string;
  service?: string | null;
  risk_level?: string | null;
  violations: string[];
  proposed_plan?: RemediationPlan | null;
  created_at?: string | null;
}

export interface AuditEvent {
  incident_id: string;
  timestamp: string;
  event_type: string;
  actor?: string | null;
  outcome?: string | null;
  details?: Record<string, unknown>;
}
