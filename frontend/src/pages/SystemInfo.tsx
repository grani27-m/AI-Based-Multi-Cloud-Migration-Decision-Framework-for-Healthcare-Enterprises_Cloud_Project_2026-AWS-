// src/pages/SystemInfo.tsx — what is actually running, and the honest status of every AWS service.
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { Card, ErrorState, Loading } from '../components/ui';

const STATUS_COLOR: Record<string, string> = { deployed: 'var(--ok)', tested: 'var(--ok)', configured: 'var(--cloud)',
  'local/mock': 'var(--veto)', planned: 'var(--muted)' };

export default function SystemInfo() {
  const q = useQuery({ queryKey: ['system'], queryFn: api.system });
  const r = useQuery({ queryKey: ['ready'], queryFn: api.ready, refetchInterval: 10_000 });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} />;
  const s = q.data!;
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">System</h1><p className="text-sm" style={{ color: 'var(--muted)' }}>{s.project} · {s.course}</p></div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Team">
          <ul className="space-y-2 text-sm">{s.team.map((t: { name: string; reg: string; module: string }) =>
            <li key={t.reg}><b>{t.name}</b> <span style={{ color: 'var(--muted)' }}>({t.reg})</span><br /><span className="text-xs">{t.module}</span></li>)}</ul>
        </Card>
        <Card title="Runtime">
          <ul className="text-sm space-y-1">
            <li>API version <b>{s.api_version}</b></li>
            <li>Database <b>{s.database.dialect}</b> · reachable <b>{r.data ? String(r.data.database) : '…'}</b></li>
            <li>Model <b>{s.model.loaded ? s.model.model_version : 'NOT LOADED (fallback)'}</b></li>
            <li>Decision engine <b>{s.decision_engine.version}</b> · weights <b>{s.decision_engine.weight_set}</b></li>
            <li>Emergency ≥ {s.decision_engine.emergency_threshold} · veto ≥ {s.decision_engine.latency_veto_ms} ms</li>
            <li>Edge adapter <b>{s.execution.edge_adapter}</b></li>
            <li>Cloud adapter <b>{s.execution.cloud_adapter}</b></li>
          </ul>
        </Card>
        <Card title="Alert channels" sub="Configured through environment variables only">
          <ul className="text-sm space-y-1">{Object.entries(s.alert_channels_configured).map(([k, v]) =>
            <li key={k}>{k}: <b style={{ color: v ? 'var(--ok)' : 'var(--muted)' }}>{v ? 'configured' : 'not configured'}</b></li>)}</ul>
        </Card>
      </div>
      {s.aws_services && <Card title="AWS services — real status" sub={s.aws_services.note}>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th className="py-1">Service</th><th>Role in design</th><th>Local stand-in</th><th>Status</th><th>Evidence</th></tr></thead>
          <tbody>{s.aws_services.services.map((x: { service: string; role: string; local: string; status: string; evidence: string }) =>
            <tr key={x.service} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
              <td className="py-1.5 pr-3 font-medium whitespace-nowrap">{x.service}</td><td className="pr-3">{x.role}</td><td className="pr-3 text-xs">{x.local}</td>
              <td className="pr-3 font-semibold whitespace-nowrap" style={{ color: STATUS_COLOR[x.status] ?? 'var(--muted)' }}>{x.status}</td>
              <td className="text-xs">{x.evidence}</td></tr>)}</tbody></table></div>
      </Card>}
    </div>
  );
}
