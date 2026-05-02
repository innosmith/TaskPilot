import { useState } from 'react';
import { Copy, Check, Sparkles, ExternalLink } from 'lucide-react';
import { api } from '../../api/client';
import type { StyleCtx, CreditorsFilter } from './creditors-types';

interface Props {
  filter: CreditorsFilter;
  styleCtx: StyleCtx;
}

const SECTIONS = [
  {
    key: 'unternehmen',
    title: 'Unternehmenskontext',
    badge: 'Basis',
    body: 'KMU mit Fokus auf IT-Beratung, AI Solutions und strategische Digitalisierung. Dieser Kontext fliesst in den Research-Prompt ein, damit das LLM branchenspezifische Empfehlungen generieren kann.',
  },
  {
    key: 'software',
    title: 'Eingesetzte Software',
    badge: 'Portfolio',
    body: 'Analyse der aktiven Softwarelizenzen aus dem Rechnungsarchiv: Cloud-Infrastruktur, Entwicklungstools, SaaS-Abonnements, Sicherheit und Kommunikation.',
  },
  {
    key: 'standard',
    title: 'Kostenlose Standardtools',
    badge: 'Ergänzung',
    body: 'Tools, die nicht in Rechnungen erscheinen (z.\u00a0B. Open-Source, Freemium-Tiers). Diese werden separat erfasst, damit das Gesamtbild vollständig ist.',
  },
  {
    key: 'integration',
    title: 'Wichtige Integrationen',
    badge: 'Verknüpfung',
    body: 'Abhängigkeiten und Integrationsanforderungen zwischen den Tools — API-Verbindungen, SSO, Datenflüsse und Automatisierungen.',
  },
  {
    key: 'zusatz',
    title: 'Zusatzinformationen',
    badge: 'Optional',
    body: '',
  },
] as const;

export function CreditorsResearch({ filter, styleCtx }: Props) {
  const { hasBg, textPrimary, textSecondary, textMuted } = styleCtx;

  const card = `rounded-xl p-4 sm:p-5 ${
    hasBg
      ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10'
      : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50'
  }`;

  const [open, setOpen] = useState<Record<string, boolean>>({ unternehmen: true });
  const [zusatzText, setZusatzText] = useState('');
  const [researchPrompt, setResearchPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const toggle = (key: string) =>
    setOpen(prev => ({ ...prev, [key]: !prev[key] }));

  const generate = async () => {
    setLoading(true);
    try {
      const res = await api.post<{ prompt: string }>('/api/creditors/deep-research', {
        extra_context: zusatzText || undefined,
      });
      setResearchPrompt(res.prompt ?? '');
    } catch {
      setResearchPrompt('Fehler beim Generieren des Prompts.');
    } finally {
      setLoading(false);
    }
  };

  const copyPrompt = async () => {
    await navigator.clipboard.writeText(researchPrompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Configurable context sections */}
      <div className={card}>
        <h3 className={`text-sm font-semibold mb-4 ${textPrimary}`}>Konfigurierbarer Kontext</h3>
        <div className="flex flex-col gap-1.5">
          {SECTIONS.map(s => (
            <div key={s.key} className="rounded-lg overflow-hidden">
              <button
                onClick={() => toggle(s.key)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm font-medium transition-colors ${
                  hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
                } ${textPrimary}`}
              >
                <span className={`text-xs w-4 shrink-0 transition-transform duration-200 ${open[s.key] ? 'rotate-90' : ''}`}>▸</span>
                <span className="flex-1">{s.title}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  hasBg ? 'bg-white/10 text-white/60' : 'bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                }`}>
                  {s.badge}
                </span>
              </button>
              <div
                className={`grid transition-[grid-template-rows] duration-200 ${
                  open[s.key] ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
                }`}
              >
                <div className="overflow-hidden">
                  <div className={`px-3 pb-3 pt-1 text-xs leading-relaxed ${textSecondary}`}>
                    {s.key === 'zusatz' ? (
                      <textarea
                        value={zusatzText}
                        onChange={e => setZusatzText(e.target.value)}
                        placeholder="Zusätzlichen Kontext hier eingeben…"
                        rows={3}
                        className={`w-full rounded-lg border px-3 py-2 text-xs resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/40 ${
                          hasBg
                            ? 'border-white/10 bg-white/5 text-white placeholder:text-white/30'
                            : 'border-gray-300 bg-white text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100'
                        }`}
                      />
                    ) : (
                      s.body
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Prompt generation */}
      <div className={card}>
        <div className="flex items-center justify-between mb-3">
          <h3 className={`text-sm font-semibold ${textPrimary}`}>Research-Prompt</h3>
          <button
            onClick={generate}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <>
                <span className="h-3 w-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Generiere…
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" />
                {researchPrompt ? 'Neu generieren' : 'Prompt generieren'}
              </>
            )}
          </button>
        </div>

        <div className="relative">
          <pre
            className={`rounded-lg p-4 text-xs font-mono leading-relaxed max-h-96 overflow-auto whitespace-pre-wrap ${
              hasBg
                ? 'bg-black/40 text-gray-200 ring-1 ring-white/10'
                : 'bg-gray-900 text-gray-200 dark:bg-gray-950'
            }`}
          >
            {researchPrompt || 'Noch kein Prompt generiert. Klicken Sie auf «Prompt generieren».'}
          </pre>
          {researchPrompt && (
            <button
              onClick={copyPrompt}
              className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
            >
              {copied ? <><Check className="h-3 w-3" /> Kopiert</> : <><Copy className="h-3 w-3" /> Kopieren</>}
            </button>
          )}
        </div>
        {researchPrompt && (
          <p className={`text-[10px] mt-1.5 ${textMuted}`}>
            {researchPrompt.length.toLocaleString('de-CH')} Zeichen
          </p>
        )}
      </div>

      {/* Target info */}
      <div className={`rounded-xl p-4 flex items-start gap-3 ${
        hasBg ? 'bg-indigo-950/40 ring-1 ring-indigo-400/20' : 'bg-indigo-50 dark:bg-indigo-950/50'
      }`}>
        <ExternalLink className={`h-4 w-4 mt-0.5 shrink-0 ${hasBg ? 'text-indigo-400' : 'text-indigo-500 dark:text-indigo-400'}`} />
        <div>
          <p className={`text-xs leading-relaxed ${hasBg ? 'text-indigo-200' : 'text-indigo-900 dark:text-indigo-200'}`}>
            Diesen Prompt können Sie in{' '}
            <a href="https://perplexity.ai" target="_blank" rel="noreferrer" className="underline hover:no-underline font-medium">
              Perplexity
            </a>
            , Gemini Deep Research oder einem anderen LLM-Tool ausführen für eine strategische IT-Portfolio-Analyse.
          </p>
        </div>
      </div>
    </div>
  );
}
