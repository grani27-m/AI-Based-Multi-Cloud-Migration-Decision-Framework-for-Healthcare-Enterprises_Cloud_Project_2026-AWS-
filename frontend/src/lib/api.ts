// src/lib/api.ts — Owner: Rani Gupta
// Typed client for the FastAPI backend. Every number on screen comes from these calls;
// there is no hard-coded or sample data in the UI. Errors are surfaced, never hidden.

export type Role = 'admin' | 'doctor' | 'auditor' | 'device';
export interface User { id: number; username: string; role: Role; full_name: string }

export interface Summary {
  generated_at: string; source_filter: string;
  events: { total: number; by_status: Record<string, number>; by_source: Record<string, number> };
  decisions: { total: number; edge: { count: number; pct: number }; cloud: { count: number; pct: number };
               by_reason: Record<string, number> };
  predictions: { by_method: Record<string, number>; by_risk: Record<string, number> };
  executions: { by_status: Record<string, number> };
  alerts: { triggered: number; delivered: number; failed: number; not_configured: number; pending: number; mock_delivered?: number;
            by_status: Record<string, number>; by_kind: Record<string, number> };
  reconciliation: Record<string, boolean | number | string>;
}
export interface EventRow {
  event_id: string; device_id: string; source: string; status: string; observed_at: string; received_at: string;
  criticality: number; criticality_method: string; cloud_cost_index: number; last_rtt_ms: number | null;
  predicted_rtt_ms: number | null; prediction_method: string | null; risk: string | null;
  destination: 'EDGE' | 'CLOUD' | null; reason: string | null; edge_score: number | null; cloud_score: number | null;
}
export interface Page<T> { total: number; limit?: number; offset?: number; items: T[] }
export interface Decision {
  destination: 'EDGE' | 'CLOUD'; reason: string; veto: string; edge_score: number | null; cloud_score: number | null;
  weight_set: string; weights: Record<string, number>; normalised: Record<string, number>;
  contributions: { edge?: Record<string, number>; cloud?: Record<string, number> };
  engine_version: string; explanation: string; thresholds?: Record<string, number>;
}
export interface EventDetail {
  event_id: string; duplicate: boolean; status: string; error: string | null; device_id: string; source: string;
  observed_at: string; received_at: string;
  criticality: { score: number; method: string; vitals: Record<string, unknown> | null };
  cloud_cost_index: number;
  prediction: { predicted_rtt_ms: number; risk: string; method: string; model_version: string; horizon_s: number;
                inference_ms: number; last_observed_rtt_ms: number } | null;
  decision: Decision | null;
  execution: { status: string; requested_destination: string; final_destination: string | null; adapter: string;
               attempts: number; duration_ms: number; output_ref: string | null; error: string | null;
               attempt_log: { destination: string; adapter: string; attempt: number; ok: boolean; ms: number; error?: string }[] } | null;
  alerts: { id: number; severity: string; kind: string; status: string }[];
  network_window?: { timestamp: string; rtt_avg_ms: number | null; loss_pct: number; jitter_ms: number | null }[];
  provenance?: Record<string, unknown>;
}
export interface AlertRow {
  id: number; event_id: string; device_id: string; severity: string; kind: string; message: string; status: string;
  created_at: string; delivered_at: string | null; acknowledged_at: string | null;
  deliveries: { channel: string; attempt: number; status: string; detail: string; latency_ms: number; attempted_at: string }[];
}
export interface CandidateScore { name: string; kind: 'edge' | 'cloud'; admissible: boolean; excluded_reason: string | null;
  score: number | null; contributions: Record<string, number>; normalised: Record<string, number> }
export interface Ranking { device_id: string; destination: string; destination_kind: 'edge' | 'cloud'; reason: string;
  criticality: number; weights: Record<string, number>; weight_set: string; ranking: CandidateScore[]; explanation: string;
  engine_version: string }
export interface AuditRow { id: number; ts: string; actor: string; action: string; resource: string;
  detail: Record<string, unknown>; prev_hash: string; hash: string }
export interface Verify { valid: boolean; checked: number; first_broken_id: number | null; problem: string | null;
  head_hash: string | null; verified_at: string; verified_by: string }
export interface DeviceRow { id: string; kind: string; is_active: boolean; first_seen_at: string; last_seen_at: string;
  events: number; last_event: null | { event_id: string; source: string; criticality: number; last_rtt_ms: number | null;
  predicted_rtt_ms: number | null; destination: string | null; reason: string | null } }
export interface TsPoint { event_id: string; device_id: string; source: string; received_at: string; observed_at: string;
  last_rtt_ms: number | null; predicted_rtt_ms: number; method: string; criticality: number; destination: string; reason: string }
