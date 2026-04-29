import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import Markdown from 'react-markdown';
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
  top_keywords: string[] | string | null;
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

interface Persona { id: number; persona_name: string; description: string | null; }
interface Topic { id: number; topic_name: string; relevance_weight: number | null; category: string | null; keywords: string | null; strategic_why: string | null; }
interface Stats { total: number; high_score: number; medium_score: number; low_score: number; avg_score: number; today: number; this_week: number; sources: number; rss_count: number; youtube_count: number; web_count: number; }

type TabId = 'signals' | 'briefings' | 'deep-dives';
type TypeFilter = '' | 'rss' | 'youtube';
type TimeRange = '' | 'today' | 'week' | '2weeks';
type ScoreFilter = 0 | 7 | 8 | 9;

interface SavedFilters { typeFilter: TypeFilter; timeRange: TimeRange; minScore: ScoreFilter; topicFilter: string; personaFilter: string; }

const FILTER_STORAGE_KEY = 'signale_filters';
const LIMIT = 20;

function loadSavedFilters(): SavedFilters {
  try { const raw = localStorage.getItem(FILTER_STORAGE_KEY); if (raw) return JSON.parse(raw); } catch { /* ignore */ }
  return { typeFilter: '', timeRange: '', minScore: 0, topicFilter: '', personaFilter: '' };
}
function saveFilters(f: SavedFilters) { localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(f)); }

function relativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'gerade eben';
  if (mins < 60) return `vor ${mins} Min.`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `vor ${days} ${days === 1 ? 'Tag' : 'Tagen'}`;
  return new Date(isoDate).toLocaleDateString('de-CH', { day: 'numeric', month: 'short', year: 'numeric' });
}

function getKeywords(kw: string[] | string | null): string[] {
  if (!kw) return [];
  if (Array.isArray(kw)) return kw;
  return kw.split(',').map(s => s.trim()).filter(Boolean);
}

function getYouTubeEmbedUrl(url: string): string {
  const match = url.match(/(?:v=|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})/);
  return match ? `https://www.youtube.com/embed/${match[1]}?autoplay=1` : url;
}

// ── Component ────────────────────────────────────────

