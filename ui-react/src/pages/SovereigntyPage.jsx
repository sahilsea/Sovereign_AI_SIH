import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api/client';
import { ShieldCheck, ShieldAlert, Activity, Database, Radio, Ban, Server } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import useNetworkStatus from '../hooks/useNetworkStatus';

const Stat = ({ label, value, tone = 'text-sov-text-primary' }) => (
  <div className="bg-sov-bg rounded border border-sov-border p-3">
    <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
    <div className="text-xs text-sov-text-muted mt-0.5">{label}</div>
  </div>
);

/**
 * Live egress evidence (GET /sovereignty/network, trust/egress.py): what
 * the OS says the SEVERANCE and Ollama processes are connected to, plus
 * what the in-process guard blocked. Polled every 2s -- nothing here is a
 * static claim.
 */
function NetworkMonitorPanel({ isAdmin }) {
  const { data, error } = useNetworkStatus(2000);
  const [facts, setFacts] = useState(null);
  const [probe, setProbe] = useState(null);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    apiGet('/sovereignty/facts').then(setFacts).catch(() => setFacts(null));
  }, []);

  const runProbe = async () => {
    setProbing(true);
    try {
      setProbe(await apiPost('/sovereignty/network/probe', {}));
    } catch (err) {
      setProbe({ blocked: false, detail: err.message });
    } finally {
      setProbing(false);
    }
  };

  if (error) {
    return <div className="mb-8 p-4 rounded-lg border border-sov-red/40 text-sov-red text-sm">Network monitor unavailable: {error}</div>;
  }
  if (!data) {
    return <div className="mb-8 p-4 text-sov-text-muted text-sm">Loading live network monitor…</div>;
  }

  const { guard, monitor } = data;
  const clean = monitor.external_count === 0;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
      <div className={`lg:col-span-2 bg-sov-card border rounded-lg p-5 ${clean ? 'border-sov-green/30' : 'border-sov-red/60'}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Activity className={clean ? 'text-sov-green' : 'text-sov-red'} /> Live Network Monitor
          </h2>
          <span className="flex items-center gap-1.5 text-xs text-sov-green">
            <Radio size={12} className="animate-pulse" />
            last OS check {monitor.last_check ? new Date(monitor.last_check).toLocaleTimeString() : '—'}
          </span>
        </div>

        <div className={`rounded border p-4 mb-4 flex items-center gap-3 ${clean ? 'border-sov-green/30 bg-sov-green/5' : 'border-sov-red/40 bg-sov-red/5'}`}>
          {clean ? <ShieldCheck className="text-sov-green shrink-0" size={28} /> : <ShieldAlert className="text-sov-red shrink-0" size={28} />}
          <div>
            <div className={`font-bold ${clean ? 'text-sov-green' : 'text-sov-red'}`}>
              {clean
                ? `No external connections in ${monitor.checks.toLocaleString()} OS checks`
                : `${monitor.external_count} external connection(s) observed`}
            </div>
            <div className="text-xs text-sov-text-secondary mt-0.5">
              Watching {monitor.watched_processes.map((p) => `${p.name} (${p.pid})`).join(', ') || 'no processes'} since{' '}
              {monitor.started_at ? new Date(monitor.started_at).toLocaleTimeString() : '—'}.
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <Stat label="external connections" value={monitor.external_count} tone={clean ? 'text-sov-green' : 'text-sov-red'} />
          <Stat label="blocked by guard" value={guard.blocked_count} tone={guard.blocked_count ? 'text-sov-amber' : 'text-sov-text-primary'} />
          <Stat label="local connections allowed" value={guard.allowed_local_connections.toLocaleString()} />
          <Stat label="guard mode" value={guard.mode.toUpperCase()} tone={guard.mode === 'block' ? 'text-sov-green' : 'text-sov-amber'} />
        </div>

        <h3 className="text-sm font-semibold text-sov-text-secondary mb-2">Observed connections (from the OS socket table)</h3>
        <div className="border border-sov-border rounded overflow-auto max-h-56">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-sov-sidebar text-sov-text-secondary sticky top-0">
              <tr><th className="p-2">Process</th><th className="p-2">Remote</th><th className="p-2">Scope</th><th className="p-2">Seen</th></tr>
            </thead>
            <tbody>
              {monitor.external_connections.map((c, i) => (
                <tr key={`x${i}`} className="border-t border-sov-border text-sov-red">
                  <td className="p-2">{c.process} ({c.pid})</td><td className="p-2">{c.remote_ip}:{c.remote_port}</td>
                  <td className="p-2 font-bold">EXTERNAL</td><td className="p-2">{new Date(c.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))}
              {monitor.local_endpoints.map((e, i) => (
                <tr key={`l${i}`} className="border-t border-sov-border">
                  <td className="p-2">{e.process}</td>
                  <td className="p-2">{e.remote_ip}:{e.remote_port ?? 'client'}</td>
                  <td className="p-2 text-sov-green">local{e.remote_port === 11434 ? ' · Ollama' : ''}</td>
                  <td className="p-2 text-sov-text-muted">{e.observations}×</td>
                </tr>
              ))}
              {monitor.external_connections.length === 0 && monitor.local_endpoints.length === 0 && (
                <tr><td colSpan="4" className="p-3 text-center text-sov-text-muted font-sans">No connections observed yet — run a query to see local model traffic appear here.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {guard.blocked_attempts.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-sov-amber mb-2 flex items-center gap-1.5"><Ban size={14} /> Blocked outbound attempts</h3>
            <ul className="text-xs font-mono space-y-1">
              {guard.blocked_attempts.slice().reverse().map((b, i) => (
                <li key={i} className="text-sov-text-secondary">
                  {new Date(b.timestamp).toLocaleTimeString()} — {b.remote_ip}:{b.remote_port} ({b.action})
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="bg-sov-card border border-sov-border rounded-lg p-5 flex flex-col gap-4">
        <h2 className="text-lg font-semibold flex items-center gap-2"><Database className="text-sov-orange" /> Data Residency</h2>
        {facts ? (
          <dl className="text-xs space-y-2">
            {[
              ['Model server', facts.ollama_api_base],
              ['Database', facts.database],
              ['Corpus', facts.corpus_dir],
              ['Agent workspace', facts.workspace_dir],
              ['Code sandbox', data.sandbox_mode],
              ['At-rest encryption', facts.at_rest_encryption],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-sov-text-muted">{k}</dt>
                <dd className="font-mono text-sov-text-secondary break-all">{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <div className="text-sm text-sov-text-muted">Loading…</div>
        )}

        {isAdmin && (
          <div className="border-t border-sov-border pt-4 mt-auto">
            <div className="text-sm font-semibold mb-1 flex items-center gap-2"><Server size={14} /> Test the egress guard</div>
            <p className="text-xs text-sov-text-muted mb-3">
              Tries to open a connection to a public address (1.1.1.1:443). The guard should refuse it before any packet is sent.
            </p>
            <button
              onClick={runProbe}
              disabled={probing || guard.mode !== 'block'}
              className="px-3 py-1.5 bg-sov-orange text-black text-sm font-semibold rounded hover:bg-sov-orange-dark disabled:opacity-50"
            >
              {probing ? 'Testing…' : 'Attempt external connection'}
            </button>
            {probe && (
              <div className={`mt-3 text-xs p-2 rounded border ${probe.blocked ? 'border-sov-green/40 text-sov-green' : 'border-sov-red/40 text-sov-red'}`}>
                {probe.blocked ? 'BLOCKED — ' : 'NOT BLOCKED — '}{probe.detail}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const SovereigntyPage = () => {
  const { principal } = useAuth();
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    const fetchLedger = async () => {
      try {
        setLoading(true);
        const data = await apiGet('/ledger?limit=50');
        setLedger(data || []);
      } catch (err) {
        setError(err.message || 'Failed to fetch ledger');
      } finally {
        setLoading(false);
      }
    };
    fetchLedger();
  }, []);

  const handleVerify = async () => {
    try {
      setVerifying(true);
      const res = await apiGet('/ledger/verify');
      setVerifyResult(res);
    } catch (err) {
      setVerifyResult({ error: err.message });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <ShieldCheck className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Sovereignty & Trust</h1>
      </div>

      <NetworkMonitorPanel isAdmin={!!principal?.is_admin} />

      <div className="bg-sov-card border border-sov-border rounded-lg p-5 flex-1 flex flex-col min-h-0">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Audit Ledger</h2>
          <div className="flex items-center gap-3">
            {verifyResult && !verifyResult.error && (
              <span className={`px-3 py-1 rounded text-xs font-bold ${verifyResult.intact ? 'bg-sov-green/20 text-sov-green' : 'bg-sov-red/20 text-sov-red'}`}>
                {verifyResult.intact ? 'CHAIN INTACT' : `BROKEN AT ROW ${verifyResult.broken_at_row_id}`}
              </span>
            )}
            <button 
              onClick={handleVerify} 
              disabled={verifying}
              className="px-4 py-2 bg-sov-orange text-black font-semibold rounded hover:bg-sov-orange-dark disabled:opacity-50 transition-colors text-sm"
            >
              {verifying ? 'Verifying...' : 'Verify Chain'}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-sov-text-muted">Loading ledger...</div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-sov-red">{error}</div>
        ) : (
          <div className="overflow-auto border border-sov-border rounded bg-sov-bg flex-1">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-sov-sidebar border-b border-sov-border text-sm text-sov-text-secondary sticky top-0">
                  <th className="p-3">ID</th>
                  <th className="p-3">Timestamp</th>
                  <th className="p-3">Actor</th>
                  <th className="p-3">Action</th>
                  <th className="p-3">Hash</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((row) => (
                  <tr key={row.row_id} className="border-b border-sov-border hover:bg-sov-card-hover text-xs font-mono">
                    <td className="p-3 text-sov-text-muted">{row.row_id}</td>
                    <td className="p-3">{new Date(row.timestamp).toLocaleString()}</td>
                    <td className="p-3 text-sov-amber">{row.actor}</td>
                    <td className="p-3 font-semibold">{row.action}</td>
                    <td className="p-3 text-sov-text-muted truncate max-w-[150px]" title={row.hash}>{row.hash?.substring(0, 16)}...</td>
                  </tr>
                ))}
                {ledger.length === 0 && (
                  <tr><td colSpan="5" className="p-4 text-center text-sov-text-muted">No audit logs found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default SovereigntyPage;
