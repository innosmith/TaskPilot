import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';
import { BackgroundPicker } from '../components/BackgroundPicker';

// ── Types ────────────────────────────────────────────

interface Signal {
  id: number;
  title: string;
  source_name: string | null;
  url: string | null;
  type: string | null;
  status: string | null;
  description: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  total_score: number | null;
  relevant_role: string | null;
  ai_reason: string | null;
  topic_name: string | null;
  category: string | null;
  full_content?: string | null;
}

interface SignalListResponse {
  signals: Signal[];
  total: number;
  limit: number;
  offset: number;
}

interface Briefing {
  id: number;
  briefing_date: string | null;
  signal_count: number | null;
  high_score_count: number | null;
  avg_score: number | null;
  signal_density: string | null;
  top_keywords: string | null;
  createdAt: string | null;
  briefing_text?: string | null;
  briefing_html?: string | null;
  audio_url?: string | null;
  duration_seconds?: number | null;
}

interface DeepDive {
  id: number;
  persona_name: string | null;
  preview: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  last_synthesis?: string | null;
}

interface Persona {
  id: number;
  persona_name: string;
  description: string | null;
}

interface Topic {
  id: number;
  topic_name: string;
  relevance_weight: number | null;
  category: string | null;
  keywords: string | null;
  strategic_why: string | null;
}

interface Stats {
  total: number;
  high_score: number;
  medium_score: number;
  low_score: number;
  avg_score: number;
  today: number;
  this_week: number;
  sources: number;
  rss_count: number;
  youtube_count: number;
  web_count: number;
}

type TabId = 'signals' | 'briefings' | 'deep-dives';
type TypeFilter = '' | 'rss' | 'youtube' | 'web';

// ── Component ────────────────────────────────────────

