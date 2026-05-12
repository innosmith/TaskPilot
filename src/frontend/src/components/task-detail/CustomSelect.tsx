import { useState, useRef, useEffect, useCallback, useMemo } from 'react';

export interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
  disabled?: boolean;
  group?: string;
}

interface CustomSelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  searchable?: boolean;
  className?: string;
}

export default function CustomSelect({
  value,
  options,
  onChange,
  placeholder = 'Auswählen…',
  searchable = false,
  className = '',
}: CustomSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [highlightIdx, setHighlightIdx] = useState(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    if (!search) return options;
    const q = search.toLowerCase();
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, search]);

  const enabledFiltered = useMemo(
    () => filtered.filter((o) => !o.disabled),
    [filtered],
  );

  const grouped = useMemo(() => {
    const groups: { key: string | null; items: SelectOption[] }[] = [];
    const map = new Map<string | null, SelectOption[]>();
    for (const opt of filtered) {
      const g = opt.group ?? null;
      if (!map.has(g)) {
        const items: SelectOption[] = [];
        map.set(g, items);
        groups.push({ key: g, items });
      }
      map.get(g)!.push(opt);
    }
    return groups;
  }, [filtered]);

  const toggle = useCallback(() => {
    setOpen((prev) => {
      if (!prev) {
        setSearch('');
        setHighlightIdx(-1);
      }
      return !prev;
    });
  }, []);

  useEffect(() => {
    if (open && searchable) {
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open, searchable]);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  useEffect(() => {
    if (highlightIdx < 0 || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${highlightIdx}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlightIdx]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!open) {
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
          e.preventDefault();
          setOpen(true);
          setSearch('');
          setHighlightIdx(-1);
        }
        return;
      }
      switch (e.key) {
        case 'ArrowDown': {
          e.preventDefault();
          const curPos = highlightIdx < 0
            ? -1
            : enabledFiltered.indexOf(
                filtered.find((_, i) => i === highlightIdx && !filtered[i].disabled)!,
              );
          const nextEnabled = enabledFiltered[curPos + 1];
          if (nextEnabled) setHighlightIdx(filtered.indexOf(nextEnabled));
          break;
        }
        case 'ArrowUp': {
          e.preventDefault();
          const curPos2 = highlightIdx < 0
            ? enabledFiltered.length
            : enabledFiltered.indexOf(
                filtered.find((_, i) => i === highlightIdx && !filtered[i].disabled)!,
              );
          const prevEnabled = enabledFiltered[curPos2 - 1];
          if (prevEnabled) setHighlightIdx(filtered.indexOf(prevEnabled));
          break;
        }
        case 'Enter': {
          e.preventDefault();
          const target = filtered[highlightIdx];
          if (target && !target.disabled) {
            onChange(target.value);
            setOpen(false);
          }
          break;
        }
        case 'Escape':
          e.preventDefault();
          setOpen(false);
          break;
      }
    },
    [open, highlightIdx, filtered, enabledFiltered, onChange],
  );

  return (
    <div ref={containerRef} className={`relative ${className}`} onKeyDown={handleKeyDown}>
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 outline-none transition-colors hover:border-gray-300 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:border-gray-600"
      >
        {selected?.icon && <span className="shrink-0">{selected.icon}</span>}
        <span className="truncate">
          {selected ? selected.label : <span className="text-gray-400 dark:text-gray-500">{placeholder}</span>}
        </span>
        <svg className="ml-auto h-3 w-3 shrink-0 opacity-40" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-10 mt-1 max-h-[240px] overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-900">
          {searchable && (
            <div className="sticky top-0 border-b border-gray-100 bg-white px-2 py-1.5 dark:border-gray-800 dark:bg-gray-900">
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setHighlightIdx(-1); }}
                placeholder="Suchen…"
                className="w-full rounded-md border-0 bg-gray-50 px-2 py-1 text-xs outline-none placeholder:text-gray-400 dark:bg-gray-800 dark:text-gray-200 dark:placeholder:text-gray-500"
              />
            </div>
          )}

          <div ref={listRef} role="listbox">
            {grouped.map(({ key, items }) => (
              <div key={key ?? '__ungrouped'}>
                {key && (
                  <div className="px-2.5 pt-2 pb-1 text-[9px] font-semibold uppercase tracking-wider text-gray-400">
                    {key}
                  </div>
                )}
                {items.map((opt) => {
                  const idx = filtered.indexOf(opt);
                  const isSelected = opt.value === value;
                  const isHighlighted = idx === highlightIdx;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      data-idx={idx}
                      disabled={opt.disabled}
                      onClick={() => {
                        if (opt.disabled) return;
                        onChange(opt.value);
                        setOpen(false);
                      }}
                      className={[
                        'flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs transition-colors',
                        opt.disabled && 'cursor-not-allowed opacity-50',
                        !opt.disabled && isSelected && 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300',
                        !opt.disabled && !isSelected && isHighlighted && 'bg-gray-50 dark:bg-gray-800',
                        !opt.disabled && !isSelected && !isHighlighted && 'text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800',
                      ].filter(Boolean).join(' ')}
                    >
                      {opt.icon && <span className="shrink-0">{opt.icon}</span>}
                      <span className="truncate">{opt.label}</span>
                    </button>
                  );
                })}
              </div>
            ))}
            {filtered.length === 0 && (
              <div className="px-2.5 py-3 text-center text-xs text-gray-400 dark:text-gray-500">
                Keine Treffer
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