export function SignalePage() {
  const [tab, setTab] = useState<TabId>('signals');
  const [stats, setStats] = useState<Stats | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);

  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalTotal, setSignalTotal] = useState(0);
  const [loadingSignals, setLoadingSignals] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [initialLoad, setInitialLoad] = useState(true);
  const loadingRef = useRef(false);

  const saved = useMemo(loadSavedFilters, []);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(saved.typeFilter);
  const [timeRange, setTimeRange] = useState<TimeRange>(saved.timeRange);
  const [minScore, setMinScore] = useState<ScoreFilter>(saved.minScore);
  const [topicFilter, setTopicFilter] = useState(saved.topicFilter);
  const [personaFilter, setPersonaFilter] = useState(saved.personaFilter);
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout>>();

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedSignal, setExpandedSignal] = useState<Signal | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // YouTube inline player
  const [playingVideoId, setPlayingVideoId] = useState<number | null>(null);

  const [briefings, setBriefings] = useState<Briefing[]>([]);
  const [selectedBriefing, setSelectedBriefing] = useState<Briefing | null>(null);
  const [loadingBriefings, setLoadingBriefings] = useState(false);

  const [deepDives, setDeepDives] = useState<DeepDive[]>([]);
  const [selectedDeepDive, setSelectedDeepDive] = useState<DeepDive | null>(null);
  const [ddPersonaFilter, setDdPersonaFilter] = useState('');
  const [loadingDeepDives, setLoadingDeepDives] = useState(false);

  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { saveFilters({ typeFilter, timeRange, minScore, topicFilter, personaFilter }); }, [typeFilter, timeRange, minScore, topicFilter, personaFilter]);

  useEffect(() => {
    Promise.all([
      api.get<Stats>('/api/signa/stats').catch(() => null),
      api.get<Persona[]>('/api/signa/personas').catch(() => []),
      api.get<Topic[]>('/api/signa/topics').catch(() => []),
      api.get<{ signale_background_url: string | null }>('/api/settings').then(s => s.signale_background_url).catch(() => null),
    ]).then(([s, p, t, bg]) => { if (s) setStats(s); setPersonas(p as Persona[]); setTopics(t as Topic[]); if (bg) setBgUrl(bg); });
  }, []);

  useEffect(() => { clearTimeout(searchTimer.current); searchTimer.current = setTimeout(() => setDebouncedSearch(searchTerm), 400); return () => clearTimeout(searchTimer.current); }, [searchTerm]);

  useEffect(() => { setSignals([]); setHasMore(true); setExpandedId(null); setExpandedSignal(null); setPlayingVideoId(null); setInitialLoad(true); }, [typeFilter, timeRange, minScore, topicFilter, personaFilter, debouncedSearch]);

  const fetchSignals = useCallback(async (offset: number, append: boolean) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoadingSignals(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(LIMIT));
      params.set('offset', String(offset));
      params.set('status', 'relevant');
      if (typeFilter) params.set('type', typeFilter);
      if (minScore > 0) params.set('min_score', String(minScore));
      if (topicFilter) params.set('topic', topicFilter);
      if (personaFilter) params.set('persona', personaFilter);
      if (timeRange) params.set('since', timeRange);
      if (debouncedSearch) params.set('search', debouncedSearch);
      const data = await api.get<SignalListResponse>(`/api/signa/signals?${params}`);
      if (append) { setSignals(prev => [...prev, ...data.signals]); } else { setSignals(data.signals); }
      setSignalTotal(data.total);
      setHasMore(offset + data.signals.length < data.total);
    } catch { /* handled */ }
    finally { loadingRef.current = false; setLoadingSignals(false); setInitialLoad(false); }
  }, [typeFilter, minScore, topicFilter, personaFilter, timeRange, debouncedSearch]);

  useEffect(() => { if (tab === 'signals' && initialLoad) fetchSignals(0, false); }, [tab, initialLoad, fetchSignals]);

  useEffect(() => {
    if (tab !== 'signals') return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loadingRef.current && !initialLoad) {
        fetchSignals(signals.length, true);
      }
    }, { rootMargin: '300px' });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [tab, hasMore, initialLoad, signals.length, fetchSignals]);

  const toggleExpand = async (id: number) => {
    if (expandedId === id) { setExpandedId(null); setExpandedSignal(null); return; }
    setExpandedId(id);
    setLoadingDetail(true);
    try { const data = await api.get<Signal>(`/api/signa/signals/${id}`); setExpandedSignal(data); } catch { /* handled */ }
    finally { setLoadingDetail(false); }
  };

  const fetchBriefings = useCallback(async () => {
    setLoadingBriefings(true);
    try { setBriefings(await api.get<Briefing[]>('/api/signa/briefings?limit=50')); } catch { /* handled */ }
    finally { setLoadingBriefings(false); }
  }, []);
  useEffect(() => { if (tab === 'briefings') fetchBriefings(); }, [tab, fetchBriefings]);

  const fetchDeepDives = useCallback(async () => {
    setLoadingDeepDives(true);
    try { const params = ddPersonaFilter ? `?persona=${encodeURIComponent(ddPersonaFilter)}&limit=50` : '?limit=50'; setDeepDives(await api.get<DeepDive[]>(`/api/signa/deep-dives${params}`)); } catch { /* handled */ }
    finally { setLoadingDeepDives(false); }
  }, [ddPersonaFilter]);
  useEffect(() => { if (tab === 'deep-dives') fetchDeepDives(); }, [tab, fetchDeepDives]);

  const openBriefingDetail = async (id: number) => { try { setSelectedBriefing(await api.get<Briefing>(`/api/signa/briefings/${id}`)); } catch { /* handled */ } };
  const openDeepDiveDetail = async (id: number) => { try { setSelectedDeepDive(await api.get<DeepDive>(`/api/signa/deep-dives/${id}`)); } catch { /* handled */ } };

  const handleBgSelect = async (url: string | null) => { await api.patch('/api/settings', { signale_background_url: url }); setBgUrl(url); };

  const hasBg = !!bgUrl;
  const isGradient = bgUrl?.startsWith('gradient:') ?? false;
  const bgStyle = isGradient ? { background: bgUrl!.slice('gradient:'.length) } : hasBg ? { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined;

  const glass = hasBg ? 'border-white/10 bg-black/35 backdrop-blur-xl' : 'border-gray-200/60 bg-white/70 backdrop-blur-xl dark:border-gray-800 dark:bg-gray-900/60';
  const cardGlass = hasBg ? 'border-white/10 bg-white/[0.06] backdrop-blur-xl' : 'border-gray-200/70 bg-white/80 backdrop-blur-lg dark:border-white/10 dark:bg-white/[0.06]';
  const cardExpandedGlass = hasBg ? 'border-white/15 bg-white/[0.08] backdrop-blur-xl' : 'border-indigo-200 bg-white/90 backdrop-blur-xl dark:border-indigo-500/30 dark:bg-white/[0.08]';
  const textPrimary = hasBg ? 'text-white' : 'text-gray-900 dark:text-white';
  const textSecondary = hasBg ? 'text-white/70' : 'text-gray-600 dark:text-gray-400';
  const textMuted = hasBg ? 'text-white/40' : 'text-gray-400 dark:text-gray-500';

  return (
    <div className="relative flex h-full flex-col" style={!hasBg ? undefined : bgStyle}>
      {!hasBg && <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-indigo-50/30 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950/20" />}
      {hasBg && !isGradient && <div className="absolute inset-0 bg-black/30 dark:bg-black/45" />}
      {isGradient && <div className="absolute inset-0 bg-black/10 dark:bg-black/25" />}

      <div className="relative z-10 flex h-full flex-col">
        {/* Header */}
        <div className={`border-b px-6 py-4 ${glass}`}>
          <div className="mx-auto flex max-w-3xl items-center justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className={`text-xl font-bold ${textPrimary}`}>Signale</h1>
                {stats && <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">{stats.total.toLocaleString('de-CH')}</span>}
              </div>
              {stats && (
                <div className={`mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs ${textSecondary}`}>
                  <span className="flex items-center gap-1"><span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />{stats.today} heute</span>
                  <span>{stats.this_week} diese Woche</span>
                  <span>{stats.high_score} Must-Read</span>
                  <span>&#216; {stats.avg_score}</span>
                  <span>{stats.sources} Quellen</span>
                </div>
              )}
            </div>
            <button onClick={() => setBgPickerOpen(true)} className={`rounded-xl p-2.5 transition-colors ${hasBg ? 'text-white/60 hover:bg-white/10 hover:text-white' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`} title="Hintergrund ändern">
              <ImageIcon className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className={`border-b px-6 ${glass}`}>
          <div className="mx-auto flex max-w-3xl items-center gap-1">
            {([{ id: 'signals' as TabId, label: 'Signale' }, { id: 'briefings' as TabId, label: 'Briefings' }, { id: 'deep-dives' as TabId, label: 'Deep Dives' }]).map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} className={`relative px-4 py-3 text-sm font-medium transition-colors ${tab === t.id ? (hasBg ? 'text-white' : 'text-indigo-600 dark:text-indigo-400') : (hasBg ? 'text-white/50 hover:text-white/80' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300')}`}>
                {t.label}
                {tab === t.id && <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-indigo-500" />}
              </button>
            ))}
          </div>
        </div>

        {/* ── Signals Tab ── */}
        {tab === 'signals' && (
          <div className="flex-1 overflow-y-auto">
            <div className={`sticky top-0 z-20 border-b px-6 py-3 ${glass}`}>
              <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-2">
                <PillGroup options={[{ value: '', label: 'Alle' }, { value: 'today', label: 'Heute' }, { value: 'week', label: 'Woche' }, { value: '2weeks', label: '2 Wochen' }]} value={timeRange} onChange={v => setTimeRange(v as TimeRange)} hasBg={hasBg} />
                <Sep hasBg={hasBg} />
                <PillGroup options={[{ value: '', label: 'Alle' }, { value: 'rss', label: 'Artikel' }, { value: 'youtube', label: 'Videos' }]} value={typeFilter} onChange={v => setTypeFilter(v as TypeFilter)} hasBg={hasBg} />
                <Sep hasBg={hasBg} />
                <PillGroup options={[{ value: '0', label: 'Alle' }, { value: '7', label: '\u2265 7' }, { value: '8', label: '\u2265 8' }, { value: '9', label: 'MUST-READ', accent: true }]} value={String(minScore)} onChange={v => setMinScore(Number(v) as ScoreFilter)} hasBg={hasBg} />
                <Sep hasBg={hasBg} />
                <select value={topicFilter} onChange={e => setTopicFilter(e.target.value)} className={`rounded-lg border px-2.5 py-1.5 text-xs ${hasBg ? 'border-white/15 bg-white/10 text-white' : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'}`}>
                  <option value="">Topic</option>
                  {topics.map(t => <option key={t.id} value={t.topic_name}>{t.topic_name}</option>)}
                </select>
                <select value={personaFilter} onChange={e => setPersonaFilter(e.target.value)} className={`rounded-lg border px-2.5 py-1.5 text-xs ${hasBg ? 'border-white/15 bg-white/10 text-white' : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'}`}>
                  <option value="">Persona</option>
                  {personas.map(p => <option key={p.id} value={p.persona_name}>{p.persona_name}</option>)}
                </select>
                <div className="ml-auto">
                  <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="Suchen..." className={`w-48 rounded-lg border px-3 py-1.5 text-xs outline-none transition-colors ${hasBg ? 'border-white/15 bg-white/10 text-white placeholder:text-white/40 focus:border-white/30' : 'border-gray-200 bg-white text-gray-900 placeholder:text-gray-400 focus:border-indigo-400 dark:border-gray-700 dark:bg-gray-800 dark:text-white'}`} />
                </div>
              </div>
            </div>

            <div className="mx-auto max-w-3xl px-6 py-6">
              {initialLoad && loadingSignals ? (
                <div className="grid gap-5">{Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} hasBg={hasBg} />)}</div>
              ) : signals.length === 0 && !loadingSignals ? (
                <div className={`py-20 text-center ${textMuted}`}>
                  <SignalIcon className="mx-auto mb-3 h-10 w-10 opacity-40" />
                  <p className="text-sm">Keine Signale gefunden</p>
                  <p className="mt-1 text-xs">Passe die Filter an oder versuche eine andere Suche</p>
                </div>
              ) : (
                <>
                  <div className="grid gap-5">
                    {signals.map(s => {
                      const isYT = s.type === 'youtube';
                      const isExpanded = expandedId === s.id;
                      const isPlaying = playingVideoId === s.id;
                      const summaryText = isYT ? s.ai_reason : (s.ai_reason || s.description);

                      // YouTube signals: no expand, just play inline
                      if (isYT) {
                        return (
                          <div key={s.id} className={`rounded-2xl border shadow-sm transition-all ${cardGlass}`}>
                            {/* Video area */}
                            {isPlaying && s.url ? (
                              <div className="aspect-video w-full overflow-hidden rounded-t-2xl">
                                <iframe src={getYouTubeEmbedUrl(s.url)} className="h-full w-full" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />
                              </div>
                            ) : s.thumbnail_url ? (
                              <div className="relative cursor-pointer overflow-hidden rounded-t-2xl" onClick={() => setPlayingVideoId(s.id)}>
                                <img src={s.thumbnail_url} alt="" className="aspect-video w-full object-cover" loading="lazy" />
                                <div className="absolute inset-0 flex items-center justify-center bg-black/20 transition-colors hover:bg-black/30">
                                  <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-600/90 shadow-lg transition-transform hover:scale-110">
                                    <PlayIcon className="h-6 w-6 text-white" />
                                  </div>
                                </div>
                              </div>
                            ) : null}

                            <div className="p-4">
                              <div className="mb-2 flex items-start justify-between gap-2">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  {s.relevant_role && <span className="rounded-full bg-purple-500/15 px-2.5 py-0.5 text-[11px] font-medium text-purple-600 dark:text-purple-300">{s.relevant_role}</span>}
                                  {s.source_name && <span className={`text-[11px] ${textMuted}`}>{s.source_name}</span>}
                                </div>
                                <ScoreBadge score={s.total_score} />
                              </div>
                              <h3 className={`text-sm font-semibold leading-snug ${textPrimary}`}>{s.title}</h3>
                              {summaryText && <p className={`mt-2 text-sm leading-relaxed ${textSecondary}`}>{summaryText}</p>}
                              <div className={`mt-3 flex items-center gap-2 text-[11px] ${textMuted}`}>
                                {s.published_at && <span>{relativeTime(s.published_at)}</span>}
                                {s.topic_name && <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-white/8' : 'bg-gray-100 dark:bg-gray-800'}`}>{s.topic_name}</span>}
                                <TypeBadge type={s.type} />
                              </div>
                            </div>
                          </div>
                        );
                      }

                      // RSS / Web signals: expand for full content
                      return (
                        <div key={s.id} className={`rounded-2xl border shadow-sm transition-all ${isExpanded ? cardExpandedGlass : `${cardGlass} cursor-pointer`}`} onClick={() => !isExpanded && toggleExpand(s.id)}>
                          <div className="p-5">
                            <div className="mb-2 flex items-start justify-between gap-2">
                              <div className="flex flex-wrap items-center gap-1.5">
                                {s.relevant_role && <span className="rounded-full bg-purple-500/15 px-2.5 py-0.5 text-[11px] font-medium text-purple-600 dark:text-purple-300">{s.relevant_role}</span>}
                                {s.source_name && <span className={`text-[11px] ${textMuted}`}>{s.source_name}</span>}
                              </div>
                              <div className="flex shrink-0 items-center gap-1.5">
                                <ScoreBadge score={s.total_score} />
                                {isExpanded && (
                                  <button onClick={e => { e.stopPropagation(); toggleExpand(s.id); }} className={`rounded-lg p-1 transition-colors ${hasBg ? 'text-white/50 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}>
                                    <CloseIcon className="h-4 w-4" />
                                  </button>
                                )}
                              </div>
                            </div>

                            <h3 className={`text-sm font-semibold leading-snug ${textPrimary}`}>{s.title}</h3>
                            {summaryText && <p className={`mt-2 text-sm leading-relaxed ${textSecondary}`}>{summaryText}</p>}

                            {!isExpanded && (
                              <div className={`mt-3 flex flex-wrap items-center gap-2 text-[11px] ${textMuted}`}>
                                {s.published_at && <span>{relativeTime(s.published_at)}</span>}
                                {s.topic_name && <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-white/8' : 'bg-gray-100 dark:bg-gray-800'}`}>{s.topic_name}</span>}
                                <TypeBadge type={s.type} />
                              </div>
                            )}
                          </div>

                          {isExpanded && (
                            <div className="border-t border-inherit px-5 pb-5 pt-4">
                              {loadingDetail ? (
                                <div className="flex h-20 items-center justify-center"><div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" /></div>
                              ) : (
                                <>
                                  <div className={`mb-3 flex flex-wrap items-center gap-3 text-xs ${textMuted}`}>
                                    {expandedSignal?.published_at && <span>{new Date(expandedSignal.published_at).toLocaleString('de-CH')}</span>}
                                    {expandedSignal?.topic_name && <span className={`rounded-full px-2 py-0.5 ${hasBg ? 'bg-white/8' : 'bg-gray-100 dark:bg-gray-800'}`}>{expandedSignal.topic_name}</span>}
                                    <TypeBadge type={expandedSignal?.type ?? s.type} />
                                  </div>

                                  {expandedSignal?.full_content && (
                                    <ContentBlock content={expandedSignal.full_content} hasBg={hasBg} />
                                  )}

                                  <div className="flex items-center gap-3">
                                    {expandedSignal?.url && (
                                      <a href={expandedSignal.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-indigo-500/15 px-4 py-2 text-xs font-semibold text-indigo-600 transition-colors hover:bg-indigo-500/25 dark:text-indigo-400">
                                        <LinkIcon className="h-3.5 w-3.5" />Artikel lesen
                                      </a>
                                    )}
                                  </div>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div ref={sentinelRef} className="h-1" />
                  {loadingSignals && !initialLoad && (
                    <div className="mt-4 grid gap-5">{Array.from({ length: 2 }).map((_, i) => <SkeletonCard key={`more-${i}`} hasBg={hasBg} />)}</div>
                  )}
                  {!hasMore && signals.length > 0 && <p className={`mt-6 pb-4 text-center text-xs ${textMuted}`}>Alle {signalTotal.toLocaleString('de-CH')} Signale geladen</p>}
                </>
              )}
            </div>
          </div>
        )}

        {/* ── Briefings Tab ── */}
        {tab === 'briefings' && (
          <div className="flex flex-1 overflow-hidden">
            <div className={`flex-1 overflow-y-auto p-6 ${selectedBriefing ? 'w-1/2' : 'w-full'}`}>
              {loadingBriefings ? (
                <div className="mx-auto max-w-3xl grid gap-4">{Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} hasBg={hasBg} />)}</div>
              ) : briefings.length === 0 ? (
                <div className={`py-16 text-center text-sm ${textMuted}`}>Keine Briefings vorhanden</div>
              ) : (
                <div className="mx-auto grid max-w-3xl gap-4">
                  {briefings.map(b => (
                    <button key={b.id} onClick={() => openBriefingDetail(b.id)} className={`w-full rounded-2xl border p-5 text-left shadow-sm transition-all ${selectedBriefing?.id === b.id ? cardExpandedGlass : cardGlass}`}>
                      <div className="flex items-center justify-between">
                        <h3 className={`font-semibold ${textPrimary}`}>{b.briefing_date ? new Date(b.briefing_date).toLocaleDateString('de-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : `Briefing #${b.id}`}</h3>
                        {b.avg_score != null && <ScoreBadge score={b.avg_score} />}
                      </div>
                      <div className={`mt-1.5 flex items-center gap-3 text-xs ${textSecondary}`}>
                        {b.signal_count != null && <span>{b.signal_count} Signale</span>}
                        {b.high_score_count != null && <span>{b.high_score_count} High-Score</span>}
                      </div>
                      {b.top_keywords && (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {getKeywords(b.top_keywords).slice(0, 6).map((kw, i) => (
                            <span key={i} className={`rounded-full px-2 py-0.5 text-[10px] ${hasBg ? 'bg-white/8 text-white/50' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'}`}>{kw}</span>
                          ))}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {selectedBriefing && (
              <div className={`w-1/2 overflow-y-auto border-l p-6 ${glass}`}>
                <div className="flex items-center justify-between">
                  <h2 className={`text-lg font-bold ${textPrimary}`}>{selectedBriefing.briefing_date ? new Date(selectedBriefing.briefing_date).toLocaleDateString('de-CH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : `Briefing #${selectedBriefing.id}`}</h2>
                  <div className="flex items-center gap-1">
                    <CopyButton text={selectedBriefing.briefing_text || ''} hasBg={hasBg} />
                    <button onClick={() => setSelectedBriefing(null)} className={`rounded-lg p-1.5 transition-colors ${hasBg ? 'text-white/50 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}><CloseIcon className="h-4 w-4" /></button>
                  </div>
                </div>
                {selectedBriefing.audio_url && (
                  <div className={`mt-4 rounded-xl border p-3 ${hasBg ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50'}`}>
                    <audio src={selectedBriefing.audio_url} controls className="w-full" />
                  </div>
                )}
                {selectedBriefing.briefing_html ? (
                  <div className={`mt-4 prose prose-sm max-w-none ${hasBg ? 'prose-invert' : 'dark:prose-invert'}`} dangerouslySetInnerHTML={{ __html: selectedBriefing.briefing_html }} />
                ) : selectedBriefing.briefing_text ? (
                  <div className={`mt-4 whitespace-pre-wrap text-sm leading-relaxed ${textSecondary}`}>{selectedBriefing.briefing_text}</div>
                ) : (
                  <p className={`mt-4 text-sm ${textMuted}`}>Kein Inhalt verfügbar</p>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Deep Dives Tab ── */}
        {tab === 'deep-dives' && (
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className={`border-b px-6 py-3 ${glass}`}>
              <div className="mx-auto max-w-3xl">
                <select value={ddPersonaFilter} onChange={e => setDdPersonaFilter(e.target.value)} className={`rounded-lg border px-3 py-1.5 text-sm ${hasBg ? 'border-white/15 bg-white/10 text-white' : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'}`}>
                  <option value="">Alle Personas</option>
                  {personas.map(p => <option key={p.id} value={p.persona_name}>{p.persona_name}</option>)}
                </select>
              </div>
            </div>
            <div className="flex flex-1 overflow-hidden">
              <div className={`flex-1 overflow-y-auto p-6 ${selectedDeepDive ? 'w-1/2' : 'w-full'}`}>
                {loadingDeepDives ? (
                  <div className="mx-auto max-w-3xl grid gap-4">{Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} hasBg={hasBg} />)}</div>
                ) : deepDives.length === 0 ? (
                  <div className={`py-16 text-center text-sm ${textMuted}`}>Keine Deep Dives vorhanden</div>
                ) : (
                  <div className="mx-auto grid max-w-3xl gap-4">
                    {deepDives.map(dd => (
                      <button key={dd.id} onClick={() => openDeepDiveDetail(dd.id)} className={`w-full rounded-2xl border p-5 text-left shadow-sm transition-all ${selectedDeepDive?.id === dd.id ? cardExpandedGlass : cardGlass}`}>
                        <div className="flex items-center gap-2">
                          <span className="rounded-full bg-purple-500/15 px-2.5 py-0.5 text-[11px] font-medium text-purple-600 dark:text-purple-300">{dd.persona_name}</span>
                          {dd.createdAt && <span className={`text-xs ${textMuted}`}>{new Date(dd.createdAt).toLocaleDateString('de-CH')}</span>}
                        </div>
                        {dd.preview && <p className={`mt-2 text-sm leading-relaxed ${textSecondary}`}>{dd.preview}</p>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {selectedDeepDive && (
                <div className={`w-1/2 overflow-y-auto border-l p-6 ${glass}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-purple-500/15 px-2.5 py-0.5 text-xs font-medium text-purple-600 dark:text-purple-300">{selectedDeepDive.persona_name}</span>
                      {selectedDeepDive.createdAt && <span className={`text-xs ${textMuted}`}>{new Date(selectedDeepDive.createdAt).toLocaleDateString('de-CH')}</span>}
                    </div>
                    <div className="flex items-center gap-1">
                      <CopyButton text={selectedDeepDive.last_synthesis || ''} hasBg={hasBg} />
                      <button onClick={() => setSelectedDeepDive(null)} className={`rounded-lg p-1.5 transition-colors ${hasBg ? 'text-white/50 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}><CloseIcon className="h-4 w-4" /></button>
                    </div>
                  </div>
                  <div className={`mt-4 whitespace-pre-wrap text-sm leading-relaxed ${hasBg ? 'text-white/80' : 'text-gray-700 dark:text-gray-300'}`}>{selectedDeepDive.last_synthesis || 'Kein Inhalt verfügbar'}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <BackgroundPicker isOpen={bgPickerOpen} onClose={() => setBgPickerOpen(false)} currentUrl={bgUrl} onSelect={handleBgSelect} />
    </div>
  );
}

// ── Sub-Components ──────────────────────────────────

function CopyButton({ text, hasBg }: { text: string; hasBg: boolean }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text.replace(/<[^>]*>/g, ''));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={handleCopy} title="In Zwischenablage kopieren" className={`rounded-lg p-1.5 transition-colors ${copied ? 'text-emerald-500' : hasBg ? 'text-white/50 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}>
      {copied ? <CheckIcon className="h-4 w-4" /> : <ClipboardIcon className="h-4 w-4" />}
    </button>
  );
}

function ContentBlock({ content, hasBg }: { content: string; hasBg: boolean }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => { await navigator.clipboard.writeText(content.replace(/<[^>]*>/g, '')); setCopied(true); setTimeout(() => setCopied(false), 2000); };
  const isHtml = /<[a-z][\s\S]*>/i.test(content);
  return (
    <div className={`relative mb-4 rounded-xl border ${hasBg ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/40'}`}>
      <button onClick={handleCopy} title="In Zwischenablage kopieren" className={`absolute right-3 top-3 z-10 rounded-lg p-1.5 transition-colors ${copied ? 'text-emerald-500' : hasBg ? 'text-white/40 hover:bg-white/10' : 'text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'}`}>
        {copied ? <CheckIcon className="h-4 w-4" /> : <ClipboardIcon className="h-4 w-4" />}
      </button>
      <div className={`max-h-[40rem] overflow-y-auto p-5 pr-12 ${hasBg ? 'text-white/80' : 'text-gray-700 dark:text-gray-300'}`}>
        {isHtml ? (
          <div className="prose prose-sm max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: content }} />
        ) : (
          <Markdown className="prose prose-sm max-w-none dark:prose-invert">{content}</Markdown>
        )}
      </div>
    </div>
  );
}

function PillGroup({ options, value, onChange, hasBg }: { options: { value: string; label: string; accent?: boolean }[]; value: string; onChange: (v: string) => void; hasBg: boolean; }) {
  return (
    <div className="flex items-center gap-1">
      {options.map(opt => {
        const active = value === opt.value;
        const accent = opt.accent && active;
        return (
          <button key={opt.value} onClick={() => onChange(opt.value)} className={`rounded-full px-3 py-1 text-[11px] font-medium transition-all ${accent ? 'bg-red-500/90 text-white shadow-sm' : active ? (hasBg ? 'bg-white/20 text-white shadow-sm' : 'bg-indigo-500/15 text-indigo-600 shadow-sm dark:bg-indigo-500/20 dark:text-indigo-400') : (hasBg ? 'text-white/50 hover:bg-white/10' : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800')}`}>
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function Sep({ hasBg }: { hasBg: boolean }) { return <div className={`h-4 w-px ${hasBg ? 'bg-white/15' : 'bg-gray-200 dark:bg-gray-700'}`} />; }

function SkeletonCard({ hasBg }: { hasBg: boolean }) {
  return (
    <div className={`animate-pulse rounded-2xl border p-5 ${hasBg ? 'border-white/10 bg-white/5' : 'border-gray-200/70 bg-gray-100/50 dark:border-gray-800 dark:bg-gray-800/30'}`}>
      <div className="flex items-center gap-2"><div className={`h-4 w-24 rounded-full ${hasBg ? 'bg-white/10' : 'bg-gray-200 dark:bg-gray-700'}`} /><div className={`h-4 w-16 rounded-full ${hasBg ? 'bg-white/10' : 'bg-gray-200 dark:bg-gray-700'}`} /></div>
      <div className={`mt-3 h-4 w-3/4 rounded ${hasBg ? 'bg-white/10' : 'bg-gray-200 dark:bg-gray-700'}`} />
      <div className={`mt-2 h-3 w-full rounded ${hasBg ? 'bg-white/8' : 'bg-gray-200/70 dark:bg-gray-700/60'}`} />
      <div className={`mt-1.5 h-3 w-5/6 rounded ${hasBg ? 'bg-white/8' : 'bg-gray-200/70 dark:bg-gray-700/60'}`} />
      <div className={`mt-1.5 h-3 w-2/3 rounded ${hasBg ? 'bg-white/8' : 'bg-gray-200/70 dark:bg-gray-700/60'}`} />
    </div>
  );
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return null;
  const isMustRead = score >= 9;
  const isHigh = score >= 7;
  const color = isMustRead ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : isHigh ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400' : 'bg-gray-500/10 text-gray-500 dark:text-gray-400';
  return (
    <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${color}`}>
      {typeof score === 'number' ? score.toFixed(1) : score}
      {isMustRead && <span className="text-[9px] font-semibold uppercase tracking-wider">MUST-READ</span>}
    </span>
  );
}

function TypeBadge({ type }: { type: string | null }) {
  if (!type) return null;
  const cfg: Record<string, string> = { rss: 'bg-orange-500/10 text-orange-600 dark:text-orange-400', youtube: 'bg-red-500/10 text-red-600 dark:text-red-400', web: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' };
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${cfg[type] || cfg.web}`}>{type}</span>;
}

// ── Icons ──

function ImageIcon({ className }: { className?: string }) { return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" /></svg>; }
function CloseIcon({ className }: { className?: string }) { return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>; }
function LinkIcon({ className }: { className?: string }) { return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" /></svg>; }
function PlayIcon({ className }: { className?: string }) { return <svg className={className} fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>; }
function SignalIcon({ className }: { className?: string }) { return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.348 14.652a3.75 3.75 0 0 1 0-5.304m5.304 0a3.75 3.75 0 0 1 0 5.304m-7.425 2.121a6.75 6.75 0 0 1 0-9.546m9.546 0a6.75 6.75 0 0 1 0 9.546M5.106 18.894c-3.808-3.807-3.808-9.98 0-13.788m13.788 0c3.808 3.807 3.808 9.98 0 13.788M12 12h.008v.008H12V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" /></svg>; }
function ClipboardIcon({ className }: { className?: string }) { return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" /></svg>; }
function CheckIcon({ className }: { className?: string }) { return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" /></svg>; }
