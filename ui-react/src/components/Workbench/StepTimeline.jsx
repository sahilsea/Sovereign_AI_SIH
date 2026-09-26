import React, { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Loader2, Circle, Cpu } from 'lucide-react';
import { STAGES, buildSteps } from './activityText';

export { buildSteps };

const ICON = {
  running: <Loader2 size={18} className="text-sov-orange animate-spin" />,
  ok: <CheckCircle2 size={18} className="text-sov-green" />,
  fail: <XCircle size={18} className="text-sov-red" />,
  info: <Circle size={18} className="text-sov-text-muted" />,
};
const TEXT_TONE = { running: 'text-sov-orange', ok: 'text-sov-text-secondary', fail: 'text-sov-red', info: 'text-sov-text-secondary' };

const seconds = (ms) => (ms / 1000).toFixed(1);

export default function StepTimeline({ events, running, startedAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [running]);

  const steps = buildSteps(events);
  if (!steps.length) {
    return <div className="text-sm text-sov-text-muted px-1 py-2">{running ? 'Waiting for the first step…' : 'No steps recorded.'}</div>;
  }
  const t0 = startedAt ?? steps[0].startAt;

  return (
    <ol className="relative">
      {steps.map((s, i) => {
        const meta = STAGES[s.stage] || { agent: s.stage };
        const isRunning = s.tone === 'running' && running;
        const tone = s.tone === 'running' && !running ? 'info' : s.tone;
        const took = s.endAt != null ? s.endAt - s.startAt : isRunning ? now - s.startAt : null;
        return (
          <li key={`${s.key}-${i}`} className="relative flex gap-3 pb-4 last:pb-0">
            {i < steps.length - 1 && <span className="absolute left-[8.5px] top-6 bottom-0 w-px bg-sov-border" aria-hidden />}
            <span className="relative z-10 mt-0.5 shrink-0 bg-sov-card rounded-full">{ICON[isRunning ? 'running' : tone]}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-sm font-semibold text-sov-text-primary">
                  {i + 1}. {meta.agent}
                </span>
                {s.model && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sov-green/10 text-sov-green border border-sov-green/20 text-xs font-mono">
                    <Cpu size={11} /> {s.model}
                  </span>
                )}
                {meta.engine && (
                  <span className="px-1.5 py-0.5 rounded bg-sov-border text-sov-text-muted text-xs">no LLM · {meta.engine}</span>
                )}
                <span className="ml-auto text-xs text-sov-text-muted font-mono tabular-nums">
                  +{seconds(s.startAt - t0)}s{took != null && ` · ${seconds(took)}s`}
                </span>
              </div>
              <p className={`mt-0.5 text-[15px] leading-snug break-words ${TEXT_TONE[isRunning ? 'running' : tone]}`}>{s.text}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
