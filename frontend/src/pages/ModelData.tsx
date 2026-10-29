// src/pages/ModelData.tsx — Charles's evidence: real datasets, cleaning counts, splits, training and held-out evaluation.
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, type MetricRow } from '../lib/api';
import { fmtCount, fmtTime } from '../lib/utils';
import { Card, ErrorState, Loading, tooltipStyle } from '../components/ui';

const NAMES: Record<string, string> = { lstm: 'LSTM', persistence: 'Persistence', mean20: 'Mean of 20', ewma: 'EWMA (α=0.3)', ridge: 'Ridge (linear)' };

export default function ModelData() {
  const q = useQuery({ queryKey: ['system'], queryFn: api.system });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data!;
  const rq = s.datasets?.ripe_atlas_quality, sp = s.datasets?.ripe_atlas_splits, bq = s.datasets?.bidmc_quality;
  const ev = s.model_evaluation, m = s.model, hist = s.training_history;
  const overall: [string, MetricRow][] = ev ? Object.entries(ev.overall) as [string, MetricRow][] : [];

  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">Model &amp; data</h1>
        <p className="text-sm" style={{ color: 'var(--muted)' }}>All numbers are read from the files produced by the pipeline (dataset/metadata, models/, results/model).</p></div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="RIPE Atlas network data (real)" sub="Built-in ping measurements 1001 (k-root) and 1004 (f-root), 20 public probes in India">
          {rq ? <table className="w-full text-sm"><tbody>
            {[['Raw results downloaded', rq.rows_raw], ['Invalid (bad counts / errors)', rq.rows_raw - rq.rows_after_validity],
              ['Duplicates removed', rq.duplicates_removed], ['Clean rows', rq.rows_clean], ['  of which 100 % loss', rq.rows_total_loss],
              ['Series (probe × target)', rq.series], ['Rows with RTT ≥ 150 ms', rq.rows_rtt_ge_150ms], ['Rows with RTT ≥ 300 ms', rq.rows_rtt_ge_300ms]]
              .map(([k, v]) => <tr key={k as string} className="border-b last:border-0" style={{ borderColor: 'var(--border)' }}>
                <td className="py-1" style={{ color: 'var(--muted)' }}>{k}</td><td className="text-right tabular-nums">{fmtCount(v as number)}</td></tr>)}
          </tbody></table> : <p className="text-sm">Dataset metadata missing — run the data pipeline.</p>}
          {rq && <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>{fmtTime(rq.time_range_utc[0])} → {fmtTime(rq.time_range_utc[1])}. Median RTT {rq.rtt_avg_ms['50%']} ms, p99 {rq.rtt_avg_ms['99%']} ms.</p>}
        </Card>
        <Card title="Chronological splits" sub={sp?.method}>
          {sp && <table className="w-full text-sm"><tbody>{(['train', 'val', 'test'] as const).map(k =>
            <tr key={k} className="border-b last:border-0" style={{ borderColor: 'var(--border)' }}><td className="py-1.5 font-medium capitalize">{k}</td>
              <td className="text-xs" style={{ color: 'var(--muted)' }}>{sp[k][0].slice(0, 10)} → {sp[k][1].slice(0, 10)}</td>
              <td className="text-right tabular-nums">{fmtCount(sp.windows[k])} windows</td></tr>)}</tbody></table>}
          <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>Scaler fitted on training windows only. Model selection used validation; test was held out.</p>
        </Card>
        <Card title="PhysioNet BIDMC vitals (real)" sub="Used for patient criticality in replays — never fed to the network model">
          {bq && <table className="w-full text-sm"><tbody>
            {[['ICU recordings', bq.records], ['Rows (1 Hz)', bq.rows_raw], ['Clean rows', bq.rows_clean]].map(([k, v]) =>
              <tr key={k as string} className="border-b last:border-0" style={{ borderColor: 'var(--border)' }}><td className="py-1" style={{ color: 'var(--muted)' }}>{k}</td>
                <td className="text-right tabular-nums">{fmtCount(v as number)}</td></tr>)}</tbody></table>}
          <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>Licence: ODC Attribution. Criticality = partial NEWS2 (RR, SpO₂, HR) — illustrative, not clinically validated.</p>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Model" sub={m.loaded ? m.model_version : 'not loaded'}>
          {m.loaded ? <table className="w-full text-sm"><tbody>
            {[['Architecture', `LSTM ${m.architecture.units.join('→')} · dense ${m.architecture.dense} · dropout ${m.architecture.dropout}`],
              ['Parameters', fmtCount(m.architecture.params)], ['Window', `${m.window} rounds (≈80 min)`], ['Features', m.features.join(', ')],
              ['Target', `next RTT (${s.model?.training ? 'residual vs last RTT' : ''})`], ['Best epoch', `${m.training.best_epoch} of ${m.training.epochs_run}`],
              ['Loss / optimiser', `${m.training.loss} · ${m.training.optimizer}`], ['Trained', fmtTime(m.trained_at)]].map(([k, v]) =>
              <tr key={k} className="border-b last:border-0 align-top" style={{ borderColor: 'var(--border)' }}><td className="py-1 pr-2" style={{ color: 'var(--muted)' }}>{k}</td><td>{v}</td></tr>)}
          </tbody></table> : <ErrorState error={`No trained model: ${m.load_error}. Predictions use the labelled persistence fallback.`} />}
        </Card>
        <Card className="xl:col-span-2" title="Training history" sub="Loss on training and validation windows per epoch">
          {hist ? <ResponsiveContainer width="100%" height={230}>
            <LineChart data={hist.loss.map((v: number, i: number) => ({ e: i + 1, train: v, val: hist.val_loss[i] }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" /><XAxis dataKey="e" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} width={60} /><Tooltip contentStyle={tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="train" stroke="var(--cloud)" isAnimationActive={false} /><Line dataKey="val" stroke="var(--veto)" isAnimationActive={false} />
            </LineChart></ResponsiveContainer> : <p className="text-sm">No history.</p>}
        </Card>
      </div>

      {ev && <Card title={`Held-out test evaluation · ${fmtCount(ev.test_windows)} windows`}
        sub={`Test period ${ev.test_period_utc[0].slice(0, 10)} → ${ev.test_period_utc[1].slice(0, 10)}. Identical windows for every method. Objective 1 (beat persistence on MAE and RMSE): ${ev.objective_1_met ? 'MET' : 'NOT MET'}.`}>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th className="py-1">Method</th><th className="text-right">MAE ms</th>
              <th className="text-right">RMSE ms</th><th className="text-right">MAE skill</th><th className="text-right">Risk-class acc.</th></tr></thead>
            <tbody>{overall.map(([k, r]) => <tr key={k} className="border-t" style={{ borderColor: 'var(--border)', fontWeight: k === 'lstm' ? 600 : 400 }}>
              <td className="py-1.5">{NAMES[k] ?? k}</td><td className="text-right tabular-nums">{r.mae_ms.toFixed(3)}</td>
              <td className="text-right tabular-nums">{r.rmse_ms.toFixed(3)}</td>
              <td className="text-right tabular-nums" style={{ color: (r.mae_skill_vs_persistence ?? 0) > 0 ? 'var(--ok)' : (r.mae_skill_vs_persistence ?? 0) < 0 ? 'var(--emergency)' : undefined }}>
                {((r.mae_skill_vs_persistence ?? 0) * 100).toFixed(1)}%</td>
              <td className="text-right tabular-nums">{(r.risk_class_accuracy * 100).toFixed(2)}%</td></tr>)}</tbody></table>
            <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>Skill = 1 − MAE/MAE(persistence). Negative means worse than "next RTT = last RTT".</p></div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={overall.map(([k, r]) => ({ k: NAMES[k] ?? k, mae: r.mae_ms, rmse: r.rmse_ms, raw: k }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" /><XAxis dataKey="k" tick={{ fontSize: 11, fill: 'var(--text)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} unit=" ms" width={56} /><Tooltip contentStyle={tooltipStyle} formatter={(v) => `${Number(v).toFixed(3)} ms`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="mae" name="MAE" isAnimationActive={false}>{overall.map(([k]) => <Cell key={k} fill={k === 'lstm' ? 'var(--cloud)' : 'var(--muted)'} />)}</Bar>
              <Bar dataKey="rmse" name="RMSE" fill="var(--veto)" isAnimationActive={false} />
            </BarChart></ResponsiveContainer>
        </div>
        {ev.by_group && <div className="mt-4 overflow-x-auto"><table className="w-full text-xs">
          <thead><tr style={{ color: 'var(--muted)' }} className="text-left"><th className="py-1">Probe group</th>{overall.map(([k]) => <th key={k} className="text-right">{NAMES[k] ?? k} MAE</th>)}</tr></thead>
          <tbody>{Object.entries(ev.by_group).map(([g, rows]) => <tr key={g} className="border-t" style={{ borderColor: 'var(--border)' }}>
            <td className="py-1">{g.replace('_', ' ')} ({fmtCount((rows as Record<string, MetricRow>).lstm.n)})</td>
            {overall.map(([k]) => <td key={k} className="text-right tabular-nums">{(rows as Record<string, MetricRow>)[k].mae_ms.toFixed(3)}</td>)}</tr>)}</tbody></table></div>}
      </Card>}
    </div>
  );
}
