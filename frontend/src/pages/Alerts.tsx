// src/pages/Alerts.tsx — alert feed with per-channel delivery log and acknowledgement.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { fmtTime } from '../lib/utils';
import { Btn, Card, Empty, ErrorState, Loading, Select, StatusBadge } from '../components/ui';

export default function Alerts() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const q = useQuery({ queryKey: ['alerts', severity, status], queryFn: () => api.alerts({ limit: 100, severity, status }), refetchInterval: 8000 });
  const ack = useMutation({ mutationFn: api.ack, onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }) });
  const canAck = user?.role === 'admin' || user?.role === 'doctor';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div><h1 className="text-xl font-bold">Alerts</h1>
          <p className="text-sm max-w-2xl" style={{ color: 'var(--muted)' }}>
            An alert is <b>triggered</b> by the pipeline; it is only <b>delivered</b> when a configured channel (Telegram, e-mail, webhook)
            accepted it. Every attempt is listed. WARNING alerts are recorded but not pushed by default.</p></div>
        <div className="ml-auto flex gap-3">
          <Select label="Severity" value={severity} onChange={setSeverity} options={[['', 'All'], ['CRITICAL', 'Critical'], ['WARNING', 'Warning']]} />
          <Select label="Status" value={status} onChange={setStatus} options={[['', 'All'], ['delivered', 'Delivered'],
            ['partially_delivered', 'Partial'], ['failed', 'Failed'], ['not_configured', 'No channel'], ['not_notified', 'Recorded only'], ['triggered', 'Pending']]} />
        </div>
      </div>
      {q.isLoading && <Loading />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {ack.error && <ErrorState error={ack.error} />}
      {q.data && q.data.items.length === 0 && <Card><Empty title="No alerts" hint="Emergency overrides, network vetoes and execution failures create alerts." /></Card>}
      <div className="space-y-3">
        {q.data?.items.map(a => (
          <Card key={a.id}>
            <div className="flex flex-wrap items-start gap-3">
              <span className="text-xs font-bold px-2 py-0.5 rounded text-white"
                style={{ background: a.severity === 'CRITICAL' ? 'var(--emergency)' : 'var(--veto)' }}>{a.severity}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{a.message}</p>
                <p className="text-xs mt-1" style={{ color: 'var(--muted)' }}>#{a.id} · {a.kind.replace(/_/g, ' ')} · {fmtTime(a.created_at)}
                  {a.delivered_at && <> · delivered {fmtTime(a.delivered_at)}</>}</p>
              </div>
              <StatusBadge s={a.status} />
              {canAck && !a.acknowledged_at && a.severity === 'CRITICAL' &&
                <Btn kind="ghost" disabled={ack.isPending} onClick={() => ack.mutate(a.id)}>Acknowledge</Btn>}
              {a.acknowledged_at && <span className="text-xs" style={{ color: 'var(--ok)' }}>acknowledged {fmtTime(a.acknowledged_at)}</span>}
            </div>
            {a.deliveries.length > 0 && (
              <table className="mt-3 w-full text-xs"><tbody>
                {a.deliveries.map((d, i) => (
                  <tr key={i} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    <td className="py-1 pr-3 font-medium">{d.channel}</td><td className="pr-3">attempt {d.attempt}</td>
                    <td className="pr-3"><StatusBadge s={d.status} /></td><td className="pr-3" style={{ color: 'var(--muted)' }}>{d.detail}</td>
                    <td className="text-right tabular-nums">{d.latency_ms ? `${d.latency_ms} ms` : ''}</td></tr>))}
              </tbody></table>)}
          </Card>))}
      </div>
    </div>
  );
}
