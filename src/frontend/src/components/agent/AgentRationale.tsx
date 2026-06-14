import { useState } from 'react';
import { TracePanel } from '../TracePanel';

/**
 * AgentRationale — lesbares "Warum" einer Agent-Aktion.
 *
 * Zeigt einen menschlichen Einzeiler (Begruendung/Zusammenfassung) und blendet
 * auf Wunsch den technischen Trace darunter ein. Ersetzt die bisherige
 * JSON-/Tool-Event-Wand auf Freigabe- und Triage-Karten.
 */

interface AgentRationaleProps {
  /** Menschlich lesbare Begruendung (1 Satz). */
  summary: string | null | undefined;
  /** Job-ID fuer optionalen aufklappbaren Trace. */
  jobId?: string | null;
  glassBg?: boolean;
  /** Praefix-Label vor der Begruendung. */
  label?: string;
  className?: string;
}

export function AgentRationale({ summary, jobId, glassBg = false, label = 'Warum', className = '' }: AgentRationaleProps) {
  const [showTrace, setShowTrace] = useState(false);
  const text = (summary || '').trim();
  if (!text && !jobId) return null;

  const muted = glassBg ? 'text-white/60' : 'text-gray-400 dark:text-gray-500';
  const body = glassBg ? 'text-white/90' : 'text-gray-700 dark:text-gray-200';

  return (
    <div className={`text-xs ${className}`}>
      {text && (
        <p className={body}>
          <span className={`font-semibold ${muted}`}>{label}: </span>
          {text}
        </p>
      )}
      {jobId && (
        <>
          <button
            type="button"
            onClick={() => setShowTrace((v) => !v)}
            className={`mt-1 inline-flex items-center gap-1 text-[11px] font-medium transition-colors ${muted} hover:underline`}
          >
            {showTrace ? 'Details ausblenden' : 'Wie kam der Agent dahin?'}
          </button>
          {showTrace && (
            <div className="mt-1">
              <TracePanel jobId={jobId} compact />
            </div>
          )}
        </>
      )}
    </div>
  );
}
