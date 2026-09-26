import React from 'react';
import { Cpu, Server, Shield, ShieldAlert, CheckCircle, HelpCircle, XCircle, GitBranch } from 'lucide-react';
import { useModelStatus } from '../contexts/ModelContext';
import useNetworkStatus from '../hooks/useNetworkStatus';

const ROLE_LABELS = {
  primary: 'Documents',
  fallback: 'Fallback Drafting',
  code: 'Code',
  vision: 'Vision / OCR',
  planner: 'Agent Planner',
  embedding: 'Embeddings',
};

const TASK_LABELS = {
  document: 'Document Q&A, summaries, approval notes',
  planning: 'Multi-step agent: plan + tool calls',
  code: 'Code generation (run in sandbox)',
  vision: 'Images, scans, drawings, handwriting',
  embedding: 'Semantic search',
};

const ModelsPage = () => {
  const { models, modelsLoading, backend, selection, activeModelId, isProcessing } = useModelStatus();
  const { data: net } = useNetworkStatus(5000);
  const external = net?.monitor?.external_count;

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <Cpu className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Available Models</h1>
      </div>

      <div className="bg-sov-card border border-sov-border rounded-lg p-5 mb-8 flex flex-col md:flex-row gap-6 items-center">
        <div className="flex-1">
          <h2 className="text-lg font-semibold mb-2 flex items-center gap-2"><Server size={20} className="text-sov-text-secondary"/> Sovereign Infrastructure</h2>
          <p className="text-sov-text-secondary text-sm leading-relaxed">
            All models are deployed on-premise within the air-gapped environment. No data leaves the secure perimeter.
            Active backend: <span className="font-mono text-sov-orange bg-sov-orange/10 px-2 py-0.5 rounded ml-1">{backend || 'unknown'}</span>
          </p>
        </div>
        <div className="bg-sov-bg p-4 rounded-lg border border-sov-border flex items-center gap-3">
          {external ? <ShieldAlert className="text-sov-red" size={24} /> : <Shield className="text-sov-green" size={24} />}
          <div>
            <div className={`text-sm font-semibold ${external ? 'text-sov-red' : 'text-sov-green'}`}>
              {external === undefined ? 'Monitor loading…' : `${external} external connection(s)`}
            </div>
            <div className="text-xs text-sov-text-muted">Live, from the OS socket table</div>
          </div>
        </div>
      </div>

      <h3 className="text-lg font-semibold mb-3 text-sov-text-secondary flex items-center gap-2">
        <GitBranch size={18} /> Automatic Model Selection
      </h3>
      <div className="bg-sov-card border border-sov-border rounded-lg overflow-hidden mb-8">
        <table className="w-full text-left text-sm">
          <thead className="bg-sov-sidebar text-sov-text-secondary">
            <tr><th className="p-3">Task type</th><th className="p-3">Routed to</th><th className="p-3">Why</th></tr>
          </thead>
          <tbody>
            {Object.entries(selection).map(([task, sel]) => (
              <tr key={task} className="border-t border-sov-border">
                <td className="p-3">{TASK_LABELS[task] || task}</td>
                <td className="p-3 font-mono text-sov-orange">{sel.model}</td>
                <td className="p-3 text-xs text-sov-text-muted">{sel.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-3 py-2 text-xs text-sov-text-muted border-t border-sov-border">
          To add a model: <span className="font-mono">ollama pull &lt;id&gt;</span>, then add it to{' '}
          <span className="font-mono">config/models.json</span> with its task types and priority. No code change needed.
        </div>
      </div>

      <h3 className="text-lg font-semibold mb-4 text-sov-text-secondary">Model Registry</h3>

      {modelsLoading ? (
        <div className="text-sov-text-muted">Loading models...</div>
      ) : models.length === 0 ? (
        <div className="text-sov-text-muted">No models configured for this deployment.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {models.map(model => {
            const isActive = model.id === activeModelId;
            return (
              <div
                key={model.id}
                className={`p-5 rounded-lg border relative overflow-hidden group transition-colors ${
                  isActive ? 'border-sov-green bg-sov-card' : 'border-sov-border bg-sov-card'
                }`}
              >
                {isActive && (
                  <div className="absolute top-0 right-0 p-2 bg-sov-green text-black text-xs font-bold rounded-bl-lg flex items-center gap-1">
                    <span className="relative flex h-2 w-2">
                      {isProcessing && (
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-black opacity-60" />
                      )}
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-black" />
                    </span>
                    {isProcessing ? 'PROCESSING' : 'ACTIVE'}
                  </div>
                )}

                <div className="flex justify-between items-start mb-3 pr-16">
                  <h4 className="font-mono font-semibold text-lg break-all">{model.id}</h4>
                </div>

                <div className="flex flex-wrap gap-1.5 mb-3">
                  {model.roles.map((role) => (
                    <span key={role} className="px-2 py-1 text-xs rounded bg-sov-sidebar border border-sov-border text-sov-text-muted">
                      {ROLE_LABELS[role] || role}
                    </span>
                  ))}
                </div>

                <div className="flex items-center gap-2 text-sm mb-4">
                  {model.status === 'installed' ? (
                    <>
                      <CheckCircle className="text-sov-green" size={16} />
                      <span className="text-sov-green">Installed</span>
                    </>
                  ) : model.status === 'missing' ? (
                    <>
                      <XCircle className="text-sov-red" size={16} />
                      <span className="text-sov-red">Not pulled locally</span>
                    </>
                  ) : (
                    <>
                      <HelpCircle className="text-sov-text-muted" size={16} />
                      <span className="text-sov-text-muted">Status unknown</span>
                    </>
                  )}
                </div>

                <div className="pt-3 border-t border-sov-border flex justify-between items-center gap-2 text-xs text-sov-text-muted">
                  <span>{[model.family, model.params].filter(Boolean).join(' · ')}</span>
                  <span className="text-right">capable of: {(model.tasks || []).join(', ')}</span>
                </div>
                {model.note && <div className="mt-2 text-xs text-sov-text-muted italic">{model.note}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ModelsPage;
