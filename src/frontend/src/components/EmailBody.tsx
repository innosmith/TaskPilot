import { sanitizeEmailHtml } from '../utils/emailHtml';

interface EmailBodyProps {
  html: string;
  /** Glass-Modus (Hintergrundbild aktiv): erzwingt helle Schrift via prose-invert. */
  glassBg?: boolean;
  /** Prose-Grösse: 'xs' für kompakte Thread-Ansichten, 'sm' sonst. */
  size?: 'xs' | 'sm';
  className?: string;
}

/**
 * Rendert E-Mail-HTML (Microsoft Graph / Outlook) theme-sicher: Inline-Farben
 * werden gestrippt (sanitizeEmailHtml) und über die `.email-content`-Klasse durch
 * die Theme-Farbe ersetzt, damit der Text in Light, Dark und Glass-Modus lesbar bleibt.
 */
export function EmailBody({ html, glassBg = false, size = 'sm', className = '' }: EmailBodyProps) {
  const proseSize = size === 'xs' ? 'prose-xs' : 'prose-sm';
  const invert = glassBg ? 'prose-invert' : 'dark:prose-invert';
  return (
    <div
      className={`email-content prose ${proseSize} max-w-none break-words ${invert} ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: sanitizeEmailHtml(html) }}
    />
  );
}
