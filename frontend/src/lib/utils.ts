// src/lib/utils.ts — shared formatting helpers (team Frontend Build Guide §4 format rules)

export const fmtLatency = (ms: number | null | undefined) => (ms == null ? '—' : `${ms.toFixed(1)} ms`);
export const fmtCriticality = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)} / 10`);
export const fmtCount = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('en-IN'));
export const fmtPct = (p: number | null | undefined) => (p == null ? '—' : `${p.toFixed(1)}%`);
export const fmtNum = (v: number | null | undefined, d = 3) => (v == null ? '—' : v.toFixed(d));

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' IST';
}
export function fmtTimeShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false });
}

export const REASON_LABELS: Record<string, string> = {
  ahp_decision: 'AHP decision',
  override_critical_patient: 'Emergency override',
  network_degradation_veto: 'Network veto',
  prediction_unavailable_safe_default: 'No forecast → safe EDGE',
};
export const fmtReason = (c: string | null | undefined) => (c ? REASON_LABELS[c] ?? c.replace(/_/g, ' ') : '—');

export const SOURCE_LABELS: Record<string, string> = {
  replay: 'Replay · real data', simulated: 'Simulated', live: 'Live device', test: 'Test fixture',
};

export function clsx(...c: (string | false | null | undefined)[]) { return c.filter(Boolean).join(' '); }
