import React, { useEffect, useState, useCallback } from 'react';
import { Shield, Loader2, Check, X, Search } from 'lucide-react';
import { apiGet, apiPost, apiDelete } from '../../api/client';

/**
 * A sponsor's console: every active, non-admin employee and a Grant/Revoke
 * control for the ONE compartment this sponsor owns (GET /grants/people).
 * The backend re-checks every action -- this table can't grant anything the
 * sponsor doesn't personally sponsor.
 */
export default function SponsorAccessTable() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [filter, setFilter] = useState('');

  const load = useCallback(() => {
    apiGet('/grants/people').then(setData).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const act = async (personId, compartment, grant) => {
    setBusy(`${personId}:${compartment}`);
    setError(null);
    try {
      if (grant) await apiPost('/grants', { person_id: personId, compartment });
      else await apiDelete('/grants', { person_id: personId, compartment });
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  if (error && !data) return <div className="p-4 text-sov-red text-sm">{error}</div>;
  if (!data) return <div className="p-4 text-sov-text-muted text-sm">Loading employees…</div>;

  const q = filter.trim().toLowerCase();
  const people = data.people.filter((p) => !q || `${p.person_id} ${p.name} ${p.job_title}`.toLowerCase().includes(q));

  return (
    <div className="bg-sov-card border border-sov-border rounded-lg p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Shield size={20} className="text-sov-orange" /> Your compartment:{' '}
          {data.compartments.map((c) => (
            <span key={c} className="px-2 py-0.5 text-sm font-mono rounded border bg-purple-500/10 text-purple-400 border-purple-500">{c.toUpperCase()}</span>
          ))}
        </h2>
        <div className="flex items-center gap-2 bg-sov-bg border border-sov-border rounded px-2">
          <Search size={14} className="text-sov-text-muted" />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find employee"
                 className="bg-transparent py-1.5 text-sm outline-none w-44" />
        </div>
      </div>
      <p className="text-sm text-sov-text-secondary mb-4">
        You are the only person who can grant or revoke this compartment. Employees who need access come to you;
        administrators cannot do it for them.
      </p>
      {error && <div className="mb-3 p-2 rounded border border-sov-red/40 text-sov-red text-sm">{error}</div>}
      <div className="overflow-auto border border-sov-border rounded bg-sov-bg">
        <table className="w-full text-left text-sm">
          <thead className="bg-sov-sidebar text-sov-text-secondary">
            <tr><th className="p-3">Employee</th><th className="p-3">Grade</th><th className="p-3">Access</th><th className="p-3 text-right">Action</th></tr>
          </thead>
          <tbody>
            {people.flatMap((p) => data.compartments.map((c) => {
              const holds = p.holds[c];
              const working = busy === `${p.person_id}:${c}`;
              return (
                <tr key={`${p.person_id}-${c}`} className="border-t border-sov-border">
                  <td className="p-3">
                    <div className="font-medium">{p.name} <span className="font-mono text-xs text-sov-text-muted">{p.person_id}</span></div>
                    <div className="text-xs text-sov-text-muted">{p.job_title}</div>
                  </td>
                  <td className="p-3 font-mono">{p.grade}</td>
                  <td className="p-3">
                    {holds
                      ? <span className="inline-flex items-center gap-1 text-sov-green"><Check size={14} /> Granted</span>
                      : <span className="inline-flex items-center gap-1 text-sov-text-muted"><X size={14} /> No access</span>}
                  </td>
                  <td className="p-3 text-right">
                    <button
                      onClick={() => act(p.person_id, c, !holds)}
                      disabled={!!busy}
                      className={`px-3 py-1 rounded border text-xs font-semibold disabled:opacity-40 ${
                        holds ? 'border-sov-red text-sov-red hover:bg-sov-red/10' : 'border-sov-green text-sov-green hover:bg-sov-green/10'
                      }`}
                    >
                      {working ? <Loader2 size={13} className="animate-spin inline" /> : holds ? 'Revoke' : 'Grant'}
                    </button>
                  </td>
                </tr>
              );
            }))}
            {people.length === 0 && <tr><td colSpan="4" className="p-4 text-center text-sov-text-muted">No employees found.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Read-only: which single person sponsors each compartment. */
export function SeparationOfDuties() {
  const [comps, setComps] = useState([]);
  useEffect(() => { apiGet('/grants/compartments').then(setComps).catch(() => setComps([])); }, []);
  return (
    <div className="bg-sov-card border border-sov-border rounded-lg p-5 h-fit">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-2"><Shield size={20} /> Separation of duties</h2>
      <p className="text-sm text-sov-text-secondary mb-4">
        Administrators create accounts and reset passwords. They hold <strong>no compartment authority</strong>: only a
        compartment's sponsor can grant it, and sponsor accounts can't be created or reset from here.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {comps.map((c) => (
          <div key={c.id} className="bg-sov-bg border border-sov-border rounded p-3">
            <div className="text-xs font-mono uppercase text-purple-400">{c.id}</div>
            <div className="font-mono text-sm">{c.sponsor}</div>
            <div className="text-xs text-sov-text-muted">{c.description}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
