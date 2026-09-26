import React from 'react';
import { X } from 'lucide-react';
import SystemStatus from './SystemStatus';
import ModelInUse from './ModelInUse';
import EgressStatus from './EgressStatus';
import AgentActivityLog from './AgentActivityLog';

/**
 * Docked "System details" panel beside the chat. It is NOT a modal: the
 * conversation stays fully usable while it is open, so you can ask the agent
 * something and watch the steps happen here at the same time. The activity
 * log comes first because that's what you watch while a task runs.
 */
export default function SystemDetails({ onClose, documents, activityLog, isRunning, onClearLog }) {
  return (
    <aside
      aria-label="System details"
      className="w-full md:w-[440px] lg:w-[480px] shrink-0 h-full flex flex-col border-l border-sov-border-light bg-sov-sidebar"
    >
      <div className="flex items-center justify-between px-5 py-3 border-b border-sov-border-light">
        <h2 className="text-base font-semibold text-sov-text-primary">System details</h2>
        <button onClick={onClose} className="p-1 text-sov-text-muted hover:text-sov-text-primary" aria-label="Close system details">
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        <div className="h-[60vh] min-h-[360px]">
          <AgentActivityLog entries={activityLog} isRunning={isRunning} onClear={onClearLog} />
        </div>
        <EgressStatus />
        <SystemStatus documents={documents} />
        <ModelInUse />
      </div>
    </aside>
  );
}
