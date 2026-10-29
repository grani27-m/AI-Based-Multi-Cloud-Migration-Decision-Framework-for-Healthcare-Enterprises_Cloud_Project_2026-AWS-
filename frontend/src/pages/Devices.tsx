// src/pages/Devices.tsx — device registry built automatically from ingested events.
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { fmtCriticality, fmtLatency, fmtTime } from '../lib/utils';
import { Card, DestBadge, Empty, ErrorState, Loading, ReasonBadge, SourceBadge } from '../components/ui';

export default function Devices() {
  const q = useQuery({ queryKey: ['devices'], queryFn: api.devices, refetchInterval: 15_000 });
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">Devices</h1>
        <p className="text-sm" style={{ color: 'var(--muted)' }}>Registered on first event. No patient identity is stored — only device IDs.</p></div>
      {q.isLoading && <Loading />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && q.data.devices.length === 0 && <Card><Empty title="No devices yet" hint="Devices appear after their first event." /></Card>}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {q.data?.devices.map(d => (
          <Card key={d.id} title={<span className="font-mono">{d.id}</span>} sub={`${d.kind} · ${d.events.toLocaleString('en-IN')} events`}
            right={<span className="text-xs" style={{ color: d.is_active ? 'var(--ok)' : 'var(--emergency)' }}>{d.is_active ? 'active' : 'deactivated'}</span>}>
            {d.last_event ? (
              <div className="space-y-1.5 text-sm">
                <div className="flex gap-2 items-center"><DestBadge d={d.last_event.destination} /><ReasonBadge r={d.last_event.reason} /></div>
                <div style={{ color: 'var(--muted)' }}>Criticality <b style={{ color: 'var(--text)' }}>{fmtCriticality(d.last_event.criticality)}</b>
                  {' · '}RTT {fmtLatency(d.last_event.last_rtt_ms)} → forecast {fmtLatency(d.last_event.predicted_rtt_ms)}</div>
                <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--muted)' }}>
                  <SourceBadge s={d.last_event.source} /> last seen {fmtTime(d.last_seen_at)}</div>
              </div>) : <p className="text-sm" style={{ color: 'var(--muted)' }}>No events.</p>}
          </Card>))}
      </div>
    </div>
  );
}
