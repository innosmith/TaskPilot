import { useState } from 'react';

/**
 * ActionReceipt — Quittung fuer eine Agent-Aktion.
 *
 * "Was wurde getan, wo, wann" — plus optionales Undo fuer umkehrbare Aktionen.
 * Baustein fuer den ansichtsuebergreifenden Aktivitaets-/Receipt-Feed.
 */

export interface ReceiptData {
  id: string;
  /** Menschlich lesbare Beschreibung, z. B. "Antwort gesendet". */
  label: string;
  /** Wo/woran, z. B. Betreff oder Aufgabentitel. */
  target?: string | null;
  /** ISO-Zeitstempel. */
  at?: string | null;
  /** Status fuer Faerbung. */
  tone?: 'done' | 'pending' | 'failed' | 'info';
  /** Emoji-/Text-Icon. */
  icon?: string;
}

function relTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return 'gerade eben';
  if (diffMin < 60) return `vor ${diffMin} Min.`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `vor ${diffH} Std.`;
  const diffD = Math.floor(diffH / 24);
  return `vor ${diffD} Tag${diffD > 1 ? 'en' : ''}`;
}

const TONE_DOT: Record<NonNullable<ReceiptData['tone']>, string> = {
  done: 'bg-emerald-500',
  pending: 'bg-amber-500',
  failed: 'bg-red-500',
  info: 'bg-indigo-400',
};

interface ActionReceiptProps {
  receipt: ReceiptData;
  glassBg?: boolean;
  /** Wenn gesetzt, wird ein Undo-Button gezeigt (umkehrbare Aktion). */
  onUndo?: (id: string) => Promise<void> | void;
  /** Klick auf die Zeile (z. B. zum Quell-Objekt springen). */
  onOpen?: (id: string) => void;
}

export function ActionReceipt({ receipt, glassBg = false, onUndo, onOpen }: ActionReceiptProps) {
  const [undoing, setUndoing] = useState(false);
  const [undone, setUndone] = useState(false);
  const tone = receipt.tone ?? 'info';
  const primary = glassBg ? 'text-white/90' : 'text-gray-800 dark:text-gray-100';
  const muted = glassBg ? 'text-white/50' : 'text-gray-400 dark:text-gray-500';
  const hover = glassBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50';

  const handleUndo = async () => {
    if (!onUndo) return;
    setUndoing(true);
    try {
      await onUndo(receipt.id);
      setUndone(true);
    } finally {
      setUndoing(false);
    }
  };

  return (
    <div
      className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 ${onOpen ? `cursor-pointer ${hover}` : ''}`}
      onClick={onOpen ? () => onOpen(receipt.id) : undefined}
    >
      {receipt.icon ? (
        <span className="shrink-0 text-sm leading-none">{receipt.icon}</span>
      ) : (
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[tone]}`} />
      )}
      <div className="min-w-0 flex-1">
        <div className={`truncate text-sm ${primary}`}>
          {receipt.label}
          {receipt.target && <span className={muted}> · {receipt.target}</span>}
        </div>
        {receipt.at && <div className={`text-[11px] ${muted}`}>{relTime(receipt.at)}</div>}
      </div>
      {onUndo && !undone && tone !== 'failed' && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); handleUndo(); }}
          disabled={undoing}
          className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-40 ${
            glassBg ? 'text-amber-200 hover:bg-amber-500/20' : 'text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-900/20'
          }`}
        >
          {undoing ? '…' : 'Rückgängig'}
        </button>
      )}
      {undone && <span className={`shrink-0 text-[11px] ${muted}`}>rückgängig gemacht</span>}
    </div>
  );
}
