// src/pages/MultiCloud.tsx — UI by Rani Gupta for Tanmay Kapoor's src/decision/candidates.py
// Ranks the local EDGE node against several cloud destinations with POST /api/v1/decision/rank.
// Nothing is stored or executed. The default candidates are HYPOTHETICAL; "use latest real forecast" fills cloud 1
// with the LSTM forecast of the most recent replayed (real-data) event in the database.
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Plus, Trash2, Play, Download } from 'lucide-react';
import { api, type Ranking } from '../lib/api';
import { fmtReason } from '../lib/utils';
import { Btn, Card, Empty, ErrorState, Select, tooltipStyle } from '../components/ui';

interface Row { name: string; lat: string; cost: string }
const START: Row[] = [
  { name: 'cloud-mumbai (hypothetical)', lat: '28', cost: '0.55' },
  { name: 'cloud-stockholm (hypothetical)', lat: '145', cost: '0.25' },
  { name: 'cloud-far (hypothetical)', lat: '320', cost: '0.10' },
];

export default function MultiCloud() {
  const [crit, setCrit] = useState(3);
  const [ws, setWs] = useState('eigenvector');
  const [rows, setRows] = useState<Row[]>(START);
  const realQ = useQuery({ queryKey: ['latest-replay'], queryFn: () => api.events({ limit: 1, source: 'replay' }) });
  const m = useMutation({
    mutationFn: () => api.rank({ criticality: crit, weight_set: ws,
      clouds: rows.map(r => ({ name: r.name.trim(), predicted_latency_ms: r.lat.trim() === '' ? null : Number(r.lat), cost_index: Number(r.cost) })) }),
  });
  const r: Ranking | undefined = m.data;
  const set = (i: number, k: keyof Row, v: string) => setRows(rs => rs.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const latest = realQ.data?.items[0];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">Multi-cloud ranking</h1>
        <p className="text-sm max-w-3xl" style={{ color: 'var(--muted)' }}>
          The same two-stage engine as every routing decision (safety vetoes, then AHP), applied to the edge node and up to
          ten cloud destinations. A cloud with no forecast or a forecast ≥ 300 ms is excluded; if none is admissible the reading stays on EDGE.
          Candidate values below are <b>hypothetical</b> unless you load the latest real forecast.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <Card className="xl:col-span-2" title="Inputs" sub="Edit the table, then rank">
          <label className="block text-sm mb-1">Patient criticality <b className="tabular-nums">{crit.toFixed(1)}</b> / 10
            {crit >= 9 && <span className="ml-2 text-xs font-semibold" style={{ color: 'var(--emergency)' }}>≥ 9 → emergency override</span>}</label>
          <input type="range" min={0} max={10} step={0.1} value={crit} onChange={e => setCrit(Number(e.target.value))} className="w-full" aria-label="criticality" />
          <div className="my-3"><Select label="Weight set" value={ws} onChange={setWs}
            options={[['eigenvector', 'eigenvector (default)'], ['column_normalisation', 'column normalisation'], ['report', 'report values']]} /></div>
          <table className="w-full text-sm table-fixed">
            <colgroup><col style={{ width: '52%' }} /><col style={{ width: '22%' }} /><col style={{ width: '20%' }} /><col /></colgroup>
            <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th>Cloud destination</th><th>Forecast ms</th><th>Cost 0–1</th><th /></tr></thead>
            <tbody>{rows.map((x, i) => (
              <tr key={i}>
                {(['name', 'lat', 'cost'] as (keyof Row)[]).map(k => (
                  <td key={k} className="py-1 pr-1"><input value={x[k]} onChange={e => set(i, k, e.target.value)} aria-label={`${k} ${i + 1}`}
                    placeholder={k === 'lat' ? 'none' : ''}
                    className={`rounded-md border px-2 py-1 text-sm w-full ${k === 'name' ? '' : 'tabular-nums'}`}
                    style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} /></td>))}
                <td><button onClick={() => setRows(rs => rs.filter((_, j) => j !== i))} disabled={rows.length <= 1} aria-label="remove"
                  className="p-1 disabled:opacity-30"><Trash2 size={14} style={{ color: 'var(--emergency)' }} /></button></td>
              </tr>))}</tbody>
          </table>
          <div className="flex flex-wrap gap-2 mt-3">
            <Btn kind="ghost" onClick={() => setRows(rs => [...rs, { name: `cloud-${rs.length + 1}`, lat: '60', cost: '0.4' }])} disabled={rows.length >= 10}><Plus size={14} />Add cloud</Btn>
            <Btn kind="ghost" disabled={!latest?.predicted_rtt_ms} onClick={() => latest && setRows(rs => [{ name: `real forecast · ${latest.device_id}`,
              lat: String(latest.predicted_rtt_ms?.toFixed(1)), cost: String(latest.cloud_cost_index) }, ...rs.slice(1)])}>
              <Download size={14} />Use latest real forecast</Btn>
            <Btn onClick={() => m.mutate()} disabled={m.isPending}><Play size={14} />Rank destinations</Btn>
          </div>
          {latest && <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>Latest replay event: {latest.event_id} · LSTM {latest.predicted_rtt_ms?.toFixed(1)} ms ·
            cost index {latest.cloud_cost_index} (synthetic)</p>}
        </Card>

        <Card className="xl:col-span-3" title="Ranking" sub={r ? `${r.engine_version} · weights ${Object.entries(r.weights).map(([k, v]) => `${k} ${v.toFixed(3)}`).join(' · ')}` : 'press Rank destinations'}>
          {m.error && <ErrorState error={m.error} />}
          {!r && !m.error && <Empty title="No ranking yet" hint="The request goes to POST /api/v1/decision/rank on the running backend." />}
          {r && <>
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <span className="text-sm" style={{ color: 'var(--muted)' }}>Destination</span>
              <span className="rounded-lg px-3 py-1 text-sm font-bold text-white" style={{ background: r.destination_kind === 'edge' ? 'var(--edge)' : 'var(--cloud)' }}>{r.destination}</span>
              <span className="text-sm">{fmtReason(r.reason)}</span>
            </div>
            {r.ranking.some(c => c.score != null) && <ResponsiveContainer width="100%" height={Math.max(140, 44 * r.ranking.length)}>
              <BarChart layout="vertical" data={r.ranking.filter(c => c.score != null).map(c => ({ n: c.name, s: +(c.score ?? 0).toFixed(4), kind: c.kind, win: c.name === r.destination }))} margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <YAxis type="category" dataKey="n" width={210} tick={{ fontSize: 11, fill: 'var(--text)' }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="s" name="AHP score" isAnimationActive={false}>
                  {r.ranking.filter(c => c.score != null).map(c => <Cell key={c.name} fill={c.kind === 'edge' ? 'var(--edge)' : 'var(--cloud)'}
                    fillOpacity={c.name === r.destination ? 1 : 0.45} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>}
            <table className="w-full text-sm mt-2">
              <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th>#</th><th>Candidate</th><th>Score</th><th>Status</th><th>Normalised inputs</th></tr></thead>
              <tbody>{r.ranking.map((c, i) => (
                <tr key={c.name} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1.5 pr-2">{i + 1}</td><td className="font-medium pr-3">{c.name}</td><td className="tabular-nums pr-3">{c.score?.toFixed(4) ?? '—'}</td>
                  <td className="pr-3" style={{ color: c.admissible ? 'var(--ok)' : 'var(--veto)' }}>{c.admissible ? 'admissible' : `excluded: ${c.excluded_reason}`}</td>
                  <td className="text-xs">{Object.entries(c.normalised ?? {}).map(([k, v]) => typeof v === 'number' ? `${k} ${v.toFixed(3)}` : `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}</td></tr>))}</tbody>
            </table>
            <p className="text-sm mt-3">{r.explanation}</p>
          </>}
        </Card>
      </div>
    </div>
  );
}
