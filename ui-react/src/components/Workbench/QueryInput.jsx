import React, { useState, useRef } from 'react';
import { Sparkles, Paperclip, PenTool, ClipboardCheck, Code, Play, X, Loader2, FileSignature, Bot } from 'lucide-react';
import { apiUpload, apiDelete } from '../../api/client';

export default function QueryInput({ onSubmit, onApprovalNote, disabled, loading, placeholder = 'Describe what you need...' }) {
  const [question, setQuestion] = useState('');
  const [uploadId, setUploadId] = useState(null);
  const [fileName, setFileName] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadInfo, setUploadInfo] = useState(null);
  // Agent mode: always run the multi-step, tool-using agent loop instead of
  // letting the intent router decide (harness/agent_loop.py).
  const [agentMode, setAgentMode] = useState(false);
  
  const fileInputRef = useRef(null);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);
    try {
      const response = await apiUpload('/ask/upload', file);
      setUploadId(response.upload_id);
      setFileName(response.filename);
      setUploadInfo(response);
    } catch (error) {
      setUploadError(error.message || 'Upload failed.');
    } finally {
      setIsUploading(false);
      // Reset so picking the same file again still fires onChange.
      e.target.value = '';
    }
  };

  const removeFile = async () => {
    if (uploadId) {
      try {
        await apiDelete(`/ask/upload/${uploadId}`);
      } catch (error) {
        console.error('Failed to remove upload:', error);
      }
    }
    setUploadId(null);
    setFileName('');
    setUploadInfo(null);
  };

  // Backend requires question.length >= 3 regardless of attachments
  // (contracts.py AskRequest.question, min_length=3) -- enforce the same
  // rule here so a too-short question is caught before the request goes
  // out, instead of failing silently with a 422 the UI never surfaced.
  const trimmedQuestion = question.trim();
  const isTooShort = trimmedQuestion.length > 0 && trimmedQuestion.length < 3;
  const canSubmit = trimmedQuestion.length >= 3;

  const handleSubmit = () => {
    if (!canSubmit) return;

    onSubmit(trimmedQuestion, uploadId, fileName, agentMode ? 'agent' : 'auto');
    setQuestion('');
  };

  return (
    <div className="w-full bg-sov-card rounded-xl border border-sov-border overflow-hidden focus-within:border-sov-orange transition-colors duration-300">
      <div className="flex items-start gap-3 p-4">
        <Sparkles className="text-sov-orange mt-1 shrink-0" size={20} />
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-transparent text-sov-text-primary placeholder-sov-text-muted outline-none resize-none min-h-[56px] max-h-48 leading-relaxed"
          disabled={disabled || loading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
        />
      </div>

      {fileName && (
        <div className="px-4 py-2 border-t border-sov-border-light bg-sov-sidebar flex items-center justify-between gap-3">
          <div className="bg-sov-border px-3 py-1 rounded-full flex items-center gap-2 text-sm text-sov-text-primary">
            <span className="truncate max-w-[200px]">{fileName}</span>
            <button onClick={removeFile} className="text-sov-text-muted hover:text-sov-red transition-colors">
              <X size={14} />
            </button>
          </div>
          {uploadInfo && (
            <span className="text-xs text-sov-text-muted flex-1">
              {uploadInfo.text_chunks} text chunk(s)
              {uploadInfo.ocr_pages ? ` · ${uploadInfo.ocr_pages} read by on-device OCR` : ''}
              {uploadInfo.images ? ` · ${uploadInfo.images} image(s) for the vision model` : ''}
              {uploadInfo.is_spreadsheet ? ' · spreadsheet → agent tools' : ''}
            </span>
          )}
          {onApprovalNote && (
            <button
              onClick={() => onApprovalNote(uploadId, fileName)}
              disabled={disabled || loading}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded border border-sov-orange text-sov-orange hover:bg-sov-orange hover:text-black transition-colors disabled:opacity-50"
              title="Read this inspection report and draft a formal approval note"
            >
              <FileSignature size={14} /> Draft Approval Note
            </button>
          )}
        </div>
      )}

      {uploadError && (
        <div className="px-4 py-2 border-t border-sov-border-light bg-sov-red/10 text-sov-red text-xs">
          {uploadError}
        </div>
      )}

      {isTooShort && (
        <div className="px-4 py-2 border-t border-sov-border-light bg-sov-amber/10 text-sov-amber text-xs">
          Question must be at least 3 characters.
        </div>
      )}

      <div className="flex items-center justify-between p-3 border-t border-sov-border-light bg-sov-sidebar">
        <div className="flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".pdf,.pptx,.docx,.xlsx,.xlsm,.csv,.txt,.md,.json,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tif,.tiff"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || loading || isUploading}
            className={`p-2 rounded-lg flex items-center gap-2 transition-colors ${
              uploadId ? 'bg-sov-border text-sov-text-primary' : 'text-sov-text-secondary hover:bg-sov-border hover:text-sov-text-primary'
            }`}
            title="Attach File"
          >
            {isUploading ? <Loader2 className="animate-spin" size={18} /> : <Paperclip size={18} />}
          </button>
          
          <button
            onClick={() => setQuestion(prev => (prev + (prev.length > 0 && !prev.endsWith(' ') ? ' ' : '') + 'Analyze the attached image: ').trimStart())}
            disabled={disabled || loading}
            className="p-2 rounded-lg flex items-center gap-2 text-sov-text-secondary hover:bg-sov-border hover:text-sov-text-primary transition-colors"
            title="Read Drawing (Vision Mode)"
          >
            <PenTool size={18} />
          </button>

          <button
            onClick={() => setQuestion(prev => (prev + (prev.length > 0 && !prev.endsWith(' ') ? ' ' : '') + 'What is the standard operating procedure for ').trimStart())}
            disabled={disabled || loading}
            className="p-2 rounded-lg flex items-center gap-2 text-sov-text-secondary hover:bg-sov-border hover:text-sov-text-primary transition-colors"
            title="Check SOP"
          >
            <ClipboardCheck size={18} />
          </button>

          <button
            onClick={() => setQuestion(prev => (prev + (prev.length > 0 && !prev.endsWith(' ') ? ' ' : '') + 'Write a python script to ').trimStart())}
            disabled={disabled || loading}
            className="p-2 rounded-lg flex items-center gap-2 text-sov-text-secondary hover:bg-sov-border hover:text-sov-text-primary transition-colors"
            title="Run Code"
          >
            <Code size={18} />
          </button>
        </div>

        <div className="flex items-center gap-3">
        <button
          onClick={() => setAgentMode(v => !v)}
          disabled={disabled || loading}
          aria-pressed={agentMode}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            agentMode
              ? 'bg-sov-orange/15 text-sov-orange border-sov-orange/50'
              : 'text-sov-text-secondary border-sov-border-light hover:text-sov-text-primary'
          }`}
          title="Agent mode: plan the task and use local tools (document search, files, spreadsheets, sandboxed code, vision) step by step"
        >
          <Bot size={15} /> Agent {agentMode ? 'on' : 'auto'}
        </button>
        <button
          onClick={handleSubmit}
          disabled={disabled || loading || !canSubmit}
          className="bg-sov-orange hover:bg-sov-orange-dark text-white px-6 py-2 rounded-lg flex items-center gap-2 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
          Run
        </button>
        </div>
      </div>
    </div>
  );
}
