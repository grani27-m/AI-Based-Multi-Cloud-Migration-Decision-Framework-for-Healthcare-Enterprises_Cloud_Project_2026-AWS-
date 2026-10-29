// src/pages/LiveMonitor.tsx — paginated event history with a full per-event trace (predict → decide → execute → alert).
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Pause, Play, X } from 'lucide-react';
import { api, type EventDetail } from '../lib/api';
import { fmtCriticality, fmtLatency, fmtNum, fmtTime, fmtTimeShort } from '../lib/utils';
import { Btn, Card, DestBadge, Empty, ErrorState, Loading, ReasonBadge, Select, SourceBadge, StatusBadge, tooltipStyle } from '../components/ui';

const PAGE = 25;

export default function LiveMonitor() {
  const [paused, setPaused] = useState(false);
  const [page, setPage] = useState(0);
  const [source, setSource] = useState('');
  const [dest, setDest] = useState('');
  const [reason, setReason] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ['events', page, source, dest, reason],
    queryFn: () => api.events({ limit: PAGE, offset: page * PAGE, source, destination: dest, reason }),
    refetchInterval: paused ? false : 4000,
  });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / PAGE)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div><h1 className="text-xl font-bold">Live events</h1>
          <p className="text-sm" style={{ color: 'var(--muted)' }}>Newest first · refreshes every 4 s · click a row for its full trace</p></div>
        <div className="ml-auto flex flex-wrap gap-3 items-center">
          <Select label="Source" value={source} onChange={v => { setSource(v); setPage(0); }}
            options={[['', 'All'], ['replay', 'Replay'], ['simulated', 'Simulated'], ['live', 'Live'], ['test', 'Test']]} />
          <Select label="Destination" value={dest} onChange={v => { setDest(v); setPage(0); }} options={[['', 'All'], ['EDGE', 'EDGE'], ['CLOUD', 'CLOUD']]} />
          <Select label="Reason" value={reason} onChange={v => { setReason(v); setPage(0); }} options={[['', 'All'],
            ['ahp_decision', 'AHP'], ['override_critical_patient', 'Emergency'], ['network_degradation_veto', 'Network veto'],
            ['prediction_unavailable_safe_default', 'No forecast']]} />
          <Btn kind="ghost" onClick={() => setPaused(p => !p)}>{paused ? <><Play size={14} /> Resume</> : <><Pause size={14} /> Pause</>}</Btn>
        </div>
      </div>

      <Card>
        {q.isLoading && <Loading />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data && q.data.items.length === 0 && <Empty title="No events match the filters" />}
        {q.data && q.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wide" style={{ color: 'var(--muted)' }}>
                {['Received', 'Device', 'Source', 'Criticality', 'Last RTT', 'Forecast', 'Destination', 'Reason', 'Status'].map(h =>
                  <th key={h} className="py-2 pr-3 font-semibold whitespace-nowrap">{h}</th>)}</tr></thead>
              <tbody>
                {q.data.items.map(e => (
                  <tr key={e.event_id} onClick={() => setSelected(e.event_id)} className="border-t cursor-pointer hover:opacity-80"
                    style={{ borderColor: 'var(--border)' }}>
                    <td className="py-2 pr-3 whitespace-nowrap tabular-nums">{fmtTimeShort(e.received_at)}</td>
                    <td className="pr-3 font-mono text-xs">{e.device_id}</td>
                    <td className="pr-3"><SourceBadge s={e.source} /></td>
                    <td className="pr-3 tabular-nums" style={{ color: e.criticality >= 9 ? 'var(--emergency)' : undefined }}>{fmtCriticality(e.criticality)}</td>
                    <td className="pr-3 tabular-nums">{fmtLatency(e.last_rtt_ms)}</td>
                    <td className="pr-3 tabular-nums">{fmtLatency(e.predicted_rtt_ms)}
                      {e.prediction_method === 'persistence_fallback' && <span className="ml-1 text-[10px]" style={{ color: 'var(--veto)' }}>fallback</span>}</td>
                    <td className="pr-3"><DestBadge d={e.destination} /></td>
                    <td className="pr-3"><ReasonBadge r={e.reason} /></td>
                    <td><StatusBadge s={e.status} /></td>
                  </tr>))}
              </tbody>
            </table>
          </div>)}
        {q.data && <div className="flex items-center gap-3 mt-4 text-xs" style={{ color: 'var(--muted)' }}>
          <span>{q.data.total.toLocaleString('en-IN')} events</span>
          <div className="ml-auto flex items-center gap-2">
            <Btn kind="ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</Btn>
            <span>Page {page + 1} / {pages}</span>
            <Btn kind="ghost" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Next</Btn>
          </div></div>}
      </Card>
      {selected && <EventDrawer id={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex gap-3 text-sm py-1 border-b last:border-0" style={{ borderColor: 'var(--border)' }}>
    <span className="w-40 shrink-0" style={{ color: 'var(--muted)' }}>{k}</span><span className="min-w-0 break-words">{v}</span></div>;
}

export function EventDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['event', id], queryFn: () => api.event(id) });
  const e: EventDetail | undefined = q.data;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" style={{ background: 'rgba(2,6,23,0.45)' }} onClick={onClose}>
      <aside className="w-full max-w-2xl h-full overflow-y-auto p-6 space-y-4" style={{ background: 'var(--page)' }}
        onClick={ev => ev.stopPropagation()}>
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-bold font-mono truncate">{id}</h2>
          <Link to={`/trace/${encodeURIComponent(id)}`} className="ml-auto text-xs font-medium underline shrink-0" style={{ color: 'var(--cloud)' }}>Open request trace</Link>
          <button onClick={onClose} className="p-1" aria-label="Close"><X size={18} /></button>
        </div>
        {q.isLoading && <Loading />}
        {q.error && <ErrorState error={q.error} />}
        {e && <>
          <Card title="1 · Telemetry" sub="as received and stored">
            <Row k="Device / source" v={<>{e.device_id} · <SourceBadge s={e.source} /></>} />
            <Row k="Observed" v={fmtTime(e.observed_at)} />
            <Row k="Criticality" v={<>{fmtCriticality(e.criticality.score)} <span className="text-xs" style={{ color: 'var(--muted)' }}>({e.criticality.method})</span></>} />
            {e.criticality.vitals && <Row k="Vitals" v={`HR ${e.criticality.vitals.hr} · RR ${e.criticality.vitals.resp} · SpO₂ ${e.criticality.vitals.spo2}%`} />}
            <Row k="Cloud cost index" v={fmtNum(e.cloud_cost_index, 3)} />
            {e.provenance && Object.keys(e.provenance).length > 0 &&
              <Row k="Provenance" v={<ul className="text-xs space-y-0.5">{Object.entries(e.provenance).map(([k, v]) => <li key={k}><b>{k}:</b> {String(v)}</li>)}</ul>} />}
            {e.network_window && <div className="mt-3"><ResponsiveContainer width="100%" height={120}>
              <LineChart data={e.network_window.map((o, i) => ({ i, rtt: o.rtt_avg_ms, loss: o.loss_pct }))}>
                <XAxis dataKey="i" hide /><YAxis width={40} tick={{ fontSize: 10, fill: 'var(--muted)' }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line dataKey="rtt" name="RTT ms" stroke="var(--cloud)" dot={false} isAnimationActive={false} />
              </LineChart></ResponsiveContainer>
              <p className="text-xs" style={{ color: 'var(--muted)' }}>The 20-round network window fed to the LSTM.</p></div>}
          </Card>
          {e.prediction && <Card title="2 · Prediction (Charles)">
            <Row k="Forecast next RTT" v={<b>{fmtLatency(e.prediction.predicted_rtt_ms)}</b>} />
            <Row k="Risk" v={e.prediction.risk} />
            <Row k="Method / model" v={`${e.prediction.method} · ${e.prediction.model_version}`} />
            <Row k="Horizon / inference" v={`${e.prediction.horizon_s} s ahead · ${e.prediction.inference_ms.toFixed(2)} ms`} />
          </Card>}
          {e.decision && <Card title="3 · Decision (Tanmay)">
            <Row k="Destination" v={<><DestBadge d={e.decision.destination} /> <ReasonBadge r={e.decision.reason} /></>} />
            <Row k="Explanation" v={e.decision.explanation} />
            {e.decision.edge_score != null && <Row k="Scores" v={`EDGE ${fmtNum(e.decision.edge_score)} vs CLOUD ${fmtNum(e.decision.cloud_score)}`} />}
            <Row k="Weights" v={`${e.decision.weight_set}: ` + Object.entries(e.decision.weights).map(([k, v]) => `${k} ${v.toFixed(4)}`).join(' · ')} />
            {e.decision.contributions.edge && <Row k="Contributions" v={<table className="text-xs"><thead><tr><th></th>
              {Object.keys(e.decision.contributions.edge).map(k => <th key={k} className="px-2">{k}</th>)}</tr></thead><tbody>
              {(['edge', 'cloud'] as const).map(side => <tr key={side}><td className="pr-2 font-semibold uppercase">{side}</td>
                {Object.values(e.decision!.contributions[side]!).map((v, i) => <td key={i} className="px-2 tabular-nums">{v.toFixed(3)}</td>)}</tr>)}
              </tbody></table>} />}
          </Card>}
          {e.execution && <Card title="4 · Execution (Rani)">
            <Row k="Status" v={<StatusBadge s={e.execution.status} />} />
            <Row k="Requested → final" v={`${e.execution.requested_destination} → ${e.execution.final_destination ?? 'none'}`} />
            <Row k="Adapter" v={<>{e.execution.adapter} <span className="text-xs" style={{ color: 'var(--muted)' }}>(local stand-in unless "aws-s3")</span></>} />
            <Row k="Output" v={<code className="text-xs">{e.execution.output_ref ?? '—'}</code>} />
            <Row k="Attempts" v={<ol className="text-xs space-y-0.5">{e.execution.attempt_log.map((a, i) =>
              <li key={i}>{a.destination} #{a.attempt}: {a.ok ? 'ok' : a.error} ({a.ms} ms)</li>)}</ol>} />
          </Card>}
          <Card title="5 · Alerts">
            {e.alerts.length === 0 ? <p className="text-sm" style={{ color: 'var(--muted)' }}>No alert for this event.</p> :
              e.alerts.map(a => <Row key={a.id} k={`#${a.id} ${a.severity}`} v={<>{a.kind} · <StatusBadge s={a.status} /></>} />)}
          </Card>
        </>}
      </aside>
    </div>
  );
}
