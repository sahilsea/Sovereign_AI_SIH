import React from 'react';
import {
  CheckCircle, HelpCircle, Lock, Terminal, Info, Download, Code, Shield, FileText,
  ListChecks, Wrench, XCircle, FolderOpen,
} from 'lucide-react';
import SourceCards from './SourceCards';

export function renderMarkdown(text) {
  if (!text) return { __html: '' };
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  let html = escaped
    .replace(/```(?:\w+)?\n?([\s\S]*?)```/g, '<pre class="bg-sov-sidebar p-4 rounded-lg my-4 overflow-x-auto border border-sov-border text-sm font-mono text-sov-text-primary">$1</pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-sov-border px-1.5 py-0.5 rounded text-sov-orange font-mono text-sm">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-sov-text-primary font-bold">$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em class="text-sov-text-primary italic">$1</em>')
    .replace(/^### (.*$)/gim, '<h3 class="text-base font-bold text-sov-text-primary mt-5 mb-2">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-lg font-bold text-sov-text-primary mt-6 mb-2">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold text-sov-orange mt-6 mb-3">$1</h1>')
    .replace(/^&gt; (.*$)/gim, '<blockquote class="border-l-4 border-sov-orange pl-4 py-1 my-4 text-sov-text-secondary">$1</blockquote>')
    .replace(/\n\n/g, '</p><p class="my-3">')
    .replace(/^[-•] (.*$)/gim, '<li class="ml-4 list-disc marker:text-sov-orange my-1">$1</li>');
  return { __html: `<p class="my-3">${html}</p>` };
}

// Deterministic outcome from the backend (contracts.py AskResponse.outcome).
export const OUTCOMES = {
  sourced: { label: 'Answer with sources', icon: CheckCircle, tone: 'text-sov-green', box: 'border-sov-green/30 bg-sov-green/5' },
  computed: { label: 'Result from executed code and tools', icon: Terminal, tone: 'text-sov-orange', box: 'border-sov-orange/30 bg-sov-orange/5' },
  general: { label: 'General answer — no document sources', icon: Info, tone: 'text-sov-text-secondary', box: 'border-sov-border bg-sov-sidebar' },
  unavailable: { label: 'Information unavailable', icon: HelpCircle, tone: 'text-sov-amber', box: 'border-sov-amber/30 bg-sov-amber/5' },
  restricted: { label: 'Access restricted', icon: Lock, tone: 'text-sov-red', box: 'border-sov-red/30 bg-sov-red/5' },
};

function outcomeOf(result) {
  if (result.outcome && OUTCOMES[result.outcome]) return result.outcome;
  if (result.status !== 'answered') return result.denials?.length ? 'restricted' : 'unavailable';
  return result.citations?.length ? 'sourced' : 'general';
}

function OutcomeBanner({ result }) {
  const key = outcomeOf(result);
  const o = OUTCOMES[key];
  const Icon = o.icon;
  const label = result.effective_label;
  return (
    <div className={`rounded-lg border px-4 py-3 ${o.box}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className={`flex items-center gap-2 font-semibold ${o.tone}`}>
          <Icon size={17} /> {o.label}
        </div>
        {label && key !== 'restricted' && key !== 'unavailable' && (
          <span className="flex items-center gap-1.5 text-xs text-sov-text-secondary">
            <Shield size={12} /> {label.tier?.toUpperCase()}
            {label.compartments?.length > 0 && ` · ${label.compartments.join(', ')}`}
          </span>
        )}
      </div>
      {result.verification_note && (
        <p className="text-xs text-sov-text-secondary mt-1.5 leading-relaxed">{result.verification_note}</p>
      )}
    </div>
  );
}

function Downloads({ result }) {
  if (result.status !== 'answered' || result.ledger_row_id == null) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {['DOCX', 'PPTX', 'XLSX'].map((format) => (
        <a
          key={format}
          href={`/report/${result.ledger_row_id}?format=${format.toLowerCase()}`}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-sov-text-secondary bg-sov-sidebar hover:bg-sov-border hover:text-sov-text-primary rounded border border-sov-border-light transition-colors"
        >
          <Download size={13} /> {format}
        </a>
      ))}
    </div>
  );
}

function AgentWork({ result }) {
  if (!(result.plan?.length || result.agent_trace?.length)) return null;
  return (
    <details className="bg-sov-sidebar rounded-lg border border-sov-border-light">
      <summary className="cursor-pointer px-4 py-2.5 text-sm text-sov-text-primary flex items-center gap-2">
        <ListChecks size={15} className="text-sov-orange" />
        How the agent did it: {result.plan?.length || 0}-step plan, {result.agent_trace?.length || 0} tool call(s)
      </summary>
      <div className="px-4 pb-4 space-y-4">
        {result.plan?.length > 0 && (
          <ol className="text-sm text-sov-text-secondary space-y-1">
            {result.plan.map((stepText, i) => <li key={i}>{stepText}</li>)}
          </ol>
        )}
        <div className="space-y-2">
          {result.agent_trace?.map((s) => (
            <details key={s.step} className="bg-sov-card border border-sov-border rounded">
              <summary className="cursor-pointer px-3 py-2 text-sm flex items-center gap-2">
                {s.ok ? <CheckCircle size={14} className="text-sov-green shrink-0" /> : <XCircle size={14} className="text-sov-red shrink-0" />}
                <Wrench size={12} className="text-sov-text-muted shrink-0" />
                <span className="font-mono text-sov-orange">{s.step}. {s.tool}</span>
                <span className="text-sov-text-muted truncate">{s.thought}</span>
                <span className="ml-auto text-xs text-sov-text-muted font-mono">{s.duration_seconds}s</span>
              </summary>
              <div className="px-3 pb-3 text-xs font-mono space-y-2">
                <div>
                  <div className="text-sov-text-muted mb-1">args</div>
                  <pre className="whitespace-pre-wrap break-words text-sov-text-secondary">{JSON.stringify(s.args, null, 2)}</pre>
                </div>
                <div>
                  <div className="text-sov-text-muted mb-1">result (from the tool, not the model)</div>
                  <pre className="whitespace-pre-wrap break-words text-sov-text-secondary">{s.observation}</pre>
                </div>
              </div>
            </details>
          ))}
        </div>
      </div>
    </details>
  );
}

function Deliverables({ result }) {
  if (!result.artifacts?.length) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-sov-text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <FolderOpen size={13} /> Files created
      </h4>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {result.artifacts.map((f) => (
          <a
            key={f.name}
            href={`/workspace/files/${encodeURIComponent(f.name)}`}
            className="flex items-center gap-3 bg-sov-sidebar border border-sov-border-light hover:border-sov-orange/50 rounded-lg px-3 py-2 transition-colors"
          >
            <Download size={15} className="text-sov-orange shrink-0" />
            <div className="min-w-0">
              <div className="text-sm text-sov-text-primary font-mono truncate">{f.name}</div>
              <div className="text-xs text-sov-text-muted">
                {(f.size_bytes / 1024).toFixed(1)} KB · {f.label?.tier?.toUpperCase()}
                {f.label?.compartments?.length ? ` · ${f.label.compartments.join(', ')}` : ''}
              </div>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

function ApprovalNoteCard({ result }) {
  const note = result.approval_note;
  if (!note) return null;
  return (
    <div className="bg-sov-sidebar rounded-lg p-4 border border-sov-border-light">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="font-semibold text-sov-text-primary flex items-center gap-2">
          <FileText size={16} className="text-sov-orange" /> {note.title || 'Approval Note'}
        </h3>
        {result.ledger_row_id != null && (
          <a
            href={`/report/${result.ledger_row_id}/approval-note`}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-sov-orange hover:bg-sov-border rounded border border-sov-orange/40 transition-colors shrink-0"
          >
            <Download size={13} /> Approval Note (DOCX)
          </a>
        )}
      </div>
      <div className="text-xs text-sov-text-muted">
        {note.verified_findings?.length || 0} verified finding(s) · {note.visual_observations?.length || 0} visual observation(s), not verified
      </div>
    </div>
  );
}

function CodeRun({ result }) {
  const run = result.code_execution;
  if (!run) return null;
  return (
    <div className="bg-black rounded-lg overflow-hidden border border-sov-border-light">
      <div className="bg-sov-sidebar px-4 py-2 border-b border-sov-border-light flex justify-between items-center text-sm">
        <div className="flex items-center gap-2 text-sov-text-primary">
          <Code size={15} className="text-sov-orange" /> Ran in the sandbox
        </div>
        <div className="text-sov-text-muted font-mono text-xs">
          {Math.round((run.duration_seconds || 0) * 1000)}ms · exit {run.exit_code}{run.timed_out && ' · timed out'}
        </div>
      </div>
      <div className="p-4 font-mono text-sm overflow-x-auto text-sov-text-secondary">
        {!result.answer?.includes('```') && <pre>{result.code}</pre>}
        {run.stdout && <pre className="text-sov-green whitespace-pre-wrap">{run.stdout}</pre>}
        {run.stderr && <pre className="mt-2 text-sov-red whitespace-pre-wrap">{run.stderr}</pre>}
      </div>
    </div>
  );
}

function Restricted({ result, docTitles }) {
  if (!result.denials?.length) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-sov-red uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <Lock size={12} /> Withheld from you ({result.denials.length})
      </h4>
      <ul className="space-y-1">
        {result.denials.map((d) => (
          <li key={d.doc_id} className="text-xs text-sov-text-secondary">
            <span className="text-sov-text-primary">{docTitles[d.doc_id] || d.doc_id}</span> — {d.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AnswerView({ result, docTitles }) {
  const withheld = result.status !== 'answered';
  return (
    <div className="space-y-4">
      <OutcomeBanner result={result} />
      {!(withheld && result.outcome === 'restricted') && (
        <div className="text-sov-text-secondary leading-relaxed" dangerouslySetInnerHTML={renderMarkdown(result.answer || '')} />
      )}
      <CodeRun result={result} />
      <ApprovalNoteCard result={result} />
      <Deliverables result={result} />
      <SourceCards citations={result.citations} docTitles={docTitles} />
      <AgentWork result={result} />
      <Restricted result={result} docTitles={docTitles} />
      <Downloads result={result} />
    </div>
  );
}
