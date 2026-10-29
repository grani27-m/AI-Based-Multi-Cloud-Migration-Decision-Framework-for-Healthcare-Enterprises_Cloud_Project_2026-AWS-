// src/pages/Trace.tsx — Owner: Rani Gupta
// Request trace: follow ONE stored event through every stage. The graph is built from GET /api/v1/events/{id},
// /api/v1/alerts and /api/v1/audit (audit only for admin/auditor). Click a node to see the stored data for that stage.
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { api, type EventDetail } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { fmtCriticality, fmtLatency, fmtReason, fmtTime } from '../lib/utils';
import { Card, DestBadge, Empty, ErrorState, Loading, ReasonBadge, Select, SourceBadge, StatusBadge, tooltipStyle } from '../components/ui';

interface Node { id: string; x: number; y: number; title: string; sub: string; color: string; state: 'ok' | 'warn' | 'bad' | 'idle' }

const W = 940, H = 300;

function Graph({ nodes, edges, sel, onSel }: { nodes: Node[]; edges: [string, string][]; sel: string; onSel: (id: string) => void }) {
  const by = Object.fromEntries(nodes.map(n => [n.id, n]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="request flow graph">
      <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" /></marker></defs>
      {edges.map(([a, b]) => {
        const A = by[a], B = by[b], hot = sel === a || sel === b;
        return <line key={a + b} x1={A.x + 62} y1={A.y} x2={B.x - 66} y2={B.y} stroke={hot ? 'var(--cloud)' : 'var(--border)'}
          strokeWidth={hot ? 2.5 : 1.6} markerEnd="url(#arr)" />;
      })}
      {nodes.map(n => {
        const on = n.id === sel;
        const ring = n.state === 'bad' ? 'var(--emergency)' : n.state === 'warn' ? 'var(--veto)' : n.state === 'ok' ? n.color : 'var(--border)';
        return (
          <g key={n.id} onClick={() => onSel(n.id)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}
            onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onSel(n.id)}>
            <rect x={n.x - 62} y={n.y - 30} width={124} height={60} rx={12} fill="var(--surface)" stroke={ring} strokeWidth={on ? 3 : 1.5}
              style={{ filter: on ? 'drop-shadow(0 2px 6px rgba(0,0,0,.18))' : 'none' }} />
            <rect x={n.x - 62} y={n.y - 30} width={6} height={60} rx={3} fill={n.color} />
            <text x={n.x - 48} y={n.y - 6} fontSize={12.5} fontWeight={600} fill="var(--text)">{n.title}</text>
            <text x={n.x - 48} y={n.y + 13} fontSize={11} fill="var(--muted)">{n.sub.length > 19 ? n.sub.slice(0, 18) + '…' : n.sub}</text>
          </g>);
      })}
    </svg>
  );
}

function KV({ rows }: { rows: [string, React.ReactNode][] }) {
  return <table className="w-full text-sm"><tbody>{rows.map(([k, v]) => (
    <tr key={k} className="border-b last:border-0 align-top" style={{ borderColor: 'var(--border)' }}>
      <td className="py-1.5 pr-3 whitespace-nowrap" style={{ color: 'var(--muted)' }}>{k}</td><td className="py-1.5 break-all">{v ?? '—'}</td></tr>))}</tbody></table>;
}

