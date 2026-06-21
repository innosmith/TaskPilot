// Zentrale Provider-Reihenfolge und -Labels für LLM-Modell-Auswahlen.
// Es gibt kein gemeinsames Dropdown-Component; diese Util hält die Sortierung
// konsistent über Chat, Settings und die Finanzanalysen.

export interface ProviderModel {
  provider: string;
}

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama (Lokal)',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openai: 'OpenAI',
  perplexity: 'Perplexity',
};

// Standard (Chat, Agenten, Settings): lokale Modelle zuerst — das Projekt
// betont die Stärke lokaler, datenschutzfreundlicher Verarbeitung.
export const DEFAULT_PROVIDER_ORDER = ['ollama', 'anthropic', 'gemini', 'openai', 'perplexity'];

// Finanzanalysen: Cloud-Flaggschiffe zuerst (Tiefe/Komplexität), lokale Modelle
// zuletzt — hier wird mit anonymisierten Daten gegen die stärksten Modelle gefahren.
export const ANALYSIS_PROVIDER_ORDER = ['anthropic', 'gemini', 'openai', 'perplexity', 'ollama'];

export interface ProviderGroup<T> {
  provider: string;
  label: string;
  items: T[];
}

/** Gruppiert Modelle nach Provider in der angegebenen Reihenfolge; unbekannte
 *  Provider landen als „Andere" am Schluss. */
export function groupModelsByProvider<T extends ProviderModel>(
  models: T[],
  order: string[] = DEFAULT_PROVIDER_ORDER,
): ProviderGroup<T>[] {
  const groups: ProviderGroup<T>[] = [];
  for (const p of order) {
    const items = models.filter(m => m.provider === p);
    if (items.length > 0) groups.push({ provider: p, label: PROVIDER_LABELS[p] || p, items });
  }
  const rest = models.filter(m => !order.includes(m.provider));
  if (rest.length > 0) groups.push({ provider: 'other', label: 'Andere', items: rest });
  return groups;
}
