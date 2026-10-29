// src/pages/Project.tsx — Owner: Rani Gupta (UI); content from all three modules.
// "Project tour": the whole framework on one page. Every number is read live from the API
// (/api/v1/system/info, /api/v1/dashboard/summary, /api/v1/audit/verify); the text describes the code that produced it.
import { useState, type ElementType, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowRight, BellRing, BrainCircuit, CheckCircle2, CircleDashed, Cloud, Database, FlaskConical,
  GitBranch, Network, Rocket, Scale, Server, ShieldCheck, XCircle } from 'lucide-react';
import { api } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { fmtCount, fmtNum } from '../lib/utils';
import { Card, ErrorState, Loading, tooltipStyle } from '../components/ui';

type KV = [string, ReactNode][];
interface Stage {
  id: string; ws: string; title: string; owner: string; icon: ElementType; color: string;
  what: string[]; live: KV; files: string[]; verify: string[]; link?: [string, string];
}

const METHODS: [string, string][] = [['lstm', 'LSTM'], ['persistence', 'Persistence'], ['mean20', 'Mean of 20'],
  ['ewma', 'EWMA'], ['ridge', 'Ridge']];

function Chip({ ok, children }: { ok: boolean | null; children: ReactNode }) {
  const c = ok === null ? 'var(--muted)' : ok ? 'var(--ok)' : 'var(--veto)';
  const I = ok === null ? CircleDashed : ok ? CheckCircle2 : XCircle;
  return <span className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
    style={{ borderColor: c, color: c }}><I size={13} />{children}</span>;
}

