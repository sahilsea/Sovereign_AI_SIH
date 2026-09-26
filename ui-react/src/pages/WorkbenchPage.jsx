import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { PanelRight, Plus, ShieldCheck, ShieldAlert } from 'lucide-react';
import QueryInput from '../components/Workbench/QueryInput';
import ChatTurn from '../components/Workbench/ChatTurn';
import EmptyState from '../components/Workbench/EmptyState';
import SystemDetails from '../components/Workbench/SystemDetails';
import { apiGet, apiStream } from '../api/client';
import { useModelStatus } from '../contexts/ModelContext';
import useNetworkStatus from '../hooks/useNetworkStatus';

/**
 * The conversation is the page. Every question and its answer stay in a
 * timeline so follow-ups ("what about page 2?") read in context; system
 * status, models, egress and the full activity log live in the collapsible
 * "System details" drawer.
 */
export default function WorkbenchPage() {
  const { modelIdForRole, setActiveModelId, setIsProcessing } = useModelStatus();
  const { data: net } = useNetworkStatus(3000);
  const [documents, setDocuments] = useState([]);
  const [turns, setTurns] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [activityLog, setActivityLog] = useState([]);
  // Open by default on wide screens so the live activity is visible while you chat.
  const [detailsOpen, setDetailsOpen] = useState(() => window.matchMedia('(min-width: 768px)').matches);
  const logIdRef = useRef(0);
  const turnIdRef = useRef(0);
  const bottomRef = useRef(null);

  useEffect(() => {
    apiGet('/documents').then((d) => setDocuments(d || [])).catch(() => setDocuments([]));
  }, []);

  const docTitles = useMemo(
    () => Object.fromEntries(documents.map((d) => [d.doc_id, d.title])),
    [documents],
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  const appendLog = useCallback((entry) => {
    logIdRef.current += 1;
    setActivityLog((prev) => [...prev, { id: logIdRef.current, at: Date.now(), ...entry }].slice(-300));
  }, []);

  const updateTurn = (id, fn) => setTurns((prev) => prev.map((t) => (t.id === id ? fn(t) : t)));

  // Light up the model a stage uses, ahead of the authoritative model_used.
  const glowModel = (event) => {
    let role = null;
    if (event.stage === 'intent' && event.status === 'done') {
      role = event.category === 'code' ? 'code' : event.category === 'task' ? 'planner' : 'primary';
    } else if (event.stage === 'vision' && event.status === 'start') role = 'vision';
    else if (event.stage === 'agent_step' && event.status === 'start') role = event.tool === 'analyze_image' ? 'vision' : 'planner';
    else if (event.stage === 'agent_plan' && event.status === 'start') role = 'planner';
    else if ((event.stage === 'drafting' || event.stage === 'approval_note_drafting') && event.status === 'start') role = 'primary';
    const modelId = role && (modelIdForRole(role) || modelIdForRole('primary'));
    if (modelId) setActiveModelId(modelId);
  };

  const runStream = async (url, body, turnInfo, logInfo) => {
    turnIdRef.current += 1;
    const id = turnIdRef.current;
    setTurns((prev) => [...prev, { id, events: [], result: null, error: null, startedAt: Date.now(), ...turnInfo }]);
    setIsStreaming(true);
    setIsProcessing(true);
    const runStartedAt = Date.now();
    appendLog({ type: 'run', ...logInfo });
    let finished = false;

    const fail = (message) => {
      updateTurn(id, (t) => ({ ...t, error: message || 'The request failed. Please try again.' }));
      appendLog({ type: 'event', event: { stage: 'error', message }, runStartedAt });
    };

    try {
      await apiStream(url, body, (event) => {
        appendLog({ type: 'event', event, runStartedAt });
        updateTurn(id, (t) => ({ ...t, events: [...t.events, { ...event, _at: Date.now() }] }));
        glowModel(event);
        if (event.stage === 'final' && event.response) {
          finished = true;
          updateTurn(id, (t) => ({ ...t, result: event.response }));
          if (event.response.conversation_id) setConversationId(event.response.conversation_id);
          if (event.response.model_used) setActiveModelId(event.response.model_used);
        } else if (event.stage === 'error') {
          finished = true;
          updateTurn(id, (t) => ({ ...t, error: event.message || 'The request failed.' }));
        }
      });
      if (!finished) fail('The connection closed before the agent finished. Please try again.');
    } catch (error) {
      fail(error.message);
    } finally {
      setIsStreaming(false);
      setIsProcessing(false);
    }
  };

  // Follow-ups continue the same conversation, so the backend's short
  // conversation memory (trust/conversations.py) can resolve "that", "it".
  const handleQuerySubmit = (question, uploadId, fileName, mode = 'auto') => runStream(
    '/ask/stream',
    {
      question,
      top_k: 5,
      mode,
      ...(uploadId && { upload_id: uploadId }),
      ...(conversationId && { conversation_id: conversationId }),
    },
    { question, fileName: uploadId ? fileName : null, mode },
    {
      label: `Question: "${question}"`,
      detail: [uploadId && `Attached file: ${fileName}`, conversationId && 'Follow-up', mode === 'agent' && 'Agent mode']
        .filter(Boolean).join(' · '),
    },
  );

  const handleApprovalNote = (uploadId, fileName) => runStream(
    '/ask/approval-note/stream',
    { upload_id: uploadId, ...(conversationId && { conversation_id: conversationId }) },
    { question: `Draft an approval note from ${fileName}`, fileName, mode: 'auto' },
    { label: `Approval note requested for "${fileName}"`, detail: 'Findings extraction → verification → note drafting' },
  );

  const startNewConversation = () => {
    setConversationId(null);
    setTurns([]);
  };

  const external = net?.monitor?.external_count;

  return (
    <div className="flex h-full w-full bg-sov-bg text-sov-text-primary overflow-hidden">
    {/* Chat column: always usable, including while System details is open */}
    <div className={`flex-col h-full min-w-0 flex-1 ${detailsOpen ? 'hidden md:flex' : 'flex'}`}>
      {/* Slim header: conversation controls + a door to system details */}
      <div className="flex items-center justify-between gap-3 px-6 py-3 border-b border-sov-border-light">
        <div className="text-sm text-sov-text-secondary">
          {turns.length ? `${turns.length} message${turns.length > 1 ? 's' : ''} in this conversation` : 'New conversation'}
        </div>
        <div className="flex items-center gap-2">
          {net && (
            <button
              onClick={() => setDetailsOpen(true)}
              className={`hidden sm:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
                external ? 'border-sov-red/50 text-sov-red' : 'border-sov-green/30 text-sov-green'
              }`}
              title="Live network egress monitor"
            >
              {external ? <ShieldAlert size={13} /> : <ShieldCheck size={13} />}
              {external} external connections
            </button>
          )}
          {turns.length > 0 && (
            <button
              onClick={startNewConversation}
              disabled={isStreaming}
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded border border-sov-border-light text-sov-text-secondary hover:text-sov-text-primary disabled:opacity-50"
            >
              <Plus size={13} /> New conversation
            </button>
          )}
          <button
            onClick={() => setDetailsOpen((v) => !v)}
            aria-pressed={detailsOpen}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border transition-colors ${
              detailsOpen
                ? 'border-sov-orange/50 text-sov-orange bg-sov-orange/10'
                : 'border-sov-border-light text-sov-text-secondary hover:text-sov-text-primary'
            }`}
          >
            <PanelRight size={13} /> {detailsOpen ? 'Hide system details' : 'System details'}
          </button>
        </div>
      </div>

      {/* Conversation timeline */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-3xl mx-auto w-full px-4 sm:px-6 py-6 space-y-6">
          {turns.length === 0 ? (
            <EmptyState
              documents={documents}
              onAsk={(q) => handleQuerySubmit(q, null, null, 'auto')}
              disabled={isStreaming}
            />
          ) : (
            turns.map((turn) => <ChatTurn key={turn.id} turn={turn} docTitles={docTitles} />)
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-sov-border-light bg-sov-bg">
        <div className="max-w-3xl mx-auto w-full px-4 sm:px-6 py-4">
          <QueryInput
            onSubmit={handleQuerySubmit}
            onApprovalNote={handleApprovalNote}
            disabled={isStreaming}
            loading={isStreaming}
            placeholder={turns.length ? 'Ask a follow-up…' : 'Describe what you need…'}
          />
        </div>
      </div>

    </div>

      {detailsOpen && (
        <SystemDetails
          onClose={() => setDetailsOpen(false)}
          documents={documents}
          activityLog={activityLog}
          isRunning={isStreaming}
          onClearLog={() => setActivityLog([])}
        />
      )}
    </div>
  );
}
