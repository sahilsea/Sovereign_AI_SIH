import React from 'react';
import { Server, Database, Globe } from 'lucide-react';
import { useModelStatus } from '../../contexts/ModelContext';

/** Real status only: Ollama reachability comes from GET /models, document
 * counts from GET /documents, and the API is up if this page loaded data. */
export default function SystemStatus({ documents = [] }) {
  const { ollamaReachable, models } = useModelStatus();
  const readable = documents.filter((d) => d.readable).length;
  const installed = models.filter((m) => m.status === 'installed').length;

  const rows = [
    {
      icon: Server, title: 'Local model server',
      ok: ollamaReachable === true,
      status: ollamaReachable === null ? 'Checking…' : ollamaReachable ? 'Reachable' : 'Unreachable',
      detail: `${installed} registry model(s) installed`,
    },
    { icon: Database, title: 'Knowledge base', ok: documents.length > 0, status: `${documents.length} documents`, detail: `${readable} readable by you` },
    { icon: Globe, title: 'API server', ok: true, status: 'Responding', detail: window.location.host },
  ];

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl p-5">
      <h3 className="text-lg font-semibold text-sov-text-primary mb-4">System Status</h3>
      <div className="space-y-3">
        {rows.map(({ icon: Icon, title, ok, status, detail }) => (
          <div key={title} className="flex items-start gap-3">
            <div className="p-2 bg-sov-sidebar rounded text-sov-text-secondary"><Icon size={18} /></div>
            <div>
              <div className="text-base font-medium text-sov-text-primary">{title}</div>
              <div className="text-sm flex flex-wrap gap-x-2 mt-0.5">
                <span className={ok ? 'text-sov-green' : 'text-sov-amber'}>{status}</span>
                <span className="text-sov-text-muted">·</span>
                <span className="text-sov-text-secondary">{detail}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
