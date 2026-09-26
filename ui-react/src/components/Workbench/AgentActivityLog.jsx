import React, { useEffect, useRef } from 'react';
import { Activity, Trash2, ChevronDown } from 'lucide-react';
import StepTimeline from './StepTimeline';

// Group the flat session log into runs: one "run" entry (the request)
// followed by that run's backend events.
function groupRuns(entries) {
  const runs = [];
  for (const entry of entries) {
    if (entry.type === 'run') {
      runs.push({ ...entry, events: [] });
    } else if (runs.length) {
      runs[runs.length - 1].events.push({ ...entry.event, _at: entry.at });
    }
  }
  return runs;
}

function outcomeText(events) {
  const final = events.find((e) => e.stage === 'final');
  if (final) return final.response?.status === 'answered' ? ['Done', 'text-sov-green'] : ['Withheld', 'text-sov-amber'];
  if (events.some((e) => e.stage === 'error')) return ['Failed', 'text-sov-red'];
  return null;
}

const clock = (ms) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export default function AgentActivityLog({ entries, isRunning, onClear }) {
  const bottomRef = useRef(null);
  const runs = groupRuns(entries);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [entries.length]);

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-sov-border-light flex items-center justify-between">
        <h3 className="text-base font-semibold text-sov-text-primary flex items-center gap-2">
          <Activity size={18} className="text-sov-orange" />
          Live Agent Activity
          {isRunning && (
            <span className="relative flex h-2 w-2 ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sov-green opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-sov-green" />
            </span>
          )}
        </h3>
        <button
          onClick={onClear}
          disabled={isRunning || entries.length === 0}
          className="text-sm text-sov-text-muted hover:text-sov-text-primary flex items-center gap-1 disabled:opacity-30"
        >
          <Trash2 size={14} /> Clear
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {runs.length === 0 && (
          <div className="h-full flex items-center justify-center text-center text-sov-text-muted text-sm px-6">
            No activity yet. Ask something in the chat to watch each step, the agent handling it and the model it uses, live.
          </div>
        )}

        {runs.map((run, index) => {
          const last = index === runs.length - 1;
          const runRunning = last && isRunning;
          const result = outcomeText(run.events);
          return (
            <details key={run.id} open={last} className="group bg-sov-sidebar border border-sov-border-light rounded-lg">
              <summary className="cursor-pointer list-none px-3 py-2.5 flex items-start gap-2">
                <ChevronDown size={16} className="mt-0.5 shrink-0 text-sov-text-muted transition-transform group-open:rotate-180" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-sov-text-primary break-words">{run.label}</div>
                  {run.detail && <div className="text-xs text-sov-text-muted break-words mt-0.5">{run.detail}</div>}
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-xs text-sov-text-muted font-mono">{clock(run.at)}</div>
                  {runRunning ? (
                    <div className="text-xs text-sov-orange">Running</div>
                  ) : result && <div className={`text-xs ${result[1]}`}>{result[0]}</div>}
                </div>
              </summary>
              <div className="px-4 pb-4 pt-1">
                <StepTimeline events={run.events} running={runRunning} startedAt={run.at} />
              </div>
            </details>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
