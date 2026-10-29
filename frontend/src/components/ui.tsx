// src/components/ui.tsx — small shared building blocks (cards, badges, states)
import type { ReactNode, ElementType } from 'react';
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react';
import { fmtReason, SOURCE_LABELS } from '../lib/utils';

export function Card({ title, sub, right, children, className = '' }:
  { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border p-5 ${className}`} style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
      {(title || right) && (
        <header className="flex items-start gap-3 mb-4">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{title}</h2>}
            {sub && <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>{sub}</p>}
          </div>
          {right && <div className="ml-auto shrink-0">{right}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub, icon: Icon, accent }:
  { label: string; value: ReactNode; sub?: ReactNode; icon: ElementType; accent: string }) {
  return (
    <div className="rounded-xl border p-4 flex flex-col gap-1 min-w-0" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
      <div className="flex items-center gap-2">
        <span className="rounded-md p-1.5" style={{ background: `color-mix(in srgb, ${accent} 14%, transparent)` }}>
          <Icon size={14} style={{ color: accent }} />
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wider truncate" style={{ color: 'var(--muted)' }}>{label}</span>
      </div>
      <span className="text-3xl font-bold tabular-nums leading-tight" style={{ color: 'var(--text)' }}>{value}</span>
      {sub && <span className="text-xs" style={{ color: 'var(--muted)' }}>{sub}</span>}
    </div>
  );
}

export function DestBadge({ d }: { d: string | null | undefined }) {
  if (!d) return <span style={{ color: 'var(--muted)' }}>—</span>;
  return <span className="inline-block rounded px-2 py-0.5 text-xs font-bold text-white"
    style={{ background: d === 'EDGE' ? 'var(--edge)' : 'var(--cloud)' }}>{d}</span>;
}

export function ReasonBadge({ r }: { r: string | null | undefined }) {
  const bg = r === 'override_critical_patient' ? 'var(--emergency)' : r === 'network_degradation_veto' ? 'var(--veto)'
    : r === 'prediction_unavailable_safe_default' ? 'var(--veto)' : null;
  return <span className="inline-block rounded px-2 py-0.5 text-xs font-medium whitespace-nowrap"
    style={bg ? { background: bg, color: 'white' } : { background: 'var(--chip)', color: 'var(--text)' }}>{fmtReason(r)}</span>;
}

export function SourceBadge({ s }: { s: string }) {
  const real = s === 'replay' || s === 'live';
  return <span className="inline-block rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap border"
    style={{ borderColor: real ? 'var(--ok)' : 'var(--border)', color: real ? 'var(--ok)' : 'var(--muted)' }}>
    {SOURCE_LABELS[s] ?? s}</span>;
}

const STATUS_COLORS: Record<string, string> = {
  delivered: 'var(--ok)', success: 'var(--ok)', completed: 'var(--ok)', sent: 'var(--ok)',
  partially_delivered: 'var(--veto)', fallback_success: 'var(--veto)', not_configured: 'var(--muted)',
  not_notified: 'var(--muted)', skipped: 'var(--muted)', triggered: 'var(--cloud)',
  failed: 'var(--emergency)', received: 'var(--cloud)',
};
export function StatusBadge({ s }: { s: string }) {
  const c = STATUS_COLORS[s] ?? 'var(--muted)';
  return <span className="inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap" style={{ color: c }}>
    <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />{s.replace(/_/g, ' ')}</span>;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="flex items-center gap-2 py-10 justify-center text-sm" style={{ color: 'var(--muted)' }}>
    <Loader2 size={16} className="animate-spin" />{label}</div>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border px-4 py-3 text-sm flex items-start gap-2"
      style={{ borderColor: 'var(--emergency)', color: 'var(--emergency)', background: 'color-mix(in srgb, var(--emergency) 6%, transparent)' }}>
      <AlertTriangle size={16} className="shrink-0 mt-0.5" />
      <div className="flex-1">{error instanceof Error ? error.message : String(error)}</div>
      {onRetry && <button onClick={onRetry} className="underline text-xs">Retry</button>}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return <div className="flex flex-col items-center gap-2 py-10 text-center" style={{ color: 'var(--muted)' }}>
    <Inbox size={22} /><div className="text-sm font-medium" style={{ color: 'var(--text)' }}>{title}</div>
    {hint && <div className="text-xs max-w-md">{hint}</div>}</div>;
}

export function Select({ value, onChange, options, label }:
  { value: string; onChange: (v: string) => void; options: [string, string][]; label: string }) {
  return (
    <label className="text-xs flex items-center gap-1.5" style={{ color: 'var(--muted)' }}>{label}
      <select value={value} onChange={e => onChange(e.target.value)}
        className="rounded-md border px-2 py-1 text-xs" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

export function Btn({ children, onClick, disabled, kind = 'primary', type = 'button' }:
  { children: ReactNode; onClick?: () => void; disabled?: boolean; kind?: 'primary' | 'ghost' | 'danger'; type?: 'button' | 'submit' }) {
  const style = kind === 'primary' ? { background: 'var(--cloud)', color: 'white', borderColor: 'var(--cloud)' }
    : kind === 'danger' ? { background: 'transparent', color: 'var(--emergency)', borderColor: 'var(--emergency)' }
    : { background: 'transparent', color: 'var(--text)', borderColor: 'var(--border)' };
  return <button type={type} onClick={onClick} disabled={disabled}
    className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-opacity"
    style={style}>{children}</button>;
}

export const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text)' };
