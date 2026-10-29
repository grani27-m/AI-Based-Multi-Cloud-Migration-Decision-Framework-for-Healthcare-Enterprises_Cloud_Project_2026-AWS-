// src/pages/Overview.tsx — KPIs, latency forecast vs observed, routing split, reasons, reconciliation.
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart, ReferenceLine,
  ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, AlertTriangle, BellRing, Cloud, Cpu, ShieldCheck } from 'lucide-react';
import { api } from '../lib/api';
import { fmtCount, fmtPct, fmtReason, fmtTimeShort } from '../lib/utils';
import { Card, Empty, ErrorState, Kpi, Loading, Select, tooltipStyle } from '../components/ui';

const SOURCES: [string, string][] = [['', 'All sources'], ['replay', 'Replay (real data)'], ['simulated', 'Simulated'],
  ['live', 'Live'], ['test', 'Test']];

export default function Overview() {
  const [source, setSource] = useState('');
  const sQ = useQuery({ queryKey: ['summary', source], queryFn: () => api.summary(source || undefined), refetchInterval: 10_000 });
  const tQ = useQuery({ queryKey: ['ts', source], queryFn: () => api.timeseries(150, source || undefined), refetchInterval: 10_000 });
  const s = sQ.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-xl font-bold">Routing overview</h1>
          <p className="text-sm" style={{ color: 'var(--muted)' }}>
            Every figure is computed by the API from the database. {s && <>Updated {fmtTimeShort(s.generated_at)} IST.</>}
          </p>
        </div>
        <div className="ml-auto"><Select label="Source" value={source} onChange={setSource} options={SOURCES} /></div>
      </div>

      {sQ.isLoading && <Loading />}
      {sQ.error && <ErrorState error={sQ.error} onRetry={() => sQ.refetch()} />}
      {s && s.events.total === 0 && (
        <Card><Empty title="No events stored yet"
          hint={<>Push real replayed data or simulated scenarios from <Link to="/admin" className="underline">Admin → Demo runner</Link>,
          or stream with <code>python -m scripts.stream_events</code>.</>} /></Card>)}

      {s && s.events.total > 0 && <>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <Kpi label="Events" value={fmtCount(s.events.total)} icon={Activity} accent="var(--cloud)"
            sub={`${fmtCount(s.events.by_status.completed ?? 0)} completed · ${fmtCount(s.events.by_status.failed ?? 0)} failed`} />
          <Kpi label="EDGE" value={fmtCount(s.decisions.edge.count)} icon={Cpu} accent="var(--edge)" sub={fmtPct(s.decisions.edge.pct)} />
          <Kpi label="CLOUD" value={fmtCount(s.decisions.cloud.count)} icon={Cloud} accent="var(--cloud)" sub={fmtPct(s.decisions.cloud.pct)} />
          <Kpi label="Overrides" value={fmtCount(s.decisions.by_reason.override_critical_patient)} icon={AlertTriangle}
            accent="var(--emergency)" sub={`emergency · ${fmtCount(s.decisions.by_reason.network_degradation_veto)} network vetoes`} />
          <Kpi label="Alerts" value={fmtCount(s.alerts.triggered)} icon={BellRing} accent="var(--veto)"
            sub={`triggered · ${fmtCount(s.alerts.delivered)} delivered · ${fmtCount(s.alerts.failed)} failed`} />
          <Kpi label="LSTM forecasts" value={fmtCount(s.predictions.by_method.lstm ?? 0)} icon={ShieldCheck} accent="var(--ok)"
            sub={`${fmtCount(s.predictions.by_method.persistence_fallback ?? 0)} persistence fallback`} />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <Card className="xl:col-span-2" title="Observed vs LSTM-predicted round-trip time"
            sub="Last observed RTT in each window and the model's next-interval forecast. Thresholds: 75 / 150 ms risk, 300 ms veto.">
            {tQ.error && <ErrorState error={tQ.error} />}
            {tQ.data && <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={tQ.data.items.map((p, i) => ({ ...p, i, edge: p.destination === 'EDGE' ? p.predicted_rtt_ms : null }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="i" tick={{ fontSize: 11, fill: 'var(--muted)' }} label={{ value: 'event (oldest → newest)', fontSize: 11, fill: 'var(--muted)', position: 'insideBottom', offset: -2 }} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} unit=" ms" width={62} scale="log" domain={[1, 'auto']} allowDataOverflow />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => (v == null ? '—' : `${Number(v).toFixed(1)} ms`)}
                  labelFormatter={(i) => { const p = tQ.data!.items[Number(i)]; return p ? `${p.device_id} · ${fmtReason(p.reason)}` : ''; }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={75} stroke="var(--veto)" strokeDasharray="4 4" />
                <ReferenceLine y={150} stroke="var(--emergency)" strokeDasharray="4 4" />
                <ReferenceLine y={300} stroke="var(--emergency)" label={{ value: 'veto 300 ms', fontSize: 10, fill: 'var(--emergency)' }} />
                <Line dataKey="last_rtt_ms" name="observed (last)" stroke="var(--veto)" dot={false} strokeWidth={1.2} strokeDasharray="3 2" isAnimationActive={false} />
                <Line dataKey="predicted_rtt_ms" name="LSTM forecast" stroke="var(--cloud)" dot={false} strokeWidth={1.6} isAnimationActive={false} />
                <Scatter dataKey="edge" name="routed to EDGE" fill="var(--edge)" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>}
          </Card>

          <Card title="EDGE vs CLOUD" sub={`${fmtCount(s.decisions.total)} routing decisions`}>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={[{ n: 'EDGE', v: s.decisions.edge.count }, { n: 'CLOUD', v: s.decisions.cloud.count }]}
                  dataKey="v" nameKey="n" innerRadius={62} outerRadius={96} paddingAngle={2} isAnimationActive={false}>
                  <Cell fill="var(--edge)" /><Cell fill="var(--cloud)" />
                </Pie>
                <Tooltip contentStyle={tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <Card title="Why readings were routed" sub="Decision reasons (all categories, including safe defaults)">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart layout="vertical" data={Object.entries(s.decisions.by_reason).map(([k, v]) => ({ k: fmtReason(k), v, raw: k }))}
                margin={{ left: 20 }}>
                <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--muted)' }} allowDecimals={false} />
                <YAxis type="category" dataKey="k" width={170} tick={{ fontSize: 11, fill: 'var(--text)' }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="v" name="decisions" isAnimationActive={false}>
                  {Object.keys(s.decisions.by_reason).map(k => <Cell key={k} fill={k === 'override_critical_patient' ? 'var(--emergency)'
                    : k === 'ahp_decision' ? 'var(--cloud)' : 'var(--veto)'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Alert accounting" sub="Triggered ≠ delivered: every channel attempt is logged">
            <table className="w-full text-sm">
              <tbody>{[['Triggered', s.alerts.triggered], ['Delivered (≥1 channel)', s.alerts.delivered], ['Failed', s.alerts.failed],
                ['No channel configured', s.alerts.not_configured], ['Recorded only (WARNING)', s.alerts.by_status.not_notified ?? 0],
                ['Pending dispatch', s.alerts.pending]].map(([k, v]) => (
                <tr key={k as string} className="border-b last:border-0" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1.5" style={{ color: 'var(--muted)' }}>{k}</td><td className="text-right tabular-nums font-medium">{fmtCount(v as number)}</td></tr>))}
              </tbody>
            </table>
          </Card>

          <Card title="Count reconciliation" sub="Checks the dashboard totals against the stored rows">
            <ul className="space-y-1.5 text-sm">
              {Object.entries(s.reconciliation).filter(([, v]) => typeof v === 'boolean').map(([k, v]) => (
                <li key={k} className="flex gap-2 items-start">
                  <span style={{ color: v ? 'var(--ok)' : 'var(--emergency)' }}>{v ? '✔' : '✘'}</span>
                  <span>{k.replace(/_/g, ' ')}</span></li>))}
              <li className="text-xs pt-1" style={{ color: 'var(--muted)' }}>
                Failed before decision: {String(s.reconciliation.failed_before_decision)} · in flight: {String(s.reconciliation.in_flight)}</li>
            </ul>
          </Card>
        </div>
      </>}
    </div>
  );
}
