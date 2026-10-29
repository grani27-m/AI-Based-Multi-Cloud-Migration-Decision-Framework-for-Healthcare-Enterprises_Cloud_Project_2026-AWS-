// src/pages/DecisionLab.tsx — what-if explorer. The browser only sends inputs; the server runs Tanmay's real engine.
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, type Decision } from '../lib/api';
import { fmtNum } from '../lib/utils';
import { Card, DestBadge, ErrorState, ReasonBadge, Select, tooltipStyle } from '../components/ui';

function Slider({ label, value, min, max, step, unit, onChange }:
  { label: string; value: number; min: number; max: number; step: number; unit?: string; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="flex text-sm mb-1"><span>{label}</span><span className="ml-auto tabular-nums font-semibold">{value}{unit}</span></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-[var(--cloud)]" />
    </label>
  );
}

export default function DecisionLab() {
  const [crit, setCrit] = useState(5);
  const [lat, setLat] = useState(80);
  const [cost, setCost] = useState(0.4);
  const [noForecast, setNoForecast] = useState(false);
  const [ws, setWs] = useState('eigenvector');
  const [res, setRes] = useState<Decision | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const sys = useQuery({ queryKey: ['system'], queryFn: api.system });

  useEffect(() => {
    const t = setTimeout(() => {
      api.preview({ criticality: crit, predicted_latency_ms: noForecast ? null : lat, cloud_cost_index: cost, weight_set: ws })
        .then(r => { setRes(r); setErr(null); }).catch(setErr);
    }, 120);
    return () => clearTimeout(t);
  }, [crit, lat, cost, ws, noForecast]);

  const ahp = sys.data?.decision_engine?.ahp;
  const contrib = res?.contributions?.edge ? Object.keys(res.contributions.edge).map(k => ({
    k, EDGE: res.contributions.edge![k], CLOUD: res.contributions.cloud![k] })) : [];

  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">Decision lab</h1>
        <p className="text-sm max-w-3xl" style={{ color: 'var(--muted)' }}>Move the inputs to see how the two-stage engine (hard safety vetoes, then AHP scoring)
          decides. Each change calls <code>POST /api/v1/decision/preview</code>, which runs the same <code>decide()</code> used for real events.
          Nothing is stored or executed.</p></div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Inputs">
          <div className="space-y-5">
            <Slider label="Patient criticality" value={crit} min={0} max={10} step={0.1} onChange={setCrit} />
            <Slider label="Predicted latency" value={lat} min={0} max={600} step={1} unit=" ms" onChange={setLat} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={noForecast} onChange={e => setNoForecast(e.target.checked)} />
              Forecast unavailable</label>
            <Slider label="Cloud cost index" value={cost} min={0} max={1} step={0.01} onChange={setCost} />
            <Select label="Weight set" value={ws} onChange={setWs} options={[['eigenvector', 'Eigenvector (default, verified)'],
              ['report', 'As printed in report'], ['column_normalisation', 'Column normalisation (old code)']]} />
          </div>
        </Card>
        <Card className="xl:col-span-2" title="Decision">
          {Boolean(err) && <ErrorState error={err} />}
          {res && <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-3xl"><DestBadge d={res.destination} /></span><ReasonBadge r={res.reason} />
              {res.edge_score != null && <span className="text-sm tabular-nums" style={{ color: 'var(--muted)' }}>
                EDGE {fmtNum(res.edge_score)} · CLOUD {fmtNum(res.cloud_score)}</span>}
            </div>
            <p className="text-sm">{res.explanation}</p>
            {contrib.length > 0 && <ResponsiveContainer width="100%" height={220}>
              <BarChart data={contrib}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="k" tick={{ fontSize: 12, fill: 'var(--text)' }} /><YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => Number(v).toFixed(4)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="EDGE" fill="var(--edge)" isAnimationActive={false} /><Bar dataKey="CLOUD" fill="var(--cloud)" isAnimationActive={false} />
              </BarChart></ResponsiveContainer>}
            {res.veto !== 'none' && <p className="text-xs" style={{ color: 'var(--muted)' }}>A veto fired, so the AHP scores were not computed.</p>}
          </div>}
        </Card>
      </div>
      {ahp && <Card title="AHP weights — verification" sub="Computed live by src/decision/ahp.py from the pairwise matrix">
        <div className="overflow-x-auto"><table className="text-sm w-full">
          <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th className="py-1">Method</th><th>Criticality</th><th>Latency</th><th>Cost</th><th>CR</th></tr></thead>
          <tbody>
            <tr className="border-t" style={{ borderColor: 'var(--border)' }}><td className="py-1">Principal eigenvector (used)</td>
              {['criticality', 'latency', 'cost'].map(k => <td key={k} className="tabular-nums">{ahp.eigenvector.weights[k].toFixed(4)}</td>)}
              <td className="tabular-nums">{ahp.eigenvector.cr_ri_0_58.toFixed(4)} (RI 0.58) · {ahp.eigenvector.cr_ri_0_52.toFixed(4)} (RI 0.52)</td></tr>
            <tr className="border-t" style={{ borderColor: 'var(--border)' }}><td className="py-1">Column normalisation (old code)</td>
              {['criticality', 'latency', 'cost'].map(k => <td key={k} className="tabular-nums">{ahp.column_normalisation.weights[k].toFixed(4)}</td>)}
              <td className="tabular-nums">{ahp.column_normalisation.cr_ri_0_58.toFixed(4)}</td></tr>
            <tr className="border-t" style={{ borderColor: 'var(--border)' }}><td className="py-1">Printed in report</td>
              {['criticality', 'latency', 'cost'].map(k => <td key={k} className="tabular-nums">{ahp.reported.weights[k].toFixed(4)}</td>)}
              <td className="tabular-nums">{ahp.reported.cr}</td></tr>
          </tbody></table></div>
        <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>{ahp.note}</p>
      </Card>}
    </div>
  );
}