export function SignalePage() {
  const [tab, setTab] = useState<TabId>('signals');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<Stats | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);

  // Signals state
  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalTotal, setSignalTotal] = useState(0);
  const [signalOffset, setSignalOffset] = useState(0);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('');
  const [minScore, setMinScore] = useState(0);
  const [topicFilter, setTopicFilter] = useState('');
  const [personaFilter, setPersonaFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout>>();
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Briefings state
  const [briefings, setBriefings] = useState<Briefing[]>([]);
  const [selectedBriefing, setSelectedBriefing] = useState<Briefing | null>(null);

  // Deep Dives state
  const [deepDives, setDeepDives] = useState<DeepDive[]>([]);
  const [selectedDeepDive, setSelectedDeepDive] = useState<DeepDive | null>(null);
  const [ddPersonaFilter, setDdPersonaFilter] = useState('');

  // Background
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);

  const LIMIT = 30;

  // ── Load stats + filter options ──

  useEffect(() => {
    Promise.all([
      api.get<Stats>('/api/signa/stats').catch(() => null),
      api.get<Persona[]>('/api/signa/personas').catch(() => []),
      api.get<Topic[]>('/api/signa/topics').catch(() => []),
      api.get<{ signale_background_url: string | null }>('/api/settings')
        .then(s => s.signale_background_url)
        .catch(() => null),
    ]).then(([s, p, t, bg]) => {
      if (s) setStats(s);
      setPersonas(p as Persona[]);
      setTopics(t as Topic[]);
      if (bg) setBgUrl(bg);
    });
  }, []);

  // ── Debounce search ──

  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setDebouncedSearch(searchTerm), 400);
    return () => clearTimeout(searchTimer.current);
  }, [searchTerm]);

  // ── Fetch signals ──

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(LIMIT));
      params.set('offset', String(signalOffset));
      if (typeFilter) params.set('type', typeFilter);
      if (minScore > 0) params.set('min_score', String(minScore));
      if (topicFilter) params.set('topic', topicFilter);
      if (personaFilter) params.set('persona', personaFilter);
      if (debouncedSearch) params.set('search', debouncedSearch);

      const data = await api.get<SignalListResponse>(`/api/signa/signals?${params}`);
      setSignals(data.signals);
      setSignalTotal(data.total);
    } catch { /* handled */ }
    finally { setLoading(false); }
  }, [signalOffset, typeFilter, minScore, topicFilter, personaFilter, debouncedSearch]);

  useEffect(() => {
    if (tab === 'signals') fetchSignals();
  }, [tab, fetchSignals]);

  // ── Fetch briefings ──

  const fetchBriefings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<Briefing[]>('/api/signa/briefings?limit=50');
      setBriefings(data);
    } catch { /* handled */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (tab === 'briefings') fetchBriefings();
  }, [tab, fetchBriefings]);

  // ── Fetch deep dives ──

  const fetchDeepDives = useCallback(async () => {
    setLoading(true);
    try {
      const params = ddPersonaFilter ? `?persona=${encodeURIComponent(ddPersonaFilter)}&limit=50` : '?limit=50';
      const data = await api.get<DeepDive[]>(`/api/signa/deep-dives${params}`);
      setDeepDives(data);
    } catch { /* handled */ }
    finally { setLoading(false); }
  }, [ddPersonaFilter]);

  useEffect(() => {
    if (tab === 'deep-dives') fetchDeepDives();
  }, [tab, fetchDeepDives]);

  // ── Signal detail ──

  const openSignalDetail = async (id: number) => {
    setLoadingDetail(true);
    try {
      const data = await api.get<Signal>(`/api/signa/signals/${id}`);
      setSelectedSignal(data);
    } catch { /* handled */ }
    finally { setLoadingDetail(false); }
  };

  const openBriefingDetail = async (id: number) => {
    try {
      const data = await api.get<Briefing>(`/api/signa/briefings/${id}`);
      setSelectedBriefing(data);
    } catch { /* handled */ }
  };

  const openDeepDiveDetail = async (id: number) => {
    try {
      const data = await api.get<DeepDive>(`/api/signa/deep-dives/${id}`);
      setSelectedDeepDive(data);
    } catch { /* handled */ }
  };

  // ── Background ──

  const handleBgSelect = async (url: string | null) => {
    await api.patch('/api/settings', { signale_background_url: url });
    setBgUrl(url);
  };

  const hasBg = !!bgUrl;
  const isGradient = bgUrl?.startsWith('gradient:') ?? false;
  const bgStyle = isGradient
    ? { background: bgUrl!.slice('gradient:'.length) }
    : hasBg
      ? { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' }
      : undefined;

  // ── Pagination ──

  const totalPages = Math.ceil(signalTotal / LIMIT);
  const currentPage = Math.floor(signalOffset / LIMIT) + 1;

  // ── Render ──

  return (
    <div className="relative flex h-full flex-col" style={!hasBg ? undefined : bgStyle}>
      {!hasBg && <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-indigo-50/30 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950/20" />}
      {hasBg && !isGradient && <div className="absolute inset-0 bg-black/25 dark:bg-black/40" />}
      {isGradient && <div className="absolute inset-0 bg-black/10 dark:bg-black/25" />}

      <div className="relative z-10 flex h-full flex-col">
        {/* ── Header ── */}
        <div className={`border-b px-6 py-4 backdrop-blur-xl ${hasBg ? 'border-white/10 bg-black/35' : 'border-white/40 bg-white/50 dark:border-gray-800 dark:bg-gray-900/50'}`}>
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className={`text-xl font-bold ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
                  Signale
                </h1>
                {stats && (
                  <span className="flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                    {stats.total.toLocaleString('de-CH')} Signale
                  </span>
                )}
              </div>
              {stats && (
                <div className={`mt-1 flex items-center gap-4 text-xs ${hasBg ? 'text-white/60' : 'text-gray-500 dark:text-gray-400'}`}>
                  <span>{stats.today} heute</span>
                  <span>{stats.this_week} diese Woche</span>
                  <span>{stats.high_score} High-Score (&#8805;8)</span>
                  <span>&#216; {stats.avg_score}</span>
                  <span>{stats.sources} Quellen</span>
                </div>
              )}
            </div>
            <button
              onClick={() => setBgPickerOpen(true)}
              className={`rounded-lg p-2 transition-colors ${hasBg ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`}
              title="Hintergrund ändern"
            >
              <ImageIcon className="h-4.5 w-4.5" />
            </button>
          </div>
        </div>

        {/* ── Tabs ── */}
        <div className={`border-b px-6 backdrop-blur-sm ${hasBg ? 'border-white/10 bg-black/30' : 'border-white/40 bg-white/50 dark:border-gray-800 dark:bg-gray-900/50'}`}>
          <div className="flex items-center gap-1">
            {([
              { id: 'signals' as TabId, label: 'Signale', count: signalTotal },
              { id: 'briefings' as TabId, label: 'Briefings', count: briefings.length },
              { id: 'deep-dives' as TabId, label: 'Deep Dives', count: deepDives.length },
            ]).map(t => (
              <button
                key={t.id}
                onClick={() => { setTab(t.id); setSelectedSignal(null); setSelectedBriefing(null); setSelectedDeepDive(null); }}
                className={`relative px-4 py-3 text-sm font-medium transition-colors ${
                  tab === t.id
                    ? hasBg ? 'text-white' : 'text-indigo-600 dark:text-indigo-400'
                    : hasBg ? 'text-white/60 hover:text-white/80' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                }`}
              >
                {t.label}
                {tab === t.id && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-indigo-500" />}
              </button>
            ))}
          </div>
        </div>

        {/* ── Signals Tab ── */}
        {tab === 'signals' && (
          <>
            {/* Filter bar */}
            <div className={`border-b px-6 py-3 backdrop-blur-sm ${hasBg ? 'border-white/10 bg-black/25' : 'border-gray-100 bg-white/40 dark:border-gray-800 dark:bg-gray-900/40'}`}>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  placeholder="Suchen..."
                  className={`w-52 rounded-lg border px-3 py-1.5 text-sm outline-none transition-colors ${
                    hasBg
                      ? 'border-white/20 bg-white/10 text-white placeholder:text-white/40 focus:border-white/40'
                      : 'border-gray-200 bg-white text-gray-900 placeholder:text-gray-400 focus:border-indigo-400 dark:border-gray-700 dark:bg-gray-800 dark:text-white'
                  }`}
                />
                <select
                  value={typeFilter}
                  onChange={e => { setTypeFilter(e.target.value as TypeFilter); setSignalOffset(0); }}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${
                    hasBg
                      ? 'border-white/20 bg-white/10 text-white'
                      : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
                  }`}
                >
                  <option value="">Alle Typen</option>
                  <option value="rss">RSS</option>
                  <option value="youtube">YouTube</option>
                  <option value="web">Web</option>
                </select>
                <select
                  value={topicFilter}
                  onChange={e => { setTopicFilter(e.target.value); setSignalOffset(0); }}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${
                    hasBg
                      ? 'border-white/20 bg-white/10 text-white'
                      : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
                  }`}
                >
                  <option value="">Alle Topics</option>
                  {topics.map(t => <option key={t.id} value={t.topic_name}>{t.topic_name}</option>)}
                </select>
                <select
                  value={personaFilter}
                  onChange={e => { setPersonaFilter(e.target.value); setSignalOffset(0); }}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${
                    hasBg
                      ? 'border-white/20 bg-white/10 text-white'
                      : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
                  }`}
                >
                  <option value="">Alle Personas</option>
                  {personas.map(p => <option key={p.id} value={p.persona_name}>{p.persona_name}</option>)}
                </select>
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${hasBg ? 'text-white/60' : 'text-gray-500 dark:text-gray-400'}`}>Min-Score:</span>
                  <input
                    type="range"
                    min={0} max={10} step={0.5}
                    value={minScore}
                    onChange={e => { setMinScore(Number(e.target.value)); setSignalOffset(0); }}
                    className="w-24 accent-indigo-500"
                  />
                  <span className={`w-6 text-xs font-medium ${hasBg ? 'text-white' : 'text-gray-700 dark:text-gray-300'}`}>{minScore}</span>
                </div>
              </div>
            </div>

            {/* Signal list + detail side panel */}
            <div className="flex flex-1 overflow-hidden">
              <div className={`flex-1 overflow-y-auto p-4 ${selectedSignal ? 'w-1/2' : 'w-full'}`}>
                {loading ? (
                  <div className="flex h-40 items-center justify-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                  </div>
                ) : signals.length === 0 ? (
                  <div className={`py-16 text-center text-sm ${hasBg ? 'text-white/50' : 'text-gray-400'}`}>
                    Keine Signale gefunden
                  </div>
                ) : (
                  <>
                    <div className="grid gap-3">
                      {signals.map(s => (
                        <button
                          key={s.id}
                          onClick={() => openSignalDetail(s.id)}
                          className={`group w-full rounded-xl border p-4 text-left transition-all hover:scale-[1.005] ${
                            selectedSignal?.id === s.id
                              ? hasBg ? 'border-white/30 bg-white/20 backdrop-blur-xl' : 'border-indigo-300 bg-indigo-50/50 dark:border-indigo-700 dark:bg-indigo-950/30'
                              : hasBg ? 'border-white/10 bg-black/30 backdrop-blur-lg hover:bg-black/40' : 'border-gray-200 bg-white/70 hover:bg-white dark:border-gray-700 dark:bg-gray-900/50 dark:hover:bg-gray-900/70'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            {s.thumbnail_url && (
                              <img
                                src={s.thumbnail_url}
                                alt=""
                                className="h-16 w-24 shrink-0 rounded-lg object-cover"
                                loading="lazy"
                              />
                            )}
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <TypeBadge type={s.type} hasBg={hasBg} />
                                <ScoreBadge score={s.total_score} />
                              </div>
                              <h3 className={`mt-1 text-sm font-semibold leading-snug ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
                                {s.title}
                              </h3>
                              {s.description && (
                                <p className={`mt-1 line-clamp-2 text-xs leading-relaxed ${hasBg ? 'text-white/60' : 'text-gray-500 dark:text-gray-400'}`}>
                                  {s.description}
                                </p>
                              )}
                              <div className={`mt-2 flex flex-wrap items-center gap-2 text-[11px] ${hasBg ? 'text-white/50' : 'text-gray-400 dark:text-gray-500'}`}>
                                {s.source_name && <span>{s.source_name}</span>}
                                {s.published_at && <span>{new Date(s.published_at).toLocaleDateString('de-CH')}</span>}
                                {s.topic_name && (
                                  <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-white/10 text-white/70' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
                                    {s.topic_name}
                                  </span>
                                )}
                                {s.relevant_role && (
                                  <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-purple-500/20 text-purple-200' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'}`}>
                                    {s.relevant_role}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>

                    {/* Pagination */}
                    {totalPages > 1 && (
                      <div className="mt-4 flex items-center justify-center gap-2">
                        <button
                          disabled={currentPage <= 1}
                          onClick={() => setSignalOffset(Math.max(0, signalOffset - LIMIT))}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
                            hasBg ? 'bg-white/10 text-white hover:bg-white/20' : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300'
                          }`}
                        >
                          Zurück
                        </button>
                        <span className={`text-xs ${hasBg ? 'text-white/60' : 'text-gray-500'}`}>
                          Seite {currentPage} von {totalPages}
                        </span>
                        <button
                          disabled={currentPage >= totalPages}
                          onClick={() => setSignalOffset(signalOffset + LIMIT)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
                            hasBg ? 'bg-white/10 text-white hover:bg-white/20' : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300'
                          }`}
                        >
                          Weiter
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Detail panel */}
              {selectedSignal && (
                <div className={`w-1/2 overflow-y-auto border-l p-5 ${hasBg ? 'border-white/10 bg-black/30 backdrop-blur-xl' : 'border-gray-200 bg-white/80 dark:border-gray-700 dark:bg-gray-900/60'}`}>
                  {loadingDetail ? (
                    <div className="flex h-40 items-center justify-center">
                      <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <TypeBadge type={selectedSignal.type} hasBg={hasBg} />
                          <ScoreBadge score={selectedSignal.total_score} />
                        </div>
                        <button
                          onClick={() => setSelectedSignal(null)}
                          className={`rounded-lg p-1 transition-colors ${hasBg ? 'text-white/60 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
                        >
                          <CloseIcon className="h-4 w-4" />
                        </button>
                      </div>

                      <h2 className={`mt-3 text-lg font-bold leading-snug ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
                        {selectedSignal.title}
                      </h2>

                      <div className={`mt-2 flex flex-wrap items-center gap-3 text-xs ${hasBg ? 'text-white/50' : 'text-gray-500 dark:text-gray-400'}`}>
                        {selectedSignal.source_name && <span>{selectedSignal.source_name}</span>}
                        {selectedSignal.published_at && <span>{new Date(selectedSignal.published_at).toLocaleString('de-CH')}</span>}
                        {selectedSignal.topic_name && <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-white/10' : 'bg-gray-100 dark:bg-gray-800'}`}>{selectedSignal.topic_name}</span>}
                        {selectedSignal.relevant_role && <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-purple-500/20 text-purple-200' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'}`}>{selectedSignal.relevant_role}</span>}
                      </div>

                      {selectedSignal.ai_reason && (
                        <div className={`mt-3 rounded-lg border p-3 text-xs leading-relaxed ${hasBg ? 'border-amber-500/20 bg-amber-500/10 text-amber-200' : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300'}`}>
                          <span className="font-semibold">KI-Bewertung: </span>
                          {selectedSignal.ai_reason}
                        </div>
                      )}

                      {selectedSignal.url && (
                        <a
                          href={selectedSignal.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-indigo-500 hover:text-indigo-400"
                        >
                          <LinkIcon className="h-3.5 w-3.5" />
                          Original öffnen
                        </a>
                      )}

                      {selectedSignal.type === 'youtube' && selectedSignal.url && (
                        <div className="mt-4 aspect-video w-full overflow-hidden rounded-xl">
                          <iframe
                            src={getYouTubeEmbedUrl(selectedSignal.url)}
                            className="h-full w-full"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                          />
                        </div>
                      )}

                      {selectedSignal.full_content && (
                        <div className={`mt-4 whitespace-pre-wrap rounded-xl border p-4 text-sm leading-relaxed ${hasBg ? 'border-white/10 bg-white/5 text-white/80' : 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800/50 dark:text-gray-300'}`}>
                          {selectedSignal.full_content.length > 3000
                            ? selectedSignal.full_content.slice(0, 3000) + '…'
                            : selectedSignal.full_content
                          }
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Briefings Tab ── */}
        {tab === 'briefings' && (
          <div className="flex flex-1 overflow-hidden">
            <div className={`flex-1 overflow-y-auto p-4 ${selectedBriefing ? 'w-1/2' : 'w-full'}`}>
              {loading ? (
                <div className="flex h-40 items-center justify-center">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                </div>
              ) : briefings.length === 0 ? (
                <div className={`py-16 text-center text-sm ${hasBg ? 'text-white/50' : 'text-gray-400'}`}>
                  Keine Briefings vorhanden
                </div>
              ) : (
                <div className="grid gap-3">
                  {briefings.map(b => (
                    <button
                      key={b.id}
                      onClick={() => openBriefingDetail(b.id)}
                      className={`w-full rounded-xl border p-4 text-left transition-all hover:scale-[1.005] ${
                        selectedBriefing?.id === b.id
                          ? hasBg ? 'border-white/30 bg-white/20 backdrop-blur-xl' : 'border-indigo-300 bg-indigo-50/50 dark:border-indigo-700 dark:bg-indigo-950/30'
                          : hasBg ? 'border-white/10 bg-black/30 backdrop-blur-lg hover:bg-black/40' : 'border-gray-200 bg-white/70 hover:bg-white dark:border-gray-700 dark:bg-gray-900/50 dark:hover:bg-gray-900/70'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <h3 className={`font-semibold ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
                          {b.briefing_date ? new Date(b.briefing_date).toLocaleDateString('de-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : `Briefing #${b.id}`}
                        </h3>
                        {b.avg_score != null && <ScoreBadge score={b.avg_score} />}
                      </div>
                      <div className={`mt-1 flex items-center gap-3 text-xs ${hasBg ? 'text-white/50' : 'text-gray-500 dark:text-gray-400'}`}>
                        {b.signal_count != null && <span>{b.signal_count} Signale</span>}
                        {b.high_score_count != null && <span>{b.high_score_count} High-Score</span>}
                        {b.signal_density && <span>{b.signal_density}</span>}
                      </div>
                      {b.top_keywords && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {b.top_keywords.split(',').slice(0, 6).map((kw, i) => (
                            <span
                              key={i}
                              className={`rounded-full px-2 py-0.5 text-[10px] ${hasBg ? 'bg-white/10 text-white/60' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'}`}
                            >
                              {kw.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selectedBriefing && (
              <div className={`w-1/2 overflow-y-auto border-l p-5 ${hasBg ? 'border-white/10 bg-black/30 backdrop-blur-xl' : 'border-gray-200 bg-white/80 dark:border-gray-700 dark:bg-gray-900/60'}`}>
                <div className="flex items-center justify-between">
                  <h2 className={`text-lg font-bold ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
                    {selectedBriefing.briefing_date
                      ? new Date(selectedBriefing.briefing_date).toLocaleDateString('de-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
                      : `Briefing #${selectedBriefing.id}`}
                  </h2>
                  <button
                    onClick={() => setSelectedBriefing(null)}
                    className={`rounded-lg p-1 transition-colors ${hasBg ? 'text-white/60 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
                  >
                    <CloseIcon className="h-4 w-4" />
                  </button>
                </div>

                {selectedBriefing.audio_url && (
                  <div className={`mt-3 rounded-lg border p-3 ${hasBg ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50'}`}>
                    <span className={`text-xs font-medium ${hasBg ? 'text-white/70' : 'text-gray-600 dark:text-gray-400'}`}>Podcast-Briefing</span>
                    <audio src={selectedBriefing.audio_url} controls className="mt-1 w-full" />
                  </div>
                )}

                {selectedBriefing.briefing_html ? (
                  <div
                    className={`mt-4 prose prose-sm max-w-none ${hasBg ? 'prose-invert text-white/80' : 'dark:prose-invert'}`}
                    dangerouslySetInnerHTML={{ __html: selectedBriefing.briefing_html }}
                  />
                ) : selectedBriefing.briefing_text ? (
                  <div className={`mt-4 whitespace-pre-wrap text-sm leading-relaxed ${hasBg ? 'text-white/80' : 'text-gray-700 dark:text-gray-300'}`}>
                    {selectedBriefing.briefing_text}
                  </div>
                ) : (
                  <p className={`mt-4 text-sm ${hasBg ? 'text-white/40' : 'text-gray-400'}`}>Kein Inhalt verfügbar</p>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Deep Dives Tab ── */}
        {tab === 'deep-dives' && (
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className={`border-b px-6 py-3 backdrop-blur-sm ${hasBg ? 'border-white/10 bg-black/25' : 'border-gray-100 bg-white/40 dark:border-gray-800 dark:bg-gray-900/40'}`}>
              <select
                value={ddPersonaFilter}
                onChange={e => setDdPersonaFilter(e.target.value)}
                className={`rounded-lg border px-3 py-1.5 text-sm ${
                  hasBg
                    ? 'border-white/20 bg-white/10 text-white'
                    : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
                }`}
              >
                <option value="">Alle Personas</option>
                {personas.map(p => <option key={p.id} value={p.persona_name}>{p.persona_name}</option>)}
              </select>
            </div>

            <div className="flex flex-1 overflow-hidden">
              <div className={`flex-1 overflow-y-auto p-4 ${selectedDeepDive ? 'w-1/2' : 'w-full'}`}>
                {loading ? (
                  <div className="flex h-40 items-center justify-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                  </div>
                ) : deepDives.length === 0 ? (
                  <div className={`py-16 text-center text-sm ${hasBg ? 'text-white/50' : 'text-gray-400'}`}>
                    Keine Deep Dives vorhanden
                  </div>
                ) : (
                  <div className="grid gap-3">
                    {deepDives.map(dd => (
                      <button
                        key={dd.id}
                        onClick={() => openDeepDiveDetail(dd.id)}
                        className={`w-full rounded-xl border p-4 text-left transition-all hover:scale-[1.005] ${
                          selectedDeepDive?.id === dd.id
                            ? hasBg ? 'border-white/30 bg-white/20 backdrop-blur-xl' : 'border-indigo-300 bg-indigo-50/50 dark:border-indigo-700 dark:bg-indigo-950/30'
                            : hasBg ? 'border-white/10 bg-black/30 backdrop-blur-lg hover:bg-black/40' : 'border-gray-200 bg-white/70 hover:bg-white dark:border-gray-700 dark:bg-gray-900/50 dark:hover:bg-gray-900/70'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${hasBg ? 'bg-purple-500/20 text-purple-200' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'}`}>
                            {dd.persona_name}
                          </span>
                          {dd.createdAt && (
                            <span className={`text-xs ${hasBg ? 'text-white/40' : 'text-gray-400'}`}>
                              {new Date(dd.createdAt).toLocaleDateString('de-CH')}
                            </span>
                          )}
                        </div>
                        {dd.preview && (
                          <p className={`mt-2 line-clamp-3 text-sm leading-relaxed ${hasBg ? 'text-white/60' : 'text-gray-600 dark:text-gray-400'}`}>
                            {dd.preview}
                          </p>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {selectedDeepDive && (
                <div className={`w-1/2 overflow-y-auto border-l p-5 ${hasBg ? 'border-white/10 bg-black/30 backdrop-blur-xl' : 'border-gray-200 bg-white/80 dark:border-gray-700 dark:bg-gray-900/60'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${hasBg ? 'bg-purple-500/20 text-purple-200' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'}`}>
                        {selectedDeepDive.persona_name}
                      </span>
                      {selectedDeepDive.createdAt && (
                        <span className={`text-xs ${hasBg ? 'text-white/40' : 'text-gray-400'}`}>
                          {new Date(selectedDeepDive.createdAt).toLocaleDateString('de-CH')}
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => setSelectedDeepDive(null)}
                      className={`rounded-lg p-1 transition-colors ${hasBg ? 'text-white/60 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
                    >
                      <CloseIcon className="h-4 w-4" />
                    </button>
                  </div>
                  <div className={`mt-4 whitespace-pre-wrap text-sm leading-relaxed ${hasBg ? 'text-white/80' : 'text-gray-700 dark:text-gray-300'}`}>
                    {selectedDeepDive.last_synthesis || 'Kein Inhalt verfügbar'}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={bgUrl}
        onSelect={handleBgSelect}
      />
    </div>
  );
}

// ── Helper Components ──────────────────────────────

function TypeBadge({ type, hasBg }: { type: string | null; hasBg: boolean }) {
  const config: Record<string, { bg: string; text: string }> = {
    rss: { bg: hasBg ? 'bg-orange-500/20' : 'bg-orange-100 dark:bg-orange-900/30', text: hasBg ? 'text-orange-200' : 'text-orange-700 dark:text-orange-300' },
    youtube: { bg: hasBg ? 'bg-red-500/20' : 'bg-red-100 dark:bg-red-900/30', text: hasBg ? 'text-red-200' : 'text-red-700 dark:text-red-300' },
    web: { bg: hasBg ? 'bg-blue-500/20' : 'bg-blue-100 dark:bg-blue-900/30', text: hasBg ? 'text-blue-200' : 'text-blue-700 dark:text-blue-300' },
  };
  const c = config[type || ''] || config.web;
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${c.bg} ${c.text}`}>
      {type || 'web'}
    </span>
  );
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return null;
  const color = score >= 8
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
    : score >= 6
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
      : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400';
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${color}`}>
      {typeof score === 'number' ? score.toFixed(1) : score}
    </span>
  );
}

function getYouTubeEmbedUrl(url: string): string {
  const match = url.match(/(?:v=|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})/);
  return match ? `https://www.youtube.com/embed/${match[1]}` : url;
}

// ── Icons ────────────────────────────────────────────

function ImageIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
    </svg>
  );
}

function LinkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
    </svg>
  );
}
