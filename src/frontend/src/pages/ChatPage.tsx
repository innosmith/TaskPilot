import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, getToken } from '../api/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { TaskDetailDialog } from '../components/TaskDetailDialog';

interface LlmModel {
  id: string;
  name: string;
  type: 'local' | 'cloud';
  provider: string;
  capabilities: string[];
}

interface Conversation {
  id: string;
  title: string | null;
  model: string;
  mode: string;
  temperature: number;
  total_tokens: number;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
  message_count?: number;
  last_message_preview?: string | null;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tokens: number | null;
  cost_usd: number | null;
  reasoning_tokens?: number | null;
  thinking?: string | null;
  citations: unknown[] | null;
  attachments?: { name: string; type: string }[];
  created_at: string;
}

type ChatMode = 'chat' | 'web_search' | 'deep_research' | 'agent';

const MODES: { id: ChatMode; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'web_search', label: 'Websuche' },
  { id: 'deep_research', label: 'Deep Research' },
  { id: 'agent', label: 'Agent' },
];

const PROVIDER_ORDER = ['ollama', 'openai', 'anthropic', 'gemini', 'perplexity'];
const PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama (Lokal)',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  perplexity: 'Perplexity',
};

export function ChatPage() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [models, setModels] = useState<LlmModel[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [mode, setMode] = useState<ChatMode>('chat');
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [thinkingContent, setThinkingContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [showSidebar, setShowSidebar] = useState(true);
  const [modelOpen, setModelOpen] = useState(false);
  const [tempOpen, setTempOpen] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [expandedThinking, setExpandedThinking] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modelDropdownRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    try {
      const data = await api.get<{ items: Conversation[] }>('/api/chat/conversations');
      setConversations(data.items);
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    loadConversations();
    api.get<{ local: LlmModel[]; cloud: LlmModel[] }>('/api/models')
      .then(d => setModels([...d.local, ...d.cloud]))
      .catch(() => {});
    api.get<{ llm_default_model: string | null; llm_default_temperature: number | null }>('/api/settings/llm')
      .then(s => {
        if (s.llm_default_model) setSelectedModel(s.llm_default_model);
        if (s.llm_default_temperature !== null) setTemperature(s.llm_default_temperature);
      })
      .catch(() => {});
  }, [loadConversations]);

  useEffect(() => {
    if (!activeId) { setMessages([]); return; }
    api.get<{ messages: ChatMessage[]; mode?: string }>(`/api/chat/conversations/${activeId}`)
      .then(d => {
        setMessages(d.messages || []);
        if (d.mode) setMode(d.mode as ChatMode);
      })
      .catch(() => {});
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, thinkingContent]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) setModelOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const modelLabel = (id: string) => {
    const m = models.find(x => x.id === id);
    return m?.name || id.split('/').pop() || id;
  };

  const modelInfo = (id: string) => models.find(x => x.id === id);

  const filteredModels = () => {
    if (mode === 'deep_research') return models.filter(m => m.capabilities.includes('deep_research'));
    return models;
  };

  const groupedModels = () => {
    const source = filteredModels();
    const groups: { label: string; items: LlmModel[] }[] = [];
    for (const p of PROVIDER_ORDER) {
      const items = source.filter(m => m.provider === p);
      if (items.length > 0) groups.push({ label: PROVIDER_LABELS[p] || p, items });
    }
    const rest = source.filter(m => !PROVIDER_ORDER.includes(m.provider));
    if (rest.length > 0) groups.push({ label: 'Andere', items: rest });
    return groups;
  };

  const showModelControls = mode !== 'web_search';

  const handleWebSearch = async (query: string) => {
    setIsStreaming(true);
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(), role: 'user', content: query,
      tokens: null, cost_usd: null, citations: null, created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      const token = getToken();
      const resp = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ query, search_depth: 'basic', max_results: 5 }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      let content = '';
      if (data.answer) content += `**Zusammenfassung:** ${data.answer}\n\n`;
      content += `### Suchergebnisse (${data.result_count})\n\n`;
      for (const r of data.results || []) {
        content += `**[${r.title}](${r.url})**\n${r.content}\n\n`;
      }
      content += `\n---\n*Quelle: Tavily · ${data.credits_used} Credit(s)*`;

      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: 'assistant', content,
        tokens: null, cost_usd: null, citations: data.results, created_at: new Date().toISOString(),
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: 'assistant',
        content: `Suchfehler: ${(err as Error).message}`,
        tokens: null, cost_usd: null, citations: null, created_at: new Date().toISOString(),
      }]);
    } finally {
      setIsStreaming(false);
    }
  };

  const processSSE = async (resp: Response) => {
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buf = '', acc = '', thinkAcc = '', evt = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('event: ')) { evt = line.slice(7).trim(); continue; }
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (evt === 'thinking') {
            thinkAcc += data.content || '';
            setThinkingContent(thinkAcc);
          } else if (evt === 'chunk') {
            acc += data.content || '';
            setStreamingContent(acc);
          } else if (evt === 'done') {
            setMessages(prev => [...prev, {
              id: data.message_id || crypto.randomUUID(), role: 'assistant',
              content: data.content || acc, tokens: data.tokens, cost_usd: data.cost_usd || null,
              reasoning_tokens: data.reasoning_tokens || null,
              thinking: data.thinking || thinkAcc || null,
              citations: data.citations || null, created_at: new Date().toISOString(),
            }]);
            setStreamingContent('');
            setThinkingContent('');
          } else if (evt === 'error') {
            setMessages(prev => [...prev, {
              id: crypto.randomUUID(), role: 'assistant',
              content: `Fehler: ${data.error}`, tokens: null, cost_usd: null,
              citations: null, created_at: new Date().toISOString(),
            }]);
            setStreamingContent('');
            setThinkingContent('');
          } else if (evt === 'ping') {
            // Keepalive — ignorieren
          }
        } catch { /* */ }
      }
    }
  };

  const handleSend = async () => {
    let content = input.trim();
    if (!content || isStreaming) return;
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    // Quick-Capture: /suche wechselt den Modus
    if (content.startsWith('/suche ')) {
      content = content.slice(7).trim();
      setMode('web_search');
    }

    if (mode === 'web_search') {
      await handleWebSearch(content);
      return;
    }

    let convId = activeId;
    if (!convId) {
      try {
        const conv = await api.post<Conversation>('/api/chat/conversations', {
          model: mode === 'agent' ? 'nanobot' : selectedModel,
          temperature,
          mode,
        });
        setConversations(prev => [conv, ...prev]);
        convId = conv.id;
        setActiveId(conv.id);
      } catch (err) {
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(), role: 'assistant',
          content: `Konversation konnte nicht erstellt werden: ${(err as Error).message || 'Unbekannter Fehler'}`,
          tokens: null, cost_usd: null, citations: null, created_at: new Date().toISOString(),
        }]);
        return;
      }
    }

    // User-Nachricht sofort anzeigen
    const attachmentMeta = attachments.map(f => ({ name: f.name, type: f.type }));
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(), role: 'user', content,
      tokens: null, cost_usd: null, citations: null,
      attachments: attachmentMeta.length > 0 ? attachmentMeta : undefined,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsStreaming(true);
    setStreamingContent('');
    setThinkingContent(mode === 'agent' ? 'InnoPilot verarbeitet mit MCP-Tools...' : '');
    setAttachments([]);

    const token = getToken();
    const endpoint = mode === 'agent'
      ? `/api/chat/conversations/${convId}/agent`
      : `/api/chat/conversations/${convId}/messages`;

    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ content, model: selectedModel, temperature }),
      });
      if (!resp.ok) {
        const errorText = await resp.text().catch(() => `HTTP ${resp.status}`);
        throw new Error(errorText);
      }
      await processSSE(resp);
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(), role: 'assistant',
          content: `Fehler: ${(err as Error).message}`,
          tokens: null, cost_usd: null, citations: null, created_at: new Date().toISOString(),
        }]);
      }
    } finally {
      setIsStreaming(false);
      setStreamingContent('');
      setThinkingContent('');
      loadConversations();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setAttachments(prev => [...prev, ...Array.from(e.target.files!)]);
    e.target.value = '';
  };

  const removeAttachment = (idx: number) => setAttachments(prev => prev.filter((_, i) => i !== idx));

  const createTaskFromMessage = async (msgId: string, content: string) => {
    try {
      const result = await api.post<{ task_id: string }>(`/api/chat/messages/${msgId}/create-task`, {
        title: content.slice(0, 80),
      });
      setSelectedTaskId(result.task_id);
    } catch { /* */ }
  };

  const copyMsg = async (id: string, content: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const downloadMsg = (content: string) => {
    const blob = new Blob([content], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `chat-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.delete(`/api/chat/conversations/${id}`);
    setConversations(prev => prev.filter(c => c.id !== id));
    if (activeId === id) { setActiveId(null); setMessages([]); }
  };

  const toggleThinking = (id: string) => {
    setExpandedThinking(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const resizeTA = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
  };

  const modeIcon = (m: string) => {
    if (m === 'chat') return <ChatBubbleIcon className="h-4 w-4" />;
    if (m === 'web_search') return <SearchIcon className="h-4 w-4" />;
    if (m === 'deep_research') return <ResearchIcon className="h-4 w-4" />;
    if (m === 'agent') return <SparkleIcon className="h-4 w-4" />;
    return null;
  };

  const selectedModelInfo = modelInfo(selectedModel);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sidebar */}
      <div className={`${showSidebar ? 'w-72' : 'w-0'} shrink-0 overflow-hidden border-r border-gray-200 bg-white/60 backdrop-blur-sm transition-all dark:border-gray-800 dark:bg-gray-900/60`}>
        <div className="flex h-full w-72 flex-col">
          <div className="border-b border-gray-200 p-3 dark:border-gray-800">
            <button onClick={() => { setActiveId(null); setMessages([]); }} className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700">
              <PlusIcon className="h-4 w-4" />
              Neuer Chat
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex justify-center p-6"><div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" /></div>
            ) : conversations.length === 0 ? (
              <p className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">Noch keine Konversationen</p>
            ) : (
              <ul className="space-y-0.5 p-2">
                {conversations.map(c => (
                  <li key={c.id} onClick={() => setActiveId(c.id)} className={`group relative cursor-pointer rounded-lg px-3 py-2 text-sm transition-colors ${activeId === c.id ? 'bg-indigo-50 dark:bg-indigo-900/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}`}>
                    <p className="truncate font-medium text-gray-900 dark:text-gray-100">{c.title || c.last_message_preview || 'Neuer Chat'}</p>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] text-gray-600 dark:bg-gray-700 dark:text-gray-400">{modelLabel(c.model)}</span>
                      {c.total_cost_usd > 0 && (
                        <span className="text-[10px] text-gray-400">${c.total_cost_usd.toFixed(4)}</span>
                      )}
                    </div>
                    <button onClick={(e) => handleDelete(c.id, e)} className="absolute right-2 top-2 rounded p-1 text-gray-400 opacity-0 hover:bg-red-100 hover:text-red-600 group-hover:opacity-100 dark:hover:bg-red-900/30" title="Löschen">
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar — schlank, nur Sidebar-Toggle + Einstellungen */}
        <div className="flex items-center gap-2 border-b border-gray-200 bg-white/50 px-3 py-2 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/50">
          <button onClick={() => setShowSidebar(!showSidebar)} className="shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800" title={showSidebar ? 'Verlauf ausblenden' : 'Verlauf einblenden'}>
            <SidebarIcon className="h-5 w-5" />
          </button>

          <div className="flex-1" />

          {mode === 'agent' && (
            <span className="rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700 dark:border-violet-800 dark:bg-violet-900/30 dark:text-violet-300">
              InnoPilot · MCP-Tools
            </span>
          )}

          <button onClick={() => navigate('/einstellungen?tab=llm')} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300" title="LLM-Einstellungen">
            <SettingsIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Nachrichten oder Leerzustand */}
        {!activeId && messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50 dark:bg-indigo-900/30">
                {modeIcon(mode)}
              </div>
              <p className="text-lg font-medium text-gray-700 dark:text-gray-300">
                {mode === 'chat' && 'Neuen Chat starten'}
                {mode === 'web_search' && 'Websuche starten'}
                {mode === 'deep_research' && 'Deep Research starten'}
                {mode === 'agent' && 'Agent-Konversation starten'}
              </p>
              <p className="mt-1 max-w-md text-sm text-gray-400 dark:text-gray-500">
                {mode === 'chat' && 'Wähle ein Modell und schreibe eine Nachricht. Ideal für direkte Fragen, Texte erstellen, Ideen brainstormen.'}
                {mode === 'web_search' && 'Gib einen Suchbegriff oder eine Frage ein — Tavily liefert aktuelle Ergebnisse aus dem Web. Beispiel: «Neueste Trends KI Schweiz 2026» oder «Wechselkurs CHF EUR heute»'}
                {mode === 'deep_research' && 'Stelle eine komplexe Frage — das LLM recherchiert umfassend mit mehreren Quellen. Ideal für Marktanalysen, Technologievergleiche, Zusammenfassungen.'}
                {mode === 'agent' && 'Gib InnoPilot eine Aufgabe — er hat Zugriff auf Kalender, E-Mail, CRM, Aufgaben und mehr. Beispiel: «Zeige meine Termine nächste Woche» oder «Erstelle einen Zeitblocker für Freitag 08:00–09:00»'}
              </p>
            </div>

            {/* Prominente Eingabekarte im Leerzustand */}
            <div className="w-full max-w-2xl">
              {attachments.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {attachments.map((f, i) => (
                    <div key={i} className="flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs text-gray-700 shadow-sm dark:bg-gray-800 dark:text-gray-300">
                      <FileIcon className="h-3.5 w-3.5 text-gray-400" />
                      <span className="max-w-[120px] truncate">{f.name}</span>
                      <button onClick={() => removeAttachment(i)} className="ml-1 text-gray-400 hover:text-red-500"><XIcon className="h-3 w-3" /></button>
                    </div>
                  ))}
                </div>
              )}
              <div className="rounded-2xl border border-gray-300 bg-white shadow-sm transition-colors focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={e => { setInput(e.target.value); resizeTA(); }}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    mode === 'web_search' ? 'Suchbegriff eingeben...'
                      : mode === 'deep_research' ? 'Frage für Deep Research eingeben...'
                        : mode === 'agent' ? 'Aufgabe für InnoPilot eingeben...'
                          : 'Nachricht eingeben... (/suche für Websuche)'
                  }
                  rows={3}
                  className="max-h-48 min-h-[80px] w-full resize-none border-0 bg-transparent px-4 pt-3 pb-1 text-sm outline-none placeholder:text-gray-400 dark:text-gray-100 dark:placeholder:text-gray-500"
                />
                <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2.5">
                  <div className="flex rounded-lg bg-gray-100 p-0.5 dark:bg-gray-700">
                    {MODES.map(m => (
                      <button key={m.id} onClick={() => setMode(m.id)} className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-all ${mode === m.id ? 'bg-white text-indigo-700 shadow-sm dark:bg-gray-600 dark:text-indigo-300' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        {modeIcon(m.id)}
                        <span className="hidden sm:inline">{m.label}</span>
                      </button>
                    ))}
                  </div>
                  {showModelControls && <div className="h-4 w-px bg-gray-200 dark:bg-gray-600" />}
                  {showModelControls && (
                    <>
                      <div className="relative" ref={modelDropdownRef}>
                        <button onClick={() => setModelOpen(!modelOpen)} className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
                          {selectedModelInfo?.type === 'local' ? <LockIcon className="h-3 w-3 text-green-500" /> : <CloudIcon className="h-3 w-3 text-blue-400" />}
                          <span className="max-w-[120px] truncate">{modelLabel(selectedModel)}</span>
                          {selectedModelInfo?.capabilities.includes('thinking') && <span className="rounded bg-violet-100 px-1 py-px text-[9px] font-semibold text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">T</span>}
                          <ChevronIcon className="h-3 w-3" />
                        </button>
                        {modelOpen && (
                          <div className="absolute bottom-full left-0 z-50 mb-1 max-h-96 w-80 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-800">
                            {groupedModels().map(g => (
                              <div key={g.label}>
                                <p className="sticky top-0 bg-gray-50 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:bg-gray-900 dark:text-gray-400">{g.label}</p>
                                {g.items.map(m => (
                                  <button key={m.id} onClick={() => { setSelectedModel(m.id); setModelOpen(false); }} className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-indigo-50 dark:hover:bg-indigo-900/30 ${selectedModel === m.id ? 'bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300' : 'text-gray-700 dark:text-gray-300'}`}>
                                    {m.type === 'local' ? <LockIcon className="h-3 w-3 shrink-0 text-green-500" /> : <CloudIcon className="h-3 w-3 shrink-0 text-blue-400" />}
                                    <span className="flex-1 truncate">{m.name}</span>
                                    {m.capabilities.includes('thinking') && <span className="rounded bg-violet-100 px-1 py-px text-[9px] font-semibold text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">Thinking</span>}
                                    {m.capabilities.includes('web_search') && <span className="rounded bg-emerald-100 px-1 py-px text-[9px] font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">Web</span>}
                                    {m.capabilities.includes('deep_research') && <span className="rounded bg-amber-100 px-1 py-px text-[9px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">Deep</span>}
                                  </button>
                                ))}
                              </div>
                            ))}
                            {groupedModels().length === 0 && (
                              <p className="px-3 py-4 text-center text-xs text-gray-400">Keine Modelle für diesen Modus verfügbar</p>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="relative">
                        <button onClick={() => setTempOpen(!tempOpen)} className="rounded-md px-1.5 py-1 text-[11px] font-medium text-gray-500 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700">T&nbsp;{temperature.toFixed(1)}</button>
                        {tempOpen && (
                          <div className="absolute bottom-full left-0 z-50 mb-1 w-48 rounded-lg border border-gray-200 bg-white p-3 shadow-xl dark:border-gray-700 dark:bg-gray-800">
                            <input type="range" min="0" max="1.5" step="0.1" value={temperature} onChange={e => setTemperature(parseFloat(e.target.value))} className="w-full accent-indigo-600" />
                            <div className="mt-1 flex justify-between text-[10px] text-gray-400"><span>Präzise</span><span>Kreativ</span></div>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                  <div className="ml-auto flex items-center gap-2">
                    {mode === 'web_search' && <span className="text-[10px] text-gray-400 dark:text-gray-500">via Tavily</span>}
                    {mode === 'agent' && <span className="text-[10px] text-gray-400 dark:text-gray-500">MCP-Tools aktiv</span>}
                    <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileSelect} />
                    <button onClick={() => fileInputRef.current?.click()} className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700" title="Datei anhängen"><AttachIcon className="h-4 w-4" /></button>
                    <button onClick={handleSend} disabled={!input.trim() || isStreaming} className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"><SendIcon className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map(msg => (
                <div key={msg.id} className={`group/msg flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`relative max-w-[85%] rounded-2xl px-4 py-3 ${msg.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100'}`}>
                    {/* Thinking-Block */}
                    {msg.thinking && (
                      <div className="mb-2">
                        <button onClick={() => toggleThinking(msg.id)} className="flex items-center gap-1.5 text-[11px] font-medium text-violet-600 hover:text-violet-800 dark:text-violet-400 dark:hover:text-violet-300">
                          <BrainIcon className="h-3.5 w-3.5" />
                          <span>Überlegungen</span>
                          <svg className={`h-3 w-3 transition-transform ${expandedThinking.has(msg.id) ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" /></svg>
                        </button>
                        {expandedThinking.has(msg.id) && (
                          <div className="mt-1.5 rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs text-violet-800 dark:border-violet-800 dark:bg-violet-900/20 dark:text-violet-300">
                            <div className="whitespace-pre-wrap">{msg.thinking}</div>
                          </div>
                        )}
                      </div>
                    )}

                    {msg.role === 'assistant' ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none [&_a]:text-indigo-600 [&_a]:underline dark:[&_a]:text-indigo-400">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
                    )}

                    {msg.attachments && msg.attachments.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {msg.attachments.map((a, i) => (
                          <span key={i} className="inline-flex items-center gap-1 rounded bg-white/20 px-2 py-0.5 text-[10px]">
                            <FileIcon className="h-3 w-3" />{a.name}
                          </span>
                        ))}
                      </div>
                    )}

                    {(msg.tokens || msg.cost_usd) && (
                      <p className="mt-1 text-right text-[10px] opacity-50">
                        {msg.tokens && <>{msg.tokens} Tokens</>}
                        {msg.reasoning_tokens ? <> · {msg.reasoning_tokens} Reasoning</> : null}
                        {msg.cost_usd ? <> · ${msg.cost_usd.toFixed(5)}</> : null}
                      </p>
                    )}

                    {msg.role === 'assistant' && (
                      <div className="absolute -bottom-3 right-2 flex items-center gap-0.5 rounded-lg border border-gray-200 bg-white px-1 py-0.5 opacity-0 shadow-sm transition-opacity group-hover/msg:opacity-100 dark:border-gray-700 dark:bg-gray-800">
                        <button onClick={() => copyMsg(msg.id, msg.content)} className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Kopieren">
                          {copiedId === msg.id ? <CheckIcon className="h-3.5 w-3.5 text-green-500" /> : <CopyIcon className="h-3.5 w-3.5" />}
                        </button>
                        <button onClick={() => downloadMsg(msg.content)} className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Herunterladen">
                          <DownloadIcon className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => createTaskFromMessage(msg.id, msg.content)} className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Aufgabe erstellen">
                          <TaskIcon className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Streaming / Agent-Verarbeitung */}
              {isStreaming && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl bg-gray-100 px-4 py-3 dark:bg-gray-800">
                    {thinkingContent && (
                      <div className="mb-2 rounded-lg border border-violet-200 bg-violet-50 p-3 dark:border-violet-800 dark:bg-violet-900/20">
                        <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-violet-600 dark:text-violet-400">
                          <BrainIcon className="h-3.5 w-3.5 animate-pulse" />
                          <span>{mode === 'agent' ? 'InnoPilot arbeitet...' : 'Modell überlegt...'}</span>
                        </div>
                        <div className="whitespace-pre-wrap text-xs text-violet-800 dark:text-violet-300">{thinkingContent}</div>
                      </div>
                    )}
                    {streamingContent ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
                      </div>
                    ) : !thinkingContent ? (
                      <div className="flex items-center gap-2">
                        <div className="flex gap-1">
                          <span className="h-2 w-2 animate-pulse rounded-full bg-gray-400" />
                          <span className="h-2 w-2 animate-pulse rounded-full bg-gray-400 [animation-delay:200ms]" />
                          <span className="h-2 w-2 animate-pulse rounded-full bg-gray-400 [animation-delay:400ms]" />
                        </div>
                        {mode === 'agent' && <span className="text-xs text-gray-400">InnoPilot wird gestartet...</span>}
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {/* Anhänge + Eingabe nur wenn Chat aktiv (Leerzustand hat eigene Eingabe) */}
        {(activeId || messages.length > 0) && attachments.length > 0 && (
          <div className="border-t border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-800 dark:bg-gray-900/50">
            <div className="mx-auto flex max-w-3xl flex-wrap gap-2">
              {attachments.map((f, i) => (
                <div key={i} className="flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs text-gray-700 shadow-sm dark:bg-gray-800 dark:text-gray-300">
                  <FileIcon className="h-3.5 w-3.5 text-gray-400" />
                  <span className="max-w-[120px] truncate">{f.name}</span>
                  <button onClick={() => removeAttachment(i)} className="ml-1 text-gray-400 hover:text-red-500">
                    <XIcon className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Eingabebereich am unteren Rand — nur bei aktiver Konversation */}
        {(activeId || messages.length > 0) && <div className="border-t border-gray-200 bg-white/80 px-4 py-3 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/80">
          <div className="mx-auto max-w-3xl">
            <div className="rounded-2xl border border-gray-300 bg-white shadow-sm transition-colors focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => { setInput(e.target.value); resizeTA(); }}
                onKeyDown={handleKeyDown}
                placeholder={
                  mode === 'web_search' ? 'Suchbegriff eingeben...'
                    : mode === 'deep_research' ? 'Frage für Deep Research eingeben...'
                      : mode === 'agent' ? 'Aufgabe für InnoPilot eingeben...'
                        : 'Nachricht eingeben... (/suche für Websuche)'
                }
                rows={1}
                className="max-h-36 min-h-[44px] w-full resize-none rounded-t-2xl border-0 bg-transparent px-4 pt-3 pb-1 text-sm outline-none placeholder:text-gray-400 dark:text-gray-100 dark:placeholder:text-gray-500"
              />

              {/* Untere Toolbar: Modi + Modell + Temperatur + Buttons */}
              <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2.5">
                {/* Segmented Mode Control */}
                <div className="flex rounded-lg bg-gray-100 p-0.5 dark:bg-gray-700">
                  {MODES.map(m => (
                    <button
                      key={m.id}
                      onClick={() => setMode(m.id)}
                      className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-all ${
                        mode === m.id
                          ? 'bg-white text-indigo-700 shadow-sm dark:bg-gray-600 dark:text-indigo-300'
                          : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                      }`}
                    >
                      {modeIcon(m.id)}
                      <span className="hidden sm:inline">{m.label}</span>
                    </button>
                  ))}
                </div>

                {/* Trennlinie */}
                {showModelControls && <div className="h-4 w-px bg-gray-200 dark:bg-gray-600" />}

                {/* Modell (nicht bei Websuche/Agent) */}
                {showModelControls && (
                  <>
                    <div className="relative" ref={modelDropdownRef}>
                      <button onClick={() => setModelOpen(!modelOpen)} className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
                        {selectedModelInfo?.type === 'local' ? <LockIcon className="h-3 w-3 text-green-500" /> : <CloudIcon className="h-3 w-3 text-blue-400" />}
                        <span className="max-w-[120px] truncate">{modelLabel(selectedModel)}</span>
                        {selectedModelInfo?.capabilities.includes('thinking') && <span className="rounded bg-violet-100 px-1 py-px text-[9px] font-semibold text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">T</span>}
                        <ChevronIcon className="h-3 w-3" />
                      </button>
                      {modelOpen && (
                        <div className="absolute bottom-full left-0 z-50 mb-1 max-h-96 w-80 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-800">
                          {groupedModels().map(g => (
                            <div key={g.label}>
                              <p className="sticky top-0 bg-gray-50 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:bg-gray-900 dark:text-gray-400">{g.label}</p>
                              {g.items.map(m => (
                                <button key={m.id} onClick={() => { setSelectedModel(m.id); setModelOpen(false); }} className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-indigo-50 dark:hover:bg-indigo-900/30 ${selectedModel === m.id ? 'bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300' : 'text-gray-700 dark:text-gray-300'}`}>
                                  {m.type === 'local' ? <LockIcon className="h-3 w-3 shrink-0 text-green-500" /> : <CloudIcon className="h-3 w-3 shrink-0 text-blue-400" />}
                                  <span className="flex-1 truncate">{m.name}</span>
                                  {m.capabilities.includes('thinking') && <span className="rounded bg-violet-100 px-1 py-px text-[9px] font-semibold text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">Thinking</span>}
                                  {m.capabilities.includes('web_search') && <span className="rounded bg-emerald-100 px-1 py-px text-[9px] font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">Web</span>}
                                  {m.capabilities.includes('deep_research') && <span className="rounded bg-amber-100 px-1 py-px text-[9px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">Deep</span>}
                                </button>
                              ))}
                            </div>
                          ))}
                          {groupedModels().length === 0 && (
                            <p className="px-3 py-4 text-center text-xs text-gray-400">Keine Modelle für diesen Modus verfügbar</p>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="relative">
                      <button onClick={() => setTempOpen(!tempOpen)} className="rounded-md px-1.5 py-1 text-[11px] font-medium text-gray-500 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700">
                        T&nbsp;{temperature.toFixed(1)}
                      </button>
                      {tempOpen && (
                        <div className="absolute bottom-full left-0 z-50 mb-1 w-48 rounded-lg border border-gray-200 bg-white p-3 shadow-xl dark:border-gray-700 dark:bg-gray-800">
                          <input type="range" min="0" max="1.5" step="0.1" value={temperature} onChange={e => setTemperature(parseFloat(e.target.value))} className="w-full accent-indigo-600" />
                          <div className="mt-1 flex justify-between text-[10px] text-gray-400"><span>Präzise</span><span>Kreativ</span></div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* Modus-Hinweis + Nachrichtenanzahl */}
                <div className="ml-auto flex items-center gap-2">
                  {mode === 'web_search' && (
                    <span className="text-[10px] text-gray-400 dark:text-gray-500" title="Tavily durchsucht das Web nach aktuellen Ergebnissen">via Tavily</span>
                  )}
                  {mode === 'agent' && (
                    <span className="text-[10px] text-gray-400 dark:text-gray-500" title="InnoPilot hat Zugriff auf Kalender, E-Mail, CRM, Aufgaben">MCP-Tools aktiv</span>
                  )}
                  {messages.length > 0 && (
                    <span className="text-[10px] text-gray-400 dark:text-gray-500">{messages.length} Nachrichten</span>
                  )}
                  <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileSelect} />
                  <button onClick={() => fileInputRef.current?.click()} className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700" title="Datei anhängen">
                    <AttachIcon className="h-4 w-4" />
                  </button>
                  <button onClick={handleSend} disabled={!input.trim() || isStreaming} className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-700 disabled:opacity-40">
                    <SendIcon className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>}
      </div>

      {/* Standard Task-Detail-Dialog */}
      {selectedTaskId && (
        <TaskDetailDialog
          taskId={selectedTaskId}
          onClose={() => setSelectedTaskId(null)}
          onUpdated={() => setSelectedTaskId(null)}
        />
      )}
    </div>
  );
}


/* ── Icons ── */

function PlusIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>;
}
function TrashIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>;
}
function SidebarIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M12 17.25h8.25" /></svg>;
}
function ChevronIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" /></svg>;
}
function CheckIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" /></svg>;
}
function CopyIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" /></svg>;
}
function DownloadIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" /></svg>;
}
function SendIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" /></svg>;
}
function AttachIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" /></svg>;
}
function FileIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" /></svg>;
}
function XIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>;
}
function SettingsIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.431.992a7.723 7.723 0 0 1 0 .255c-.007.378.138.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" /></svg>;
}
function LockIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>;
}
function CloudIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z" /></svg>;
}
function BrainIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" /></svg>;
}
function TaskIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>;
}
function ChatBubbleIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" /></svg>;
}
function SearchIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" /></svg>;
}
function ResearchIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" /></svg>;
}
function SparkleIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" /></svg>;
}
