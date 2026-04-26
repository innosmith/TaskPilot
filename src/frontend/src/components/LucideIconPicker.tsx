import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { icons, type LucideIcon } from 'lucide-react';
import { Search, X } from 'lucide-react';

const ALL_ICONS: { name: string; Icon: LucideIcon }[] = Object.entries(icons).map(
  ([name, Icon]) => ({ name, Icon: Icon as LucideIcon }),
);

const BATCH_SIZE = 120;

interface LucideIconPickerProps {
  currentIcon?: string | null;
  onSelect: (iconName: string | null) => void;
  onClose: () => void;
}

export function LucideIconPicker({ currentIcon, onSelect, onClose }: LucideIconPickerProps) {
  const [query, setQuery] = useState('');
  const [visibleCount, setVisibleCount] = useState(BATCH_SIZE);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  const filtered = useMemo(() => {
    if (!query.trim()) return ALL_ICONS;
    const q = query.toLowerCase();
    return ALL_ICONS.filter((i) => i.name.toLowerCase().includes(q));
  }, [query]);

  useEffect(() => {
    setVisibleCount(BATCH_SIZE);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [query]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
      setVisibleCount((prev) => Math.min(prev + BATCH_SIZE, filtered.length));
    }
  }, [filtered.length]);

  const visible = filtered.slice(0, visibleCount);

  return (
    <div
      ref={containerRef}
      className="absolute right-0 top-8 z-[100] w-80 rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900"
    >
      <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-2 dark:border-gray-800">
        <Search className="h-4 w-4 shrink-0 text-gray-400" strokeWidth={1.5} />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Icon suchen..."
          className="min-w-0 flex-1 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:text-white dark:placeholder:text-gray-500"
        />
        {query && (
          <button onClick={() => setQuery('')} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <X className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
        )}
        <span className="shrink-0 text-[10px] text-gray-400">{filtered.length}</span>
      </div>
      <div
        ref={scrollRef}
        className="max-h-80 overflow-y-auto p-2"
        onScroll={handleScroll}
      >
        <div className="grid grid-cols-8 gap-1">
          {visible.map(({ name, Icon }) => (
            <button
              key={name}
              onClick={() => onSelect(name)}
              className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
                currentIcon === name
                  ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400'
                  : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
              }`}
              title={name}
            >
              <Icon className="h-4 w-4" strokeWidth={1.5} />
            </button>
          ))}
        </div>
        {filtered.length === 0 && (
          <p className="py-4 text-center text-xs text-gray-400">Keine Icons gefunden</p>
        )}
        {visibleCount < filtered.length && (
          <p className="py-2 text-center text-[10px] text-gray-400">Weiter scrollen...</p>
        )}
      </div>
      {currentIcon && (
        <div className="border-t border-gray-100 px-3 py-2 dark:border-gray-800">
          <button
            onClick={() => onSelect(null)}
            className="w-full rounded-lg px-2 py-1 text-xs text-red-500 transition-colors hover:bg-red-50 dark:hover:bg-red-950"
          >
            Icon entfernen
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Renders a Lucide icon by name. Returns null if name is invalid.
 */
export function LucideIconByName({
  name,
  className,
  strokeWidth = 1.5,
}: {
  name: string;
  className?: string;
  strokeWidth?: number;
}) {
  const Icon = (icons as Record<string, LucideIcon>)[name];
  if (!Icon) return null;
  return <Icon className={className} strokeWidth={strokeWidth} />;
}
