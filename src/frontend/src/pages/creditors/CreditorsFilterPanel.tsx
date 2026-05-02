import { useState, useMemo } from 'react';
import { ChevronLeft, RotateCcw, X } from 'lucide-react';
import type { CreditorsFilter, StyleCtx } from './creditors-types';

interface Props {
  filter: CreditorsFilter;
  onChange: (f: CreditorsFilter) => void;
  onClose?: () => void;
  categories: string[];
  vendors: string[];
  yearRange: { min: number; max: number };
  styleCtx: StyleCtx;
}

const ICT_CATS = ['AI', 'SOFTWARE', 'HOSTING', 'DOMAIN'];

const QUICK_RANGES: { label: string; fn: () => Partial<CreditorsFilter> }[] = [
  { label: 'Alle Jahre', fn: () => ({ yearFrom: undefined, yearTo: undefined }) },
  { label: 'Aktuelles Jahr', fn: () => ({ yearFrom: new Date().getFullYear(), yearTo: new Date().getFullYear() }) },
  { label: 'Letzte 2 Jahre', fn: () => ({ yearFrom: new Date().getFullYear() - 1, yearTo: new Date().getFullYear() }) },
];

export function CreditorsFilterPanel({
  filter, onChange, onClose, categories, vendors, yearRange, styleCtx,
}: Props) {
  const [vendorSearch, setVendorSearch] = useState('');
  const [showAllVendors, setShowAllVendors] = useState(false);

  const years = useMemo(() => {
    const arr: number[] = [];
    for (let y = yearRange.min; y <= yearRange.max; y++) arr.push(y);
    return arr;
  }, [yearRange]);

  const filteredVendors = useMemo(() => {
    const q = vendorSearch.toLowerCase();
    return q ? vendors.filter(v => v.toLowerCase().includes(q)) : vendors;
  }, [vendors, vendorSearch]);

  const visibleVendors = showAllVendors ? filteredVendors : filteredVendors.slice(0, 10);

  const isIctActive = ICT_CATS.every(c => filter.categories?.includes(c))
    && (filter.categories?.length === ICT_CATS.length);

  const toggleCategory = (cat: string) => {
    const cur = filter.categories ?? [];
    const next = cur.includes(cat) ? cur.filter(c => c !== cat) : [...cur, cat];
    onChange({ ...filter, categories: next.length ? next : undefined });
  };

  const toggleVendor = (v: string) => {
    const cur = filter.vendors ?? [];
    const next = cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v];
    onChange({ ...filter, vendors: next.length ? next : undefined });
  };

  const toggleIct = () => {
    onChange({ ...filter, categories: isIctActive ? undefined : [...ICT_CATS] });
  };

  const reset = () => {
    onChange({ yearFrom: undefined, yearTo: undefined, categories: undefined, vendors: undefined });
    setVendorSearch('');
    setShowAllVendors(false);
  };

  const { textPrimary, textSecondary, textMuted, hasBg } = styleCtx;

  const inputClass =
    'w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-2.5 py-1.5 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40';

  const selectClass = inputClass + ' appearance-none cursor-pointer';

  const activePills: string[] = [];
  if (filter.yearFrom || filter.yearTo) {
    activePills.push(`${filter.yearFrom ?? '…'} – ${filter.yearTo ?? '…'}`);
  }
  if (filter.categories?.length) {
    activePills.push(`${filter.categories.length} Kat.`);
  }
  if (filter.vendors?.length) {
    activePills.push(`${filter.vendors.length} Anb.`);
  }

  return (
    <aside className="w-64 shrink-0 flex flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className={`text-sm font-semibold ${textPrimary}`}>Filter</span>
        <button
          onClick={onClose}
          className={`p-1 rounded-lg transition-colors ${hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-100 dark:hover:bg-gray-800'} ${textMuted}`}
        >
          <X className="h-4 w-4 lg:hidden" />
          <ChevronLeft className="h-4 w-4 hidden lg:block" />
        </button>
      </div>

      {/* Active filter badges */}
      {activePills.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {activePills.map(p => (
            <span
              key={p}
              className="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300"
            >
              {p}
            </span>
          ))}
        </div>
      )}

      {/* Schnellfilter */}
      <section>
        <h4 className={`text-xs font-medium uppercase tracking-wide mb-2 ${textSecondary}`}>Schnellfilter</h4>
        <div className="flex flex-wrap gap-1.5">
          {QUICK_RANGES.map(q => {
            const range = q.fn();
            const active = filter.yearFrom === range.yearFrom && filter.yearTo === range.yearTo;
            return (
              <button
                key={q.label}
                onClick={() => onChange({ ...filter, ...range })}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-indigo-600 text-white'
                    : hasBg
                      ? 'bg-white/10 text-white/70 hover:bg-white/20'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
                }`}
              >
                {q.label}
              </button>
            );
          })}
        </div>
      </section>

      {/* Zeitraum */}
      <section>
        <h4 className={`text-xs font-medium uppercase tracking-wide mb-2 ${textSecondary}`}>Zeitraum</h4>
        <div className="flex gap-2">
          <label className="flex-1">
            <span className={`text-[11px] ${textMuted}`}>Von</span>
            <select
              value={filter.yearFrom ?? ''}
              onChange={e => onChange({ ...filter, yearFrom: e.target.value ? +e.target.value : undefined })}
              className={selectClass}
            >
              <option value="">–</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="flex-1">
            <span className={`text-[11px] ${textMuted}`}>Bis</span>
            <select
              value={filter.yearTo ?? ''}
              onChange={e => onChange({ ...filter, yearTo: e.target.value ? +e.target.value : undefined })}
              className={selectClass}
            >
              <option value="">–</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        </div>
      </section>

      {/* Kategorien */}
      <section>
        <h4 className={`text-xs font-medium uppercase tracking-wide mb-2 ${textSecondary}`}>Kategorien</h4>
        <button
          onClick={toggleIct}
          className={`mb-2 w-full rounded-lg px-2 py-1.5 text-xs font-medium transition-colors ${
            isIctActive
              ? 'bg-indigo-600 text-white'
              : hasBg
                ? 'bg-white/10 text-white/70 hover:bg-white/20'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
          }`}
        >
          Nur ICT
        </button>
        <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
          {categories.map(cat => (
            <label key={cat} className={`flex items-center gap-2 text-xs cursor-pointer rounded px-1 py-0.5 hover:bg-gray-100/50 dark:hover:bg-gray-800/50 ${textPrimary}`}>
              <input
                type="checkbox"
                checked={filter.categories?.includes(cat) ?? false}
                onChange={() => toggleCategory(cat)}
                className="rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
              />
              {cat}
            </label>
          ))}
        </div>
      </section>

      {/* Anbieter */}
      <section className="flex-1 min-h-0 flex flex-col">
        <h4 className={`text-xs font-medium uppercase tracking-wide mb-2 ${textSecondary}`}>Anbieter</h4>
        <input
          type="text"
          placeholder="Suchen…"
          value={vendorSearch}
          onChange={e => { setVendorSearch(e.target.value); setShowAllVendors(false); }}
          className={`${inputClass} mb-2`}
        />
        <div className="flex flex-col gap-1 overflow-y-auto max-h-48">
          {visibleVendors.map(v => (
            <label key={v} className={`flex items-center gap-2 text-xs cursor-pointer rounded px-1 py-0.5 hover:bg-gray-100/50 dark:hover:bg-gray-800/50 ${textPrimary}`}>
              <input
                type="checkbox"
                checked={filter.vendors?.includes(v) ?? false}
                onChange={() => toggleVendor(v)}
                className="rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
              />
              <span className="truncate">{v}</span>
            </label>
          ))}
        </div>
        {!showAllVendors && filteredVendors.length > 10 && (
          <button
            onClick={() => setShowAllVendors(true)}
            className={`mt-1 text-xs ${textMuted} hover:underline text-left`}
          >
            +{filteredVendors.length - 10} mehr anzeigen
          </button>
        )}
      </section>

      {/* Reset */}
      <button
        onClick={reset}
        className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors
          ${hasBg
            ? 'bg-white/10 text-white/70 hover:bg-white/20'
            : 'bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700'
          } ${textSecondary}`}
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Filter zurücksetzen
      </button>
    </aside>
  );
}