export interface MetricRow { mae_ms: number; rmse_ms: number; median_ae_ms: number; risk_class_accuracy: number; n: number;
  mae_skill_vs_persistence?: number; rmse_skill_vs_persistence?: number }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SystemInfo = Record<string, any>;

const TOKEN_KEY = 'hcf_token';
const USER_KEY = 'hcf_user';
// sessionStorage: the token is gone when the tab closes (no long-lived token on shared hospital PCs)
function store(): Storage | null { try { return window.sessionStorage; } catch { return null; } }
let token: string | null = store()?.getItem(TOKEN_KEY) ?? null;
let user: User | null = (() => { try { return JSON.parse(store()?.getItem(USER_KEY) || 'null'); } catch { return null; } })();
let onUnauthorized: () => void = () => {};

export const getUser = () => user;
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }
export function clearSession() { token = null; user = null; store()?.removeItem(TOKEN_KEY); store()?.removeItem(USER_KEY); }

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try { res = await fetch(path, { ...init, headers }); }
  catch { throw new ApiError(0, 'Backend unreachable — is the API running on port 8000?'); }
  if (res.status === 401 && token) { clearSession(); onUnauthorized(); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const d = (body as { detail?: unknown }).detail;
    throw new ApiError(res.status, typeof d === 'string' ? d : d ? JSON.stringify(d) : `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const qs = (p: Record<string, string | number | undefined | null>) =>
  Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');

export const api = {
  async login(username: string, password: string): Promise<User> {
    const r = await call<{ access_token: string; user: User }>('/api/v1/auth/login',
      { method: 'POST', body: JSON.stringify({ username, password }) });
    token = r.access_token; user = r.user;
    store()?.setItem(TOKEN_KEY, token); store()?.setItem(USER_KEY, JSON.stringify(user));
    return r.user;
  },
  ready: () => call<{ ready: boolean; database: boolean; model_loaded: boolean; model_version: string }>('/ready'),
  summary: (source?: string) => call<Summary>(`/api/v1/dashboard/summary?${qs({ source })}`),
  timeseries: (limit = 200, source?: string) => call<{ items: TsPoint[] }>(`/api/v1/dashboard/timeseries?${qs({ limit, source })}`),
  events: (p: { limit?: number; offset?: number; source?: string; destination?: string; reason?: string; device_id?: string; status?: string } = {}) =>
    call<Page<EventRow>>(`/api/v1/events?${qs(p)}`),
  event: (id: string) => call<EventDetail>(`/api/v1/events/${encodeURIComponent(id)}`),
  devices: () => call<{ devices: DeviceRow[] }>('/api/v1/devices'),
  alerts: (p: { limit?: number; severity?: string; status?: string } = {}) => call<Page<AlertRow>>(`/api/v1/alerts?${qs(p)}`),
  ack: (id: number) => call<{ id: number }>(`/api/v1/alerts/${id}/ack`, { method: 'POST' }),
  audit: (limit = 100, offset = 0, action?: string) => call<Page<AuditRow>>(`/api/v1/audit?${qs({ limit, offset, action })}`),
  verify: () => call<Verify>('/api/v1/audit/verify'),
  executions: (limit = 50) => call<Page<Record<string, unknown>>>(`/api/v1/executions?${qs({ limit })}`),
  system: () => call<SystemInfo>('/api/v1/system/info'),
  preview: (b: { criticality: number; predicted_latency_ms: number | null; cloud_cost_index: number; weight_set: string }) =>
    call<Decision>('/api/v1/decision/preview', { method: 'POST', body: JSON.stringify(b) }),
  rank: (b: { criticality: number; weight_set: string; clouds: { name: string; predicted_latency_ms: number | null; cost_index: number }[] }) =>
    call<Ranking>('/api/v1/decision/rank', { method: 'POST', body: JSON.stringify(b) }),
  health: () => call<{ status: string; version: string }>('/health'),
  demo: (b: { mode: 'replay' | 'simulate'; count: number; scenario?: string; seed: number }) =>
    call<{ processed: number; duplicates: number; failed: number; by_destination: Record<string, number>; by_reason: Record<string, number> }>(
      '/api/v1/demo/run', { method: 'POST', body: JSON.stringify(b) }),
  users: () => call<{ id: number; username: string; full_name: string; role: Role; is_active: boolean; created_at: string; last_login_at: string | null }[]>('/api/v1/users'),
  createUser: (b: { username: string; full_name: string; password: string; role: Role }) =>
    call('/api/v1/users', { method: 'POST', body: JSON.stringify(b) }),
  setActive: (id: number, active: boolean) => call(`/api/v1/users/${id}?is_active=${active}`, { method: 'PATCH' }),
};
