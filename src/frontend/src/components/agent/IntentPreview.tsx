/**
 * IntentPreview — zeigt vor dem Senden, WAS rausgeht.
 *
 * Verhindert Blind-Senden im eingeklappten Zustand: Empfaenger, Betreff und die
 * ersten Zeilen des Inhalts werden inline angezeigt, damit eine bewusste
 * Freigabe moeglich ist. Eiserne Regel: externe Kommunikation = immer HITL.
 */

interface IntentPreviewProps {
  recipients: string[];
  subject: string | null | undefined;
  /** Roh-Snippet (Text oder HTML); wird auf Klartext reduziert. */
  snippet?: string | null;
  glassBg?: boolean;
  maxChars?: number;
  className?: string;
}

function toPlainSnippet(raw: string | null | undefined, maxChars: number): string {
  if (!raw) return '';
  let text = raw;
  if (/<[a-z][\s\S]*>/i.test(text)) {
    text = text.replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<[^>]+>/g, ' ');
  }
  text = text.replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
  return text.length > maxChars ? text.slice(0, maxChars).trimEnd() + '…' : text;
}

export function IntentPreview({ recipients, subject, snippet, glassBg = false, maxChars = 160, className = '' }: IntentPreviewProps) {
  const muted = glassBg ? 'text-white/50' : 'text-gray-400 dark:text-gray-500';
  const value = glassBg ? 'text-white/90' : 'text-gray-700 dark:text-gray-200';
  const box = glassBg
    ? 'border-amber-300/30 bg-amber-500/10'
    : 'border-amber-200 bg-amber-50/60 dark:border-amber-900/40 dark:bg-amber-950/20';
  const plain = toPlainSnippet(snippet, maxChars);

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${box} ${className}`}>
      <div className="flex gap-2">
        <span className={`shrink-0 font-medium ${muted}`}>An</span>
        <span className={`truncate ${value}`}>{recipients.length > 0 ? recipients.join(', ') : 'Unbekannt'}</span>
      </div>
      <div className="mt-0.5 flex gap-2">
        <span className={`shrink-0 font-medium ${muted}`}>Betreff</span>
        <span className={`truncate ${value}`}>{subject || '(kein Betreff)'}</span>
      </div>
      {plain && (
        <p className={`mt-1 line-clamp-2 ${muted}`}>{plain}</p>
      )}
    </div>
  );
}
