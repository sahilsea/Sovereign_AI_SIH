import React, { useState } from 'react';
import { FileText, ChevronDown, ExternalLink, CheckCircle } from 'lucide-react';

/**
 * Compact, inspectable source cards. Each card: document title, page, the
 * verified quotation (expand to read), and -- for corpus documents -- a link
 * that opens the PDF at that page (GET /documents/{id}/file, clearance
 * re-checked server-side). Uploaded files ("upload:...") have no page link.
 */
function SourceCard({ citation, title }) {
  // Expanded by default: the verified quote is the evidence, so show it.
  const [open, setOpen] = useState(true);
  const isUpload = citation.doc_id.startsWith('upload:');
  const displayTitle = isUpload ? citation.doc_id.slice('upload:'.length) : title || citation.doc_id;
  const href = isUpload ? null : `/documents/${encodeURIComponent(citation.doc_id)}/file#page=${citation.page}`;

  return (
    <div className="bg-sov-sidebar border border-sov-border-light rounded-lg">
      <div className="flex items-center gap-2 px-3 py-2">
        <FileText size={15} className="text-sov-orange shrink-0" />
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex-1 min-w-0 text-left flex items-center gap-2"
          aria-expanded={open}
        >
          <span className="text-sm text-sov-text-primary truncate">{displayTitle}</span>
          <span className="text-xs text-sov-text-muted shrink-0">p. {citation.page}</span>
          <ChevronDown size={14} className={`text-sov-text-muted shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        {href && (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs text-sov-orange hover:text-sov-orange-dark shrink-0"
            title="Open this page of the source document"
          >
            Open page <ExternalLink size={12} />
          </a>
        )}
      </div>
      {open && (
        <div className="px-3 pb-3">
          <blockquote className="text-sm text-sov-text-secondary italic border-l-2 border-sov-green/50 pl-3">
            “{citation.quote}”
          </blockquote>
          <div className="mt-1.5 flex items-center gap-1 text-[11px] text-sov-green">
            <CheckCircle size={11} /> Matched word-for-word on this page
          </div>
        </div>
      )}
    </div>
  );
}

export default function SourceCards({ citations, docTitles }) {
  if (!citations?.length) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-sov-text-muted uppercase tracking-wider mb-2">
        Sources ({citations.length})
      </h4>
      <div className="grid grid-cols-1 gap-2">
        {citations.map((c, i) => (
          <SourceCard key={`${c.doc_id}-${c.page}-${i}`} citation={c} title={docTitles[c.doc_id]} />
        ))}
      </div>
    </div>
  );
}
