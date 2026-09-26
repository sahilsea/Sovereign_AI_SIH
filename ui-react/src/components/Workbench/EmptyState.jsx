import React from 'react';
import { Sparkles, FileText, Lock, Paperclip } from 'lucide-react';

// One-click demo questions, grouped by the tool that answers them. Each was
// run against the local models. Document examples are only offered when the
// user can read the document (the public RTI manual is always available);
// the access-control example is shown to everyone on purpose -- it answers
// for cleared users and shows "Access restricted" for everyone else.
const GROUPS = [
  {
    kind: 'Document',
    hint: 'searches the knowledge base, answers with verified quotes',
    tone: 'text-sov-green border-sov-green/30 bg-sov-green/10',
    items: [
      { q: 'What must personnel do during a toxic gas release at CDU-2?', doc: 'mrpl-hse-sop-101' },
      { q: 'Under which ministry does MRPL operate, according to the RTI manual?', doc: 'mrpl-rti-manual-sec4' },
    ],
  },
  {
    kind: 'Calculation',
    hint: 'exact calculator with steps; a model only translates words into the formula',
    tone: 'text-sov-orange border-sov-orange/30 bg-sov-orange/10',
    items: [
      { q: 'Add 2 with 2 and then divide it by 593' },
      { q: 'What is 15% of 2400?' },
      { q: 'Calculate the volumetric flow rate through a 150 mm diameter pipe at a velocity of 2 m/s' },
    ],
  },
  {
    kind: 'Coding',
    hint: 'code model writes Python, the sandbox runs it',
    tone: 'text-sky-400 border-sky-400/30 bg-sky-400/10',
    items: [
      { q: 'Write a python script to compute compound interest on 50000 at 8% for 5 years' },
      { q: 'Write a Python function that checks whether a number is prime and test it on 97 and 100' },
    ],
  },
  {
    kind: 'Access control',
    hint: 'answered only if you hold the vigilance compartment',
    tone: 'text-sov-red border-sov-red/30 bg-sov-red/10',
    items: [{ q: 'What did the Q2 2025 procurement audit find?' }],
  },
];

export default function EmptyState({ documents, onAsk, disabled }) {
  const readable = documents.filter((d) => d.readable);
  const locked = documents.length - readable.length;
  const readableIds = new Set(readable.map((d) => d.doc_id));
  const groups = GROUPS
    .map((g) => ({ ...g, items: g.items.filter((e) => !e.doc || readableIds.has(e.doc)) }))
    .filter((g) => g.items.length);

  return (
    <div className="py-8">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-2 tracking-tight">
          From Documents to <span className="text-sov-orange">Decisions</span>
        </h1>
        <p className="text-sov-text-secondary">
          Ask about your organisation's documents, run calculations, or attach a file. Everything runs on this machine.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="text-xs font-semibold text-sov-text-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <Sparkles size={13} /> Try asking
          </h2>
          <div className="space-y-4">
            {groups.map((g) => (
              <div key={g.kind}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${g.tone}`}>{g.kind}</span>
                  <span className="text-xs text-sov-text-muted">{g.hint}</span>
                </div>
                <div className="space-y-1.5">
                  {g.items.map((e) => (
                    <button
                      key={e.q}
                      onClick={() => onAsk(e.q)}
                      disabled={disabled}
                      className="w-full text-left text-sm px-4 py-2.5 rounded-lg bg-sov-card border border-sov-border hover:border-sov-orange/60 hover:text-sov-text-primary text-sov-text-secondary transition-colors disabled:opacity-50"
                    >
                      {e.q}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="flex items-start gap-2 text-xs text-sov-text-muted px-1 pt-1">
              <Paperclip size={13} className="mt-0.5 shrink-0" />
              <span>Or attach a scanned report, drawing, photo or spreadsheet with the paperclip and ask about it.</span>
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-xs font-semibold text-sov-text-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <FileText size={13} /> Documents you can access ({readable.length})
          </h2>
          <div className="bg-sov-card border border-sov-border rounded-lg divide-y divide-sov-border">
            {readable.length === 0 && (
              <div className="px-4 py-3 text-sm text-sov-text-muted">
                None yet. Ask your compartment sponsor for access.
              </div>
            )}
            {readable.map((d) => (
              <div key={d.doc_id} className="px-4 py-2.5 flex items-center justify-between gap-3">
                <span className="text-sm text-sov-text-primary truncate">{d.title}</span>
                <span className="text-[11px] text-sov-text-muted shrink-0 uppercase">{d.label?.tier}</span>
              </div>
            ))}
          </div>
          {locked > 0 && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-sov-text-muted px-1">
              <Lock size={12} /> {locked} more document(s) exist that you are not cleared to read.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
