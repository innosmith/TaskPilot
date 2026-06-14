/**
 * ConfidenceBadge — einheitliche Darstellung der Agent-Sicherheit (0..1).
 *
 * Macht das bereits vorhandene, aber bislang ungenutzte `confidence`-Signal
 * sichtbar. Wird in Inbox, Freigaben und ueberall dort verwendet, wo der Agent
 * eine Einschaetzung mit Sicherheitsgrad liefert.
 */

type ConfidenceLevel = 'high' | 'medium' | 'low';

function levelOf(value: number): ConfidenceLevel {
  if (value >= 0.8) return 'high';
  if (value >= 0.5) return 'medium';
  return 'low';
}

const LEVEL_STYLES: Record<ConfidenceLevel, { solid: string; glass: string; label: string }> = {
  high: {
    solid: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    glass: 'bg-emerald-500/25 text-emerald-100',
    label: 'Hohe Sicherheit',
  },
  medium: {
    solid: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    glass: 'bg-amber-500/25 text-amber-100',
    label: 'Mittlere Sicherheit',
  },
  low: {
    solid: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    glass: 'bg-red-500/25 text-red-100',
    label: 'Geringe Sicherheit — bitte gut prüfen',
  },
};

interface ConfidenceBadgeProps {
  /** Sicherheit als 0..1 (oder null/undefined → nichts rendern). */
  confidence: number | null | undefined;
  glassBg?: boolean;
  /** Nur farbiger Punkt ohne Prozentzahl. */
  dotOnly?: boolean;
  className?: string;
}

export function ConfidenceBadge({ confidence, glassBg = false, dotOnly = false, className = '' }: ConfidenceBadgeProps) {
  if (confidence == null || Number.isNaN(confidence)) return null;
  const value = confidence > 1 ? confidence / 100 : confidence;
  const level = levelOf(value);
  const styles = LEVEL_STYLES[level];
  const pct = Math.round(value * 100);

  if (dotOnly) {
    const dot = level === 'high' ? 'bg-emerald-500' : level === 'medium' ? 'bg-amber-500' : 'bg-red-500';
    return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${dot} ${className}`} title={`${styles.label} (${pct}%)`} />;
  }

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold leading-4 ${glassBg ? styles.glass : styles.solid} ${className}`}
      title={`${styles.label} (${pct}%)`}
    >
      {pct}% sicher
    </span>
  );
}
