import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, ShieldAlert, Radio } from 'lucide-react';
import useNetworkStatus from '../../hooks/useNetworkStatus';

/**
 * Live, compact egress evidence for the Workbench sidebar -- polls
 * GET /sovereignty/network (trust/egress.py). Every number here comes from
 * the OS socket table or the in-process guard, never from a hardcoded claim.
 */
export default function EgressStatus() {
  const { data, error } = useNetworkStatus(2000);

  if (error) {
    return (
      <div className="bg-sov-card border border-sov-border rounded-xl p-5 text-base text-sov-text-muted">
        Network monitor unavailable: {error}
      </div>
    );
  }
  if (!data) {
    return <div className="bg-sov-card border border-sov-border rounded-xl p-5 text-base text-sov-text-muted">Loading network monitor…</div>;
  }

  const external = data.monitor.external_count;
  const blocked = data.guard.blocked_count;
  const clean = external === 0;
  const ollamaLinks = data.monitor.local_endpoints.filter((e) => e.remote_port === 11434).length;

  return (
    <div className={`bg-sov-card border rounded-xl p-5 ${clean ? 'border-sov-green/30' : 'border-sov-red/50'}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-sov-text-primary flex items-center gap-2">
          {clean ? <ShieldCheck className="text-sov-green" size={18} /> : <ShieldAlert className="text-sov-red" size={18} />}
          Network egress
        </h3>
        <span className="flex items-center gap-1 text-xs uppercase tracking-wider text-sov-green">
          <Radio size={11} className="animate-pulse" /> live
        </span>
      </div>
      <div className="flex items-baseline gap-2 mb-1">
        <span className={`text-3xl font-bold tabular-nums ${clean ? 'text-sov-green' : 'text-sov-red'}`}>{external}</span>
        <span className="text-base text-sov-text-secondary">external connections</span>
      </div>
      <div className="text-sm text-sov-text-muted space-y-1 mb-3">
        <div>{data.monitor.checks.toLocaleString()} OS socket-table checks</div>
        <div>Guard: <span className="text-sov-text-secondary font-medium uppercase">{data.guard.mode}</span> · {blocked} blocked attempt(s)</div>
        <div>{ollamaLinks ? 'Local model traffic seen on :11434' : 'No model traffic yet'}</div>
      </div>
      <Link to="/sovereignty" className="text-base text-sov-orange hover:text-sov-orange-dark font-medium">
        Full network monitor →
      </Link>
    </div>
  );
}
