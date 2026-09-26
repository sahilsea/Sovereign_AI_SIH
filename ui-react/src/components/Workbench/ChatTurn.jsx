import React, { useState } from 'react';
import { Loader2, Paperclip, Bot, ChevronDown, AlertCircle } from 'lucide-react';
import AnswerView from './AnswerView';
import StepTimeline, { buildSteps } from './StepTimeline';
import { progressMessage } from './activityText';

function TurnActivity({ events, running, startedAt }) {
  const [open, setOpen] = useState(false);
  const count = buildSteps(events).length;
  if (!count) return null;
  return (
    <div className="mt-3 pt-3 border-t border-sov-border-light">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-sm text-sov-text-muted hover:text-sov-text-primary flex items-center gap-1"
        aria-expanded={open}
      >
        <ChevronDown size={15} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        {open ? 'Hide activity' : `View activity (${count} step${count > 1 ? 's' : ''})`}
      </button>
      {open && (
        <div className="mt-3">
          <StepTimeline events={events} running={running} startedAt={startedAt} />
        </div>
      )}
    </div>
  );
}

export default function ChatTurn({ turn, docTitles }) {
  const running = !turn.result && !turn.error;
  return (
    <div className="space-y-3">
      {/* The user's message */}
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-sov-orange/10 border border-sov-orange/25 rounded-2xl rounded-br-sm px-4 py-2.5">
          <div className="text-sov-text-primary whitespace-pre-wrap break-words">{turn.question}</div>
          {(turn.fileName || turn.mode === 'agent') && (
            <div className="mt-1.5 flex flex-wrap gap-2 text-xs text-sov-text-muted">
              {turn.fileName && <span className="flex items-center gap-1"><Paperclip size={11} />{turn.fileName}</span>}
              {turn.mode === 'agent' && <span className="flex items-center gap-1"><Bot size={11} />Agent mode</span>}
            </div>
          )}
        </div>
      </div>

      {/* The assistant's reply */}
      <div className="bg-sov-card border border-sov-border rounded-2xl rounded-bl-sm px-5 py-4">
        {running && (
          <div className="flex items-center gap-2.5 text-sov-orange font-medium" role="status" aria-live="polite">
            <Loader2 className="animate-spin" size={18} />
            {progressMessage(turn.events)}
          </div>
        )}
        {turn.error && (
          <div className="flex items-start gap-2 text-sov-red text-sm">
            <AlertCircle size={16} className="mt-0.5 shrink-0" /> {turn.error}
          </div>
        )}
        {turn.result && <AnswerView result={turn.result} docTitles={docTitles} />}
        <TurnActivity events={turn.events} running={running} startedAt={turn.startedAt} />
      </div>
    </div>
  );
}
