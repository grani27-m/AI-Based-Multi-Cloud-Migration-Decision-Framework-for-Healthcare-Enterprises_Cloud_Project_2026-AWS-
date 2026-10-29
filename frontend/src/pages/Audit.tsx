// src/pages/Audit.tsx — hash-chained audit log with on-demand verification.
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { api } from '../lib/api';
import { fmtTime } from '../lib/utils';
import { Btn, Card, Empty, ErrorState, Loading, Select } from '../components/ui';

export default function Audit() {
  const [action, setAction] = useState('');
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['audit', action, page], queryFn: () => api.audit(50, page * 50, action || undefined), refetchInterval: 10_000 });
  const v = useMutation({ mutationFn: api.verify });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div><h1 className="text-xl font-bold">Audit trail</h1>
          <p className="text-sm max-w-2xl" style={{ color: 'var(--muted)' }}>Append-only SHA-256 hash chain: each row stores the previous row's hash.
            Editing, deleting, inserting or reordering a row breaks verification. It is tamper-evident, not tamper-proof — export the head hash to a separate store.</p></div>
        <div className="ml-auto flex items-center gap-3">
          <Select label="Action" value={action} onChange={a => { setAction(a); setPage(0); }} options={[['', 'All'], ['event_received', 'event received'],
            ['event_processed', 'event processed'], ['event_failed', 'event failed'], ['alert_triggered', 'alert triggered'],
            ['alert_dispatched', 'alert dispatched'], ['login', 'login'], ['login_failed', 'login failed'], ['user_created', 'user created']]} />
          <Btn onClick={() => v.mutate()} disabled={v.isPending}>Verify chain</Btn>
        </div>
      </div>
      {v.error && <ErrorState error={v.error} />}
      {v.data && <Card>
        <div className="flex items-start gap-3">
          {v.data.valid ? <ShieldCheck size={28} style={{ color: 'var(--ok)' }} /> : <ShieldAlert size={28} style={{ color: 'var(--emergency)' }} />}
          <div className="text-sm">
            <div className="font-semibold" style={{ color: v.data.valid ? 'var(--ok)' : 'var(--emergency)' }}>
              {v.data.valid ? `Chain intact — ${v.data.checked.toLocaleString('en-IN')} entries verified` : `TAMPERING DETECTED at entry #${v.data.first_broken_id}: ${v.data.problem}`}</div>
            {v.data.head_hash && <div className="text-xs mt-1 font-mono break-all" style={{ color: 'var(--muted)' }}>head hash {v.data.head_hash}</div>}
            <div className="text-xs" style={{ color: 'var(--muted)' }}>verified {fmtTime(v.data.verified_at)} by {v.data.verified_by}</div>
          </div></div></Card>}
      <Card>
        {q.isLoading && <Loading />}
        {q.error && <ErrorState error={q.error} />}
        {q.data && q.data.items.length === 0 && <Empty title="No audit entries" />}
        {q.data && q.data.items.length > 0 && <div className="overflow-x-auto"><table className="w-full text-xs">
          <thead><tr className="text-left uppercase tracking-wide" style={{ color: 'var(--muted)' }}>
            {['#', 'Time', 'Actor', 'Action', 'Resource', 'Detail', 'Hash'].map(h => <th key={h} className="py-2 pr-3">{h}</th>)}</tr></thead>
          <tbody>{q.data.items.map(r => <tr key={r.id} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
            <td className="py-1.5 pr-3 tabular-nums">{r.id}</td><td className="pr-3 whitespace-nowrap">{fmtTime(r.ts)}</td>
            <td className="pr-3">{r.actor}</td><td className="pr-3 font-medium">{r.action}</td><td className="pr-3 font-mono">{r.resource}</td>
            <td className="pr-3 font-mono max-w-[340px] truncate" title={JSON.stringify(r.detail)}>{JSON.stringify(r.detail)}</td>
            <td className="font-mono" title={`prev ${r.prev_hash}`}>{r.hash.slice(0, 12)}…</td></tr>)}</tbody></table></div>}
        {q.data && <div className="flex items-center gap-2 mt-3 text-xs" style={{ color: 'var(--muted)' }}>
          <span>{q.data.total.toLocaleString('en-IN')} entries</span>
          <div className="ml-auto flex gap-2"><Btn kind="ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Newer</Btn>
            <Btn kind="ghost" disabled={(page + 1) * 50 >= q.data.total} onClick={() => setPage(p => p + 1)}>Older</Btn></div></div>}
      </Card>
    </div>
  );
}