export default function Trace() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const canAudit = user?.role === 'admin' || user?.role === 'auditor';
  const [source, setSource] = useState('');
  const [sel, setSel] = useState('decision');
  const listQ = useQuery({ queryKey: ['trace-list', source], queryFn: () => api.events({ limit: 40, source: source || undefined }), refetchInterval: 10_000 });
  const eid = id ?? listQ.data?.items[0]?.event_id;
  const evQ = useQuery({ queryKey: ['event', eid], queryFn: () => api.event(eid!), enabled: !!eid });
  const alQ = useQuery({ queryKey: ['alerts-all'], queryFn: () => api.alerts({ limit: 500 }), enabled: !!eid });
  const auQ = useQuery({ queryKey: ['audit-1000'], queryFn: () => api.audit(1000), enabled: !!eid && canAudit });
  const d: EventDetail | undefined = evQ.data;

  const alerts = useMemo(() => (alQ.data?.items ?? []).filter(a => a.event_id === eid), [alQ.data, eid]);
  const audit = useMemo(() => {
    const res = new Set([`event/${eid}`, ...alerts.map(a => `alert/${a.id}`)]);
    return (auQ.data?.items ?? []).filter(a => res.has(a.resource)).sort((a, b) => a.id - b.id);
  }, [auQ.data, alerts, eid]);

  if (listQ.isLoading) return <Loading />;
  if (listQ.error) return <ErrorState error={listQ.error} />;
  if (!eid) return <Card><Empty title="No events stored yet" hint="Send events from Admin → Demo runner or python 03_run_execution_demo.py." /></Card>;

  const p = d?.prediction, dec = d?.decision, ex = d?.execution;
  const nodes: Node[] = d ? [
    { id: 'device', x: 75, y: 150, title: 'Device', sub: d.device_id, color: 'var(--muted)', state: 'ok' },
    { id: 'api', x: 225, y: 150, title: 'API · validate', sub: `${d.network_window?.length ?? 0} rounds · JWT`, color: 'var(--model)', state: d.status === 'failed' && !dec ? 'bad' : 'ok' },
    { id: 'criticality', x: 375, y: 60, title: 'Criticality', sub: `${d.criticality.score.toFixed(2)} · ${d.criticality.method}`, color: 'var(--emergency)', state: d.criticality.score >= 9 ? 'warn' : 'ok' },
    { id: 'prediction', x: 375, y: 240, title: 'LSTM forecast', sub: p ? `${p.predicted_rtt_ms.toFixed(1)} ms · ${p.method}` : 'none', color: 'var(--model)', state: p ? (p.method === 'lstm' ? 'ok' : 'warn') : 'bad' },
    { id: 'decision', x: 530, y: 150, title: 'AHP decision', sub: dec ? `${dec.destination} · ${fmtReason(dec.reason)}` : 'none', color: 'var(--edge)', state: dec ? (dec.veto !== 'none' ? 'warn' : 'ok') : 'bad' },
    { id: 'execution', x: 690, y: 150, title: 'Execution', sub: ex ? `${ex.status} → ${ex.final_destination ?? '—'}` : 'none', color: 'var(--cloud)', state: !ex ? 'idle' : ex.status === 'success' ? 'ok' : ex.status === 'failed' ? 'bad' : 'warn' },
    { id: 'alerts', x: 860, y: 60, title: 'Alerts', sub: `${alerts.length} · ${alerts.map(a => a.status).join(', ') || 'none'}`, color: 'var(--veto)', state: alerts.length ? 'warn' : 'idle' },
    { id: 'audit', x: 860, y: 240, title: 'Audit log', sub: canAudit ? `${audit.length} entries` : 'auditor only', color: 'var(--text)', state: canAudit ? 'ok' : 'idle' },
  ] : [];
  const edges: [string, string][] = [['device', 'api'], ['api', 'criticality'], ['api', 'prediction'], ['criticality', 'decision'],
    ['prediction', 'decision'], ['decision', 'execution'], ['execution', 'alerts'], ['execution', 'audit']];

  const win = (d?.network_window ?? []).map((o, i) => ({ i, t: o.timestamp, rtt: o.rtt_avg_ms, loss: o.loss_pct }));
  if (p && win.length) win.push({ i: win.length, t: 'forecast', rtt: null, loss: 0, f: p.predicted_rtt_ms } as never);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-xl font-bold">Request trace</h1>
          <p className="text-sm" style={{ color: 'var(--muted)' }}>One stored event, stage by stage, exactly as the database recorded it. Click any box.</p>
        </div>
        <div className="ml-auto flex gap-3 items-center">
          <Select label="Source" value={source} onChange={setSource} options={[['', 'All'], ['replay', 'Replay (real)'], ['simulated', 'Simulated'], ['test', 'Test']]} />
          <Select label="Event" value={eid} onChange={v => nav(`/trace/${encodeURIComponent(v)}`)}
            options={[...(listQ.data?.items ?? []).map(e => [e.event_id, `${e.event_id.slice(0, 38)} · ${e.destination ?? '—'}`] as [string, string]),
              ...(id && !listQ.data?.items.some(e => e.event_id === id) ? [[id, id] as [string, string]] : [])]} />
        </div>
      </div>

      {evQ.error && <ErrorState error={evQ.error} />}
      {evQ.isLoading && <Loading />}
      {d && <>
        <Card title={<span className="flex flex-wrap items-center gap-2 font-mono text-xs">{d.event_id} <SourceBadge s={d.source} /> <DestBadge d={dec?.destination} />
          {dec && <ReasonBadge r={dec.reason} />}</span>} sub={`observed ${fmtTime(d.observed_at)} · received ${fmtTime(d.received_at)}`}>
          <Graph nodes={nodes} edges={edges} sel={sel} onSel={setSel} />
        </Card>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card title={nodes.find(n => n.id === sel)?.title} sub="stored data for the selected stage">
            {sel === 'device' && <KV rows={[['Device', d.device_id], ['Source', <SourceBadge s={d.source} />], ['Observed at', fmtTime(d.observed_at)],
              ['Provenance', <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(d.provenance, null, 1)}</pre>]]} />}
            {sel === 'api' && <KV rows={[['Endpoint', 'POST /api/v1/events (Bearer JWT, role device/doctor/admin)'], ['Status', <StatusBadge s={d.status} />],
              ['Error', d.error], ['Window', `${d.network_window?.length} rounds, strictly increasing timestamps`], ['Cloud cost index', d.cloud_cost_index],
              ['Duplicate?', String(d.duplicate)]]} />}
            {sel === 'criticality' && <KV rows={[['Score', fmtCriticality(d.criticality.score)], ['Method', d.criticality.method],
              ['Vitals', d.criticality.vitals ? JSON.stringify(d.criticality.vitals) : 'criticality supplied directly'],
              ['Emergency threshold', '≥ 9.0 → EDGE override']]} />}
            {sel === 'prediction' && (p ? <KV rows={[['Predicted RTT', fmtLatency(p.predicted_rtt_ms)], ['Last observed RTT', fmtLatency(p.last_observed_rtt_ms)],
              ['Method', p.method], ['Model', p.model_version], ['Horizon', `${p.horizon_s} s`], ['Risk class', p.risk], ['Inference', `${p.inference_ms.toFixed(2)} ms`]]} />
              : <Empty title="No prediction stored" />)}
            {sel === 'decision' && (dec ? <>
              <KV rows={[['Destination', <DestBadge d={dec.destination} />], ['Reason', <ReasonBadge r={dec.reason} />], ['Veto', dec.veto],
                ['EDGE score', dec.edge_score?.toFixed(4)], ['CLOUD score', dec.cloud_score?.toFixed(4)], ['Weight set', dec.weight_set],
                ['Weights', Object.entries(dec.weights).map(([k, v]) => `${k} ${v.toFixed(4)}`).join(' · ')],
                ['Normalised', Object.entries(dec.normalised ?? {}).map(([k, v]) => `${k} ${Number(v).toFixed(3)}`).join(' · ')], ['Engine', dec.engine_version]]} />
              <p className="text-sm mt-3">{dec.explanation}</p></> : <Empty title="No decision stored" />)}
            {sel === 'execution' && (ex ? <>
              <KV rows={[['Status', <StatusBadge s={ex.status} />], ['Requested → final', `${ex.requested_destination} → ${ex.final_destination ?? 'none'}`],
                ['Adapter', ex.adapter], ['Attempts', ex.attempts], ['Duration', `${ex.duration_ms.toFixed(1)} ms`], ['Output', ex.output_ref], ['Error', ex.error]]} />
              <table className="w-full text-xs mt-3"><thead><tr className="text-left" style={{ color: 'var(--muted)' }}><th>#</th><th>destination</th><th>adapter</th><th>ok</th><th>ms</th><th>error</th></tr></thead>
                <tbody>{ex.attempt_log.map((a, i) => <tr key={i} className="border-t" style={{ borderColor: 'var(--border)' }}><td className="py-1">{a.attempt}</td>
                  <td>{a.destination}</td><td>{a.adapter}</td><td style={{ color: a.ok ? 'var(--ok)' : 'var(--emergency)' }}>{a.ok ? 'yes' : 'no'}</td>
                  <td>{a.ms.toFixed(1)}</td><td className="break-all">{a.error}</td></tr>)}</tbody></table></> : <Empty title="Not executed" />)}
            {sel === 'alerts' && (alerts.length ? alerts.map(a => (
              <div key={a.id} className="mb-4">
                <div className="flex gap-2 items-center text-sm font-medium">#{a.id} {a.severity} · {a.kind} <StatusBadge s={a.status} /></div>
                <p className="text-xs my-1" style={{ color: 'var(--muted)' }}>{a.message}</p>
                <table className="w-full text-xs"><tbody>{a.deliveries.map((x, i) => <tr key={i} className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1">{x.channel}</td><td>attempt {x.attempt}</td><td><StatusBadge s={x.status} /></td><td className="break-all">{x.detail}</td></tr>)}</tbody></table>
              </div>)) : <Empty title="No alert for this event" hint="Alerts are raised for emergency overrides, network vetoes and execution failures." />)}
            {sel === 'audit' && (!canAudit ? <Empty title="Audit log is visible to admin and auditor roles" /> : audit.length ? (
              <table className="w-full text-xs"><thead><tr className="text-left" style={{ color: 'var(--muted)' }}><th>id</th><th>actor</th><th>action</th><th>resource</th><th>hash</th></tr></thead>
                <tbody>{audit.map(a => <tr key={a.id} className="border-t" style={{ borderColor: 'var(--border)' }}><td className="py-1">{a.id}</td><td>{a.actor}</td>
                  <td>{a.action}</td><td>{a.resource}</td><td className="font-mono">{a.hash.slice(0, 12)}… ← {a.prev_hash.slice(0, 8)}…</td></tr>)}</tbody></table>)
              : <Empty title="No audit rows found in the last 1000 entries" />)}
          </Card>

          <Card title="Network window used for this decision" sub="20 observed rounds (avg RTT) and the LSTM forecast for the next round">
            {win.length ? <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={win}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="i" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} unit=" ms" width={60} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => (v == null ? '—' : `${Number(v).toFixed(1)} ms`)}
                  labelFormatter={(i) => win[Number(i)]?.t === 'forecast' ? 'forecast' : fmtTime(win[Number(i)]?.t)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={300} stroke="var(--emergency)" strokeDasharray="4 4" label={{ value: 'veto 300 ms', fontSize: 10, fill: 'var(--emergency)' }} />
                <Line dataKey="rtt" name="observed RTT" stroke="var(--veto)" strokeWidth={1.6} isAnimationActive={false} connectNulls={false} />
                <Scatter dataKey="f" name="LSTM forecast" fill="var(--model)" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer> : <Empty title="No window stored" />}
          </Card>
        </div>
      </>}
    </div>
  );
}