export default function Project() {
  const { user } = useAuth();
  const canAudit = user?.role === 'admin' || user?.role === 'auditor';
  const infoQ = useQuery({ queryKey: ['system'], queryFn: api.system });
  const sQ = useQuery({ queryKey: ['summary', ''], queryFn: () => api.summary(), refetchInterval: 15_000 });
  const vQ = useQuery({ queryKey: ['verify'], queryFn: api.verify, enabled: canAudit });
  const hQ = useQuery({ queryKey: ['health'], queryFn: api.health });
  const [sel, setSel] = useState('data');

  if (infoQ.isLoading || sQ.isLoading) return <Loading label="Reading the live system…" />;
  if (infoQ.error) return <ErrorState error={infoQ.error} onRetry={() => infoQ.refetch()} />;
  const info = infoQ.data!, s = sQ.data;
  const q = info.datasets?.ripe_atlas_quality ?? {}, b = info.datasets?.bidmc_quality ?? {};
  const ev = info.model_evaluation ?? {}, ov = ev.overall ?? {};
  const ahp = info.decision_engine?.ahp ?? {}, w = ahp.eigenvector?.weights ?? {};
  const probes = Object.keys(q.rows_per_probe ?? {}).length;
  const ch = info.alert_channels_configured ?? {};
  const realChannels = Object.entries(ch).filter(([k, v]) => v && k !== 'mock-file').map(([k]) => k);
  const aws = info.aws_services ?? {};

  const stages: Stage[] = [
    { id: 'data', ws: 'A', title: 'Real datasets', owner: 'Charles Jehanabad', icon: Database, color: 'var(--data)',
      what: ['Downloads RIPE Atlas built-in ping measurements 1001 (k-root) and 1004 (f-root) from Indian probes through the public API, in weekly chunks, with a SHA-256 manifest per raw file.',
        'Validates, de-duplicates and cleans every result; builds chronological train / validation / test windows of 20 rounds with no leakage.',
        'Downloads PhysioNet BIDMC ICU numerics (53 records, checksums verified) for real vital signs.'],
      live: [['Raw RIPE Atlas files', fmtCount(q.raw_files)], ['Raw ping results', fmtCount(q.rows_raw)], ['Clean rows', fmtCount(q.rows_clean)],
        ['Probes returning data', `${probes} (1 reported 100 % loss → ${probes - 1} feed the model)`],
        ['Period (UTC)', (q.time_range_utc ?? []).map((t: string) => t.slice(0, 10)).join(' → ')],
        ['Windows train / val / test', `${fmtCount(q.windows?.train)} / ${fmtCount(q.windows?.val)} / ${fmtCount(q.windows?.test)}`],
        ['RTT ≥ 300 ms rows', fmtCount(q.rows_rtt_ge_300ms)], ['BIDMC records / clean rows', `${b.records} / ${fmtCount(b.rows_clean)}`]],
      files: ['data_ingestion/ripe_atlas.py', 'data_ingestion/physionet_bidmc.py', 'src/prediction/ripe_parser.py', 'src/prediction/dataset.py',
        'dataset/raw/ · dataset/metadata/'],
      verify: ['cd standalone_demos/charles', 'python 01_inspect_datasets.py', 'python 02_validate_and_preprocess.py'], link: ['/model', 'Model & data page'] },
    { id: 'lstm', ws: 'A', title: 'LSTM forecast', owner: 'Charles Jehanabad', icon: BrainCircuit, color: 'var(--model)',
      what: ['Stacked LSTM (64 → 32, dropout 0.2, dense 16) on 7 features predicts the next round-trip time 240 s ahead as a residual over the last value (Huber loss).',
        'Selected on the validation split only; evaluated once on the held-out test period against persistence, mean-of-20, EWMA and ridge.',
        'The API serves it with a NumPy re-implementation (identical to Keras within 1e-4), so no TensorFlow is needed in production.'],
      live: [['Model version', info.model?.model_version], ['Parameters', fmtCount(info.model?.architecture?.params)],
        ['Test windows', fmtCount(ev.test_windows)], ['Test MAE LSTM / persistence', `${fmtNum(ov.lstm?.mae_ms)} / ${fmtNum(ov.persistence?.mae_ms)} ms`],
        ['Test RMSE LSTM / persistence', `${fmtNum(ov.lstm?.rmse_ms)} / ${fmtNum(ov.persistence?.rmse_ms)} ms`],
        ['Best RMSE (EWMA / ridge)', `${fmtNum(ov.ewma?.rmse_ms)} / ${fmtNum(ov.ridge?.rmse_ms)} ms`],
        ['Forecasts served (this DB)', fmtCount(s?.predictions.by_method.lstm ?? 0)]],
      files: ['src/prediction/model.py', 'src/prediction/train.py', 'src/prediction/evaluate.py', 'src/prediction/predict_service.py', 'models/latency_lstm/'],
      verify: ['cd standalone_demos/charles', 'python 03_train_or_load_model.py', 'python 04_evaluate_predictions.py', 'streamlit run 05_dashboard.py'],
      link: ['/model', 'Model & data page'] },
    { id: 'decision', ws: 'B', title: 'AHP decision', owner: 'Tanmay Kapoor', icon: Scale, color: 'var(--edge)',
      what: ['Stage A safety vetoes: criticality ≥ 9 → EDGE (emergency override); predicted RTT ≥ 300 ms → EDGE (network veto); no forecast → EDGE (safe default).',
        'Stage B AHP: pairwise matrix over criticality, latency and cost → principal-eigenvector weights, consistency ratio checked; EDGE and CLOUD scored and compared.',
        'Multi-cloud extension ranks the edge against several cloud destinations with the same rules.'],
      live: [['Weights crit / latency / cost', `${fmtNum(w.criticality, 4)} / ${fmtNum(w.latency, 4)} / ${fmtNum(w.cost, 4)}`],
        ['λmax · CR (RI 0.58)', `${fmtNum(ahp.eigenvector?.lambda_max, 4)} · ${fmtNum(ahp.eigenvector?.cr_ri_0_58, 4)}`],
        ['Thresholds', `emergency ≥ ${info.decision_engine?.emergency_threshold}, veto ≥ ${info.decision_engine?.latency_veto_ms} ms`],
        ['Decisions stored', fmtCount(s?.decisions.total)],
        ['EDGE / CLOUD', `${fmtCount(s?.decisions.edge.count)} / ${fmtCount(s?.decisions.cloud.count)}`],
        ['Emergency overrides / network vetoes', `${fmtCount(s?.decisions.by_reason.override_critical_patient)} / ${fmtCount(s?.decisions.by_reason.network_degradation_veto)}`],
        ['Engine', info.decision_engine?.version]],
      files: ['src/decision/ahp.py', 'src/decision/override_rules.py', 'src/decision/router.py', 'src/decision/candidates.py', 'src/decision/criticality.py'],
      verify: ['cd standalone_demos/tanmay', 'python 02_calculate_ahp.py', 'python 03_compare_candidates.py', 'streamlit run 05_dashboard.py'],
      link: ['/decision-lab', 'Decision lab'] },
    { id: 'exec', ws: 'C', title: 'Execution', owner: 'Rani Gupta', icon: Server, color: 'var(--cloud)',
      what: ['Runs each decision on the chosen destination through an adapter, with up to 3 attempts and automatic CLOUD → EDGE fallback.',
        'Every attempt is stored (attempt log, duration, output reference, error). Idempotent: the same event_id is never executed twice.',
        'Adapters here are local stand-ins; CLOUD_ADAPTER=s3 writes to real Amazon S3.'],
      live: [['Edge adapter', info.execution?.edge_adapter], ['Cloud adapter', info.execution?.cloud_adapter],
        ['Max attempts', info.execution?.max_attempts],
        ...Object.entries(s?.executions.by_status ?? {}).map(([k, v]) => [`Executions ${k.replace(/_/g, ' ')}`, fmtCount(v)] as [string, ReactNode])],
      files: ['src/execution/adapters.py', 'backend/services/pipeline.py'],
      verify: ['cd standalone_demos/rani', 'python 03_run_execution_demo.py', 'python 04_inspect_audit_logs.py'], link: ['/trace', 'Request trace'] },
    { id: 'security', ws: 'C', title: 'Security & audit', owner: 'Rani Gupta', icon: ShieldCheck, color: 'var(--emergency)',
      what: ['JWT access tokens (issuer, audience, expiry) and PBKDF2 password hashes; four roles: admin, doctor, auditor, device.',
        'Every action is appended to a SHA-256 hash-chained audit log; editing, deleting or reordering a row is detected.',
        'Input validation, request-size limit, rate limiting, no secrets in the repository (.env is generated locally).'],
      live: [['Audit chain', canAudit ? (vQ.data ? (vQ.data.valid ? `VALID · ${fmtCount(vQ.data.checked)} entries` : `BROKEN at id ${vQ.data.first_broken_id}`) : '…')
        : 'needs admin / auditor role'], ['Head hash', canAudit && vQ.data?.head_hash ? `${vQ.data.head_hash.slice(0, 20)}…` : '—'],
        ['Your role', user?.role]],
      files: ['backend/security.py', 'backend/deps.py', 'backend/audit.py', 'backend/app.py'],
      verify: ['python 04_inspect_audit_logs.py --tamper-demo', 'python -m pytest tests -q'], link: ['/audit', 'Audit page'] },
    { id: 'api', ws: 'D', title: 'API, DB & alerts', owner: 'Rani Gupta', icon: BellRing, color: 'var(--veto)',
      what: ['FastAPI backend: one pipeline for every event (validate → predict → decide → execute → store → alert → audit).',
        'SQLAlchemy models with Alembic migrations on SQLite or PostgreSQL 16; data survives restarts.',
        'Alerts for emergencies, vetoes and failures; every delivery attempt is logged. "Mock delivered" means only the local mock file was written.'],
      live: [['API version', hQ.data?.version ?? info.api_version], ['Database', info.database?.dialect], ['Events stored', fmtCount(s?.events.total)],
        ['Alerts triggered', fmtCount(s?.alerts.triggered)], ['Really delivered', fmtCount(s?.alerts.delivered)],
        ['Mock delivered (nobody notified)', fmtCount(s?.alerts.mock_delivered ?? 0)],
        ['Real channels configured', realChannels.length ? realChannels.join(', ') : 'none (mock only)']],
      files: ['backend/routers/*.py', 'backend/models.py', 'migrations/', 'backend/services/alerts.py'],
      verify: ['python 01_initialize_database.py', 'python 02_start_backend.py', 'python 06_persistence_check.py'], link: ['/alerts', 'Alerts page'] },
    { id: 'deploy', ws: 'E', title: 'Deploy & reports', owner: 'Rani Gupta (lead) · all', icon: Rocket, color: 'var(--ok)',
      what: ['Multi-stage Docker image, docker-compose (API + PostgreSQL, optional MQTT and monitoring), GitHub Actions CI.',
        'AWS (eu-north-1) deployment templates and a staged, least-privilege guide; the team runs the commands with their own account.',
        'Reports: dataset, model evaluation, routing evaluation, security & tests, deployment, final status.'],
      live: [['AWS status', aws.note ? String(aws.note).split('.')[0] : '—'], ['Planned services', (aws.services ?? []).map((x: { service: string }) => x.service).join(', ')]],
      files: ['Dockerfile', 'docker-compose.yml', '.github/workflows/ci.yml', 'infra/aws/', 'reports/'],
      verify: ['docker compose up --build', 'see docs/AWS_DEPLOYMENT.md'], link: ['/system', 'System page'] },
  ];
  const st = stages.find(x => x.id === sel)!;

  const modelRows = METHODS.filter(([k]) => ov[k]).map(([k, l]) => ({ m: l, k, MAE: +ov[k].mae_ms.toFixed(3), RMSE: +ov[k].rmse_ms.toFixed(3) }));
  const weightRows = Object.entries(w).map(([k, v]) => ({ k, v: +(v as number).toFixed(4) }));
  const team = [
    { ws: 'A', name: 'Prediction & data pipeline', who: 'Charles Jehanabad · 24BIT0522', demo: 'standalone_demos/charles' },
    { ws: 'B', name: 'Decision engine (AHP + vetoes, multi-cloud)', who: 'Tanmay Kapoor · 24BIT0079', demo: 'standalone_demos/tanmay' },
    { ws: 'C', name: 'Execution & security', who: 'Rani Gupta · 24BIT0543', demo: 'standalone_demos/rani' },
    { ws: 'D', name: 'API, database, dashboard, monitoring', who: 'Rani Gupta (lead); Model & Decision pages with Charles / Tanmay', demo: 'standalone_demos/rani' },
    { ws: 'E', name: 'Deployment, integration, reporting', who: 'Rani Gupta (lead) · all members', demo: 'repository root' },
  ];

  return (
    <div className="space-y-5">
      {/* hero */}
      <section className="rounded-2xl border p-6 md:p-8 relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, color-mix(in srgb, var(--cloud) 10%, var(--surface)), var(--surface) 55%, color-mix(in srgb, var(--edge) 10%, var(--surface)))', borderColor: 'var(--border)' }}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em]" style={{ color: 'var(--cloud)' }}>{info.course}</div>
        <h1 className="text-2xl md:text-3xl font-bold mt-2 max-w-3xl leading-tight">{info.project}</h1>
        <p className="mt-3 text-sm max-w-3xl" style={{ color: 'var(--muted)' }}>
          For every reading from a hospital device, the framework forecasts the network round-trip time with an LSTM trained on
          real RIPE Atlas measurements, scores the patient's criticality from vital signs, decides between the local edge node and the
          cloud with AHP plus hard safety vetoes, executes the work with retry and fallback, and records every step in a tamper-evident audit log.
        </p>
        <div className="flex flex-wrap gap-2 mt-4">
          <Chip ok>Real data · RIPE Atlas {fmtCount(q.rows_raw)} pings</Chip>
          <Chip ok>Real data · PhysioNet BIDMC {b.records} ICU records</Chip>
          <Chip ok={!!ov.lstm && ov.lstm.mae_ms < ov.persistence.mae_ms}>LSTM beats persistence on held-out test</Chip>
          <Chip ok={canAudit ? !!vQ.data?.valid : null}>Audit chain {canAudit ? (vQ.data?.valid ? 'valid' : 'checking…') : '(auditor view)'}</Chip>
          <Chip ok={realChannels.length > 0 ? true : false}>Alerts: {realChannels.length ? realChannels.join(', ') : 'mock only'}</Chip>
          <Chip ok={null}>AWS: not deployed yet</Chip>
        </div>
        <div className="flex flex-wrap gap-3 mt-5 text-sm">
          {info.team?.map((m: { name: string; reg: string; module: string }) => (
            <div key={m.reg} className="rounded-lg border px-3 py-2" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
              <div className="font-semibold">{m.name} <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>{m.reg}</span></div>
              <div className="text-xs" style={{ color: 'var(--muted)' }}>{m.module}</div>
            </div>))}
        </div>
      </section>

      {/* pipeline */}
      <Card title="How one reading flows through the system" sub="Click a stage to see what it does, its live numbers, the code and how to verify it.">
        <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-3" role="tablist">
          {stages.map((x, i) => {
            const I = x.icon, on = x.id === sel;
            return (
              <button key={x.id} role="tab" aria-selected={on} onClick={() => setSel(x.id)}
                className="relative rounded-xl border px-3 py-3 text-left transition-all min-w-0"
                style={{ borderColor: on ? x.color : 'var(--border)', background: on ? `color-mix(in srgb, ${x.color} 12%, var(--surface))` : 'var(--surface)',
                  boxShadow: on ? `0 0 0 2px color-mix(in srgb, ${x.color} 35%, transparent)` : 'none' }}>
                <div className="flex items-center gap-2">
                  <span className="rounded-md p-1.5" style={{ background: `color-mix(in srgb, ${x.color} 16%, transparent)` }}><I size={15} style={{ color: x.color }} /></span>
                  <span className="text-[10px] font-bold rounded px-1.5 py-0.5" style={{ background: 'var(--chip)' }}>{x.ws}</span>
                  <span className="ml-auto text-[11px] tabular-nums" style={{ color: 'var(--muted)' }}>{i + 1}/{stages.length}</span>
                </div>
                <div className="text-sm font-semibold mt-2 leading-tight">{x.title}</div>
                <div className="text-[11px] mt-0.5 truncate" style={{ color: 'var(--muted)' }}>{x.owner}</div>
                {i < stages.length - 1 && <ArrowRight size={14} className="hidden xl:block absolute -right-[13px] top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--muted)' }} />}
              </button>);
          })}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-5">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: st.color }}>What it does · workstream {st.ws}</h3>
            <ul className="space-y-2 text-sm list-disc pl-4">{st.what.map(t => <li key={t}>{t}</li>)}</ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: st.color }}>Live from the API</h3>
            <table className="w-full text-sm"><tbody>{st.live.map(([k, v]) => (
              <tr key={k} className="border-b last:border-0 align-top" style={{ borderColor: 'var(--border)' }}>
                <td className="py-1.5 pr-3" style={{ color: 'var(--muted)' }}>{k}</td>
                <td className="py-1.5 font-medium tabular-nums text-right break-words">{v ?? '—'}</td></tr>))}</tbody></table>
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: st.color }}>Code &amp; how to verify</h3>
            <ul className="text-xs font-mono space-y-1">{st.files.map(f => <li key={f} className="flex gap-1.5"><GitBranch size={12} className="mt-0.5 shrink-0" />{f}</li>)}</ul>
            <pre className="mt-3 rounded-lg p-3 text-xs overflow-x-auto" style={{ background: 'var(--chip)' }}>{st.verify.join('\n')}</pre>
            {st.link && <Link to={st.link[0]} className="inline-flex items-center gap-1 mt-3 text-sm font-medium" style={{ color: 'var(--cloud)' }}>
              Open {st.link[1]} <ArrowRight size={14} /></Link>}
          </div>
        </div>
      </Card>

      {/* results */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2" title="Held-out test: LSTM vs baselines" sub={`${fmtCount(ev.test_windows)} windows, ${(ev.test_period_utc ?? []).map((t: string) => t.slice(0, 10)).join(' → ')} · lower is better`}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={modelRows} margin={{ left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="m" tick={{ fontSize: 12, fill: 'var(--text)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} unit=" ms" width={56} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v} ms`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="MAE" fill="var(--model)" isAnimationActive={false}>{modelRows.map(r => <Cell key={r.k} fill={r.k === 'lstm' ? 'var(--model)' : 'color-mix(in srgb, var(--model) 40%, var(--chip))'} />)}</Bar>
              <Bar dataKey="RMSE" fill="var(--cloud)" isAnimationActive={false}>{modelRows.map(r => <Cell key={r.k} fill={r.k === 'lstm' ? 'var(--cloud)' : 'color-mix(in srgb, var(--cloud) 35%, var(--chip))'} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>
            LSTM has the lowest MAE ({fmtNum(ov.lstm?.mae_ms)} ms, {((ov.lstm?.mae_skill_vs_persistence ?? 0) * 100).toFixed(0)} % better than persistence).
            EWMA and ridge reach a slightly lower RMSE ({fmtNum(ov.ewma?.rmse_ms)} ms); no method predicts the rare ≥ 300 ms spikes.
          </p>
        </Card>
        <Card title="AHP criterion weights" sub={`principal eigenvector · CR ${fmtNum(ahp.eigenvector?.cr_ri_0_58, 4)} (< 0.10 = consistent)`}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weightRows} layout="vertical" margin={{ left: 10 }}>
              <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
              <YAxis type="category" dataKey="k" width={78} tick={{ fontSize: 12, fill: 'var(--text)' }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="v" name="weight" fill="var(--edge)" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs" style={{ color: 'var(--muted)' }}>{ahp.note}</p>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Team and workstreams" sub="Each member's part also runs on its own from standalone_demos/">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th className="py-1 pr-3">WS</th><th className="pr-2">Workstream</th><th className="pr-2">Owner</th><th>Standalone demo</th></tr></thead>
            <tbody>{team.map(t => (
              <tr key={t.ws} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
                <td className="py-2 pr-3 font-bold">{t.ws}</td><td className="py-2 pr-2">{t.name}</td>
                <td className="py-2 pr-2" style={{ color: 'var(--muted)' }}>{t.who}</td><td className="py-2 font-mono text-xs">{t.demo}</td></tr>))}</tbody>
          </table>
        </Card>
        <Card title="What is real, what is simulated, what is not done" sub="Stated plainly so nobody over-claims in the review">
          <ul className="space-y-2 text-sm">
            {([
              [true, <>Network data: RIPE Atlas built-in measurements from Indian probes, {(q.time_range_utc ?? []).map((t: string) => t.slice(0, 10)).join(' → ')}.</>],
              [true, <>Vital signs for replay events: PhysioNet BIDMC (real ICU recordings, criticality via a partial NEWS2 score).</>],
              [true, <>Model metrics come from <code>results/model/metrics.json</code>, produced by the evaluation script on the untouched test split.</>],
              [null, <>Simulated events are synthetic and labelled <code>source=simulated</code>; the cloud cost index is synthetic everywhere.</>],
              [null, <>Edge node and cloud are local stand-ins unless S3 is configured; multi-cloud candidates in the demo are hypothetical.</>],
              [false, <>The 300 ms network veto never fires on the real replay data (no forecast reaches it); it is exercised by simulated degraded scenarios.</>],
              [false, <>AWS deployment is prepared (templates + staged guide) but not executed until the team runs it with their own account.</>],
              [false, <>Real alert delivery needs the team's Telegram / SMTP / SNS credentials; without them alerts are only mock-delivered.</>],
            ] as [boolean | null, ReactNode][]).map(([ok, t], i) => (
              <li key={i} className="flex gap-2 items-start">
                {ok === true ? <CheckCircle2 size={16} className="shrink-0 mt-0.5" style={{ color: 'var(--ok)' }} />
                  : ok === null ? <FlaskConical size={16} className="shrink-0 mt-0.5" style={{ color: 'var(--cloud)' }} />
                  : <CircleDashed size={16} className="shrink-0 mt-0.5" style={{ color: 'var(--veto)' }} />}<span>{t}</span></li>))}
          </ul>
        </Card>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {([['/events', 'Live events', Network], ['/trace', 'Request trace', GitBranch], ['/multi-cloud', 'Multi-cloud ranking', Cloud],
          ['/', 'Routing overview', Scale]] as [string, string, ElementType][]).map(([to, l, I]) => (
          <Link key={to} to={to} className="rounded-xl border p-4 flex items-center gap-3 hover:opacity-80" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
            <I size={18} style={{ color: 'var(--cloud)' }} /><span className="text-sm font-medium">{l}</span><ArrowRight size={14} className="ml-auto" style={{ color: 'var(--muted)' }} />
          </Link>))}
      </div>
    </div>
  );
}
