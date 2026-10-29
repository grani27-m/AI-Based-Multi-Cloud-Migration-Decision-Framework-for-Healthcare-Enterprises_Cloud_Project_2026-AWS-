// src/pages/Admin.tsx — demo runner (real replay / labelled simulation through the real pipeline) and user management.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Role } from '../lib/api';
import { fmtTime } from '../lib/utils';
import { Btn, Card, ErrorState, Loading, Select } from '../components/ui';

export default function Admin() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<'replay' | 'simulate'>('replay');
  const [scenario, setScenario] = useState('mixed');
  const [count, setCount] = useState(40);
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 100000));
  const run = useMutation({ mutationFn: () => api.demo({ mode, count, scenario, seed }),
    onSuccess: () => { qc.invalidateQueries(); setSeed(s => s + 1); } });
  const users = useQuery({ queryKey: ['users'], queryFn: api.users });
  const [nu, setNu] = useState({ username: '', full_name: '', password: '', role: 'doctor' as Role });
  const create = useMutation({ mutationFn: () => api.createUser(nu), onSuccess: () => { setNu({ ...nu, username: '', password: '' }); users.refetch(); } });
  const toggle = useMutation({ mutationFn: ({ id, a }: { id: number; a: boolean }) => api.setActive(id, a), onSuccess: () => users.refetch() });
  const input = 'rounded-md border px-2 py-1.5 text-sm w-full';
  const inStyle = { background: 'var(--page)', borderColor: 'var(--border)', color: 'var(--text)' };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Admin</h1>
      <Card title="Demo runner" sub="Pushes events through the real prediction → decision → execution pipeline and stores them.">
        <div className="flex flex-wrap items-end gap-4">
          <Select label="Mode" value={mode} onChange={v => setMode(v as 'replay' | 'simulate')}
            options={[['replay', 'Replay — real RIPE Atlas test period + real BIDMC vitals'], ['simulate', 'Simulate — synthetic scenarios']]} />
          {mode === 'simulate' && <Select label="Scenario" value={scenario} onChange={setScenario}
            options={[['mixed', 'Mixed'], ['normal', 'Normal'], ['degraded', 'Degraded network'], ['emergency', 'Emergency vitals'], ['failure', 'Cloud failure']]} />}
          <label className="text-xs" style={{ color: 'var(--muted)' }}>Events
            <input type="number" min={1} max={500} value={count} onChange={e => setCount(Number(e.target.value))} className={input} style={{ ...inStyle, width: 90 }} /></label>
          <label className="text-xs" style={{ color: 'var(--muted)' }}>Seed
            <input type="number" value={seed} onChange={e => setSeed(Number(e.target.value))} className={input} style={{ ...inStyle, width: 110 }} /></label>
          <Btn onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? 'Running…' : 'Run'}</Btn>
        </div>
        <p className="text-xs mt-3" style={{ color: 'var(--muted)' }}>Replay pairs a held-out RIPE Atlas network window with an unrelated BIDMC ICU second; the pairing and
          the synthetic cost index are stated in each event's provenance. Re-using a seed re-sends the same event IDs, which the API detects as duplicates.</p>
        {run.error && <div className="mt-3"><ErrorState error={run.error} /></div>}
        {run.data && <div className="mt-3 text-sm rounded-lg border p-3" style={{ borderColor: 'var(--border)' }}>
          Processed <b>{run.data.processed}</b> · duplicates {run.data.duplicates} · failed {run.data.failed} ·
          {' '}{Object.entries(run.data.by_destination).map(([k, v]) => `${k} ${v}`).join(' · ')} ·
          {' '}{Object.entries(run.data.by_reason).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}</div>}
      </Card>

      <Card title="Users" sub="Passwords are PBKDF2-hashed server-side; roles are enforced on every endpoint.">
        {users.isLoading && <Loading />}
        {users.error && <ErrorState error={users.error} />}
        {users.data && <div className="overflow-x-auto"><table className="w-full text-sm mb-4">
          <thead><tr className="text-left text-xs" style={{ color: 'var(--muted)' }}><th className="py-1">Username</th><th>Name</th><th>Role</th><th>Last login</th><th>Status</th><th></th></tr></thead>
          <tbody>{users.data.map(u => <tr key={u.id} className="border-t" style={{ borderColor: 'var(--border)' }}>
            <td className="py-1.5 font-mono">{u.username}</td><td>{u.full_name}</td><td className="capitalize">{u.role}</td>
            <td className="text-xs">{fmtTime(u.last_login_at)}</td>
            <td style={{ color: u.is_active ? 'var(--ok)' : 'var(--emergency)' }}>{u.is_active ? 'active' : 'disabled'}</td>
            <td className="text-right"><Btn kind={u.is_active ? 'danger' : 'ghost'} onClick={() => toggle.mutate({ id: u.id, a: !u.is_active })}>
              {u.is_active ? 'Disable' : 'Enable'}</Btn></td></tr>)}</tbody></table></div>}
        {toggle.error && <ErrorState error={toggle.error} />}
        <form className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end" onSubmit={e => { e.preventDefault(); create.mutate(); }}>
          <input placeholder="username" value={nu.username} onChange={e => setNu({ ...nu, username: e.target.value })} className={input} style={inStyle} />
          <input placeholder="full name" value={nu.full_name} onChange={e => setNu({ ...nu, full_name: e.target.value })} className={input} style={inStyle} />
          <input placeholder="password (≥10 chars)" type="password" value={nu.password} onChange={e => setNu({ ...nu, password: e.target.value })} className={input} style={inStyle} />
          <select value={nu.role} onChange={e => setNu({ ...nu, role: e.target.value as Role })} className={input} style={inStyle}>
            {['admin', 'doctor', 'auditor', 'device'].map(r => <option key={r}>{r}</option>)}</select>
          <Btn type="submit" disabled={create.isPending}>Create user</Btn>
        </form>
        {create.error && <div className="mt-2"><ErrorState error={create.error} /></div>}
      </Card>
    </div>
  );
}
