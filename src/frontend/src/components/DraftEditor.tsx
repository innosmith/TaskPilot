import { useState, useCallback } from 'react';
import { RichTextEditor } from './RichTextEditor';
import { api } from '../api/client';

interface DraftEditorProps {
  jobId: string;
  subject: string;
  bodyHtml: string;
  toRecipients: string[];
  ccRecipients: string[];
  glassBg?: boolean;
  onSaved?: () => void;
  onSentAfterEdit?: () => void;
  onCancel: () => void;
}

export function DraftEditor({
  jobId,
  subject: initialSubject,
  bodyHtml: initialBody,
  toRecipients: initialTo,
  ccRecipients: initialCc,
  glassBg = false,
  onSaved,
  onSentAfterEdit,
  onCancel,
}: DraftEditorProps) {
  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState(initialBody);
  const [toField, setToField] = useState(initialTo.join(', '));
  const [ccField, setCcField] = useState(initialCc.join(', '));
  const [showCc, setShowCc] = useState(initialCc.length > 0);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);

  const parseRecipients = (val: string) =>
    val.split(',').map(s => s.trim()).filter(Boolean);

  const saveDraft = useCallback(async () => {
    return api.patch(`/api/agent-jobs/${jobId}/draft`, {
      subject,
      body_html: body,
      to_recipients: parseRecipients(toField),
      cc_recipients: parseRecipients(ccField),
    });
  }, [jobId, subject, body, toField, ccField]);

  const handleSaveOnly = async () => {
    setSaving(true);
    try {
      await saveDraft();
      onSaved?.();
    } catch (err) {
      console.error('Draft speichern fehlgeschlagen:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndSend = async () => {
    setSending(true);
    try {
      await saveDraft();
      await api.patch(`/api/agent-jobs/${jobId}`, { status: 'completed' });
      onSentAfterEdit?.();
    } catch (err) {
      console.error('Senden fehlgeschlagen:', err);
    } finally {
      setSending(false);
    }
  };

  const fieldBg = glassBg
    ? 'bg-white/10 border-white/20 text-white placeholder-white/40'
    : 'bg-white border-gray-200 text-gray-900 placeholder-gray-400 dark:bg-gray-900 dark:border-gray-700 dark:text-gray-100';

  const labelStyle = glassBg
    ? 'text-white/60 text-xs font-medium'
    : 'text-gray-500 text-xs font-medium dark:text-gray-400';

  return (
    <div className="animate-in fade-in slide-in-from-top-2 duration-300 space-y-3">
      {/* Betreff */}
      <div>
        <label className={labelStyle}>Betreff</label>
        <input
          type="text"
          value={subject}
          onChange={e => setSubject(e.target.value)}
          className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${fieldBg}`}
        />
      </div>

      {/* An */}
      <div>
        <label className={labelStyle}>An</label>
        <input
          type="text"
          value={toField}
          onChange={e => setToField(e.target.value)}
          placeholder="empfaenger@beispiel.ch"
          className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${fieldBg}`}
        />
      </div>

      {/* CC */}
      {!showCc ? (
        <button
          type="button"
          onClick={() => setShowCc(true)}
          className={`text-xs ${glassBg ? 'text-white/50 hover:text-white/80' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'}`}
        >
          + CC hinzufügen
        </button>
      ) : (
        <div>
          <label className={labelStyle}>CC</label>
          <input
            type="text"
            value={ccField}
            onChange={e => setCcField(e.target.value)}
            placeholder="cc@beispiel.ch"
            className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${fieldBg}`}
          />
        </div>
      )}

      {/* Body */}
      <RichTextEditor
        content={body}
        onChange={setBody}
        editable
        glassBg={glassBg}
        minHeight="200px"
      />

      {/* Aktions-Buttons */}
      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={handleSaveAndSend}
          disabled={sending}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
            glassBg
              ? 'bg-emerald-600/90 text-white hover:bg-emerald-600 shadow-sm'
              : 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm'
          }`}
        >
          {sending ? 'Wird gesendet…' : 'Speichern und Senden'}
        </button>
        <button
          type="button"
          onClick={handleSaveOnly}
          disabled={saving}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
            glassBg
              ? 'bg-white/10 text-white hover:bg-white/20 border border-white/20'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600'
          }`}
        >
          {saving ? 'Wird gespeichert…' : 'Nur speichern'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            glassBg
              ? 'text-white/60 hover:text-white hover:bg-white/10'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800'
          }`}
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}
