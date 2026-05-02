import { useState, useEffect, useMemo, useCallback } from 'react';
import { X, ExternalLink } from 'lucide-react';
import { api } from '../../api/client';
import type { CreditorsFilter, StyleCtx, VendorRow, InvoiceRow } from './creditors-types';
import { formatCHF, normalizeVendor, buildFilterParams, Skeleton } from './creditors-helpers';

interface Props { filter: CreditorsFilter; styleCtx: StyleCtx }

interface ExtVendor extends VendorRow {
  first_invoice?: string; last_invoice?: string;
  status?: string; yearly_cost?: number;
}

type SortKey =
  | 'vendor' | 'category' | 'first_invoice' | 'last_invoice'
  | 'tenure' | 'invoice_count' | 'total_chf' | 'yearly_cost' | 'status';
interface SortState { key: SortKey; dir: 'asc' | 'desc' }
interface CatGroup { name: string; vendors: ExtVendor[]; totalSpend: number }

function isActive(v: ExtVendor): boolean {
  if (v.status === 'Aktiv') return true;
  if (!v.last_invoice) return false;
  return Date.now() - new Date(v.last_invoice).getTime() < 365.25 * 24 * 3600_000;
}

function tenureMonths(a?: string, b?: string): number {
  if (!a || !b) return 0;
  const d1 = new Date(a), d2 = new Date(b);
  return Math.max(0, (d2.getFullYear() - d1.getFullYear()) * 12 + d2.getMonth() - d1.getMonth());
}

function fmtTenure(m: number): string {
  if (m <= 0) return '–';
  if (m < 12) return `${m} Mt.`;
  const y = Math.floor(m / 12), r = m % 12;
  return r ? `${y} J. ${r} Mt.` : `${y} J.`;
}

function norm(raw: Record<string, unknown>): ExtVendor {
  const b = normalizeVendor(raw);
  return {
    ...b,
    first_invoice: (raw.first_invoice ?? raw.Erste_Rechnung ?? '') as string,
    last_invoice: (raw.last_invoice ?? raw.Letzte_Rechnung ?? '') as string,
    status: (raw.status ?? raw.Status ?? '') as string,
    yearly_cost: (raw.yearly_cost ?? raw.Avg_pro_Jahr ?? b.avg_chf ?? 0) as number,
  };
}

function cmpVal(v: ExtVendor, k: SortKey): string | number {
  switch (k) {
    case 'vendor': return v.vendor.toLowerCase();
    case 'category': return (v.category ?? '').toLowerCase();
    case 'first_invoice': return v.first_invoice ?? '';
    case 'last_invoice': return v.last_invoice ?? '';
    case 'tenure': return tenureMonths(v.first_invoice, v.last_invoice);
    case 'invoice_count': return v.invoice_count;
    case 'total_chf': return v.total_chf;
    case 'yearly_cost': return v.yearly_cost ?? 0;
    case 'status': return isActive(v) ? 0 : 1;
  }
}

const COLS: { key: SortKey; label: string; right?: boolean }[] = [
  { key: 'vendor', label: 'Anbieter' }, { key: 'category', label: 'Kategorie' },
  { key: 'first_invoice', label: 'Erstrechnung' }, { key: 'last_invoice', label: 'Letztrechnung' },
  { key: 'tenure', label: 'Laufzeit' }, { key: 'invoice_count', label: 'Anzahl', right: true },
  { key: 'total_chf', label: 'Total CHF', right: true },
  { key: 'yearly_cost', label: 'Jahreskosten', right: true }, { key: 'status', label: 'Status' },
];

export function CreditorsVendors({ filter, styleCtx }: Props) {
  const { hasBg, textPrimary, textSecondary, textMuted } = styleCtx;
  const card = `rounded-xl p-3 sm:p-4 ${hasBg
    ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10'
    : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50'}`;

  const [vendors, setVendors] = useState<ExtVendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<SortState>({ key: 'total_chf', dir: 'desc' });
  const [sel, setSel] = useState<ExtVendor | null>(null);
  const [dinv, setDinv] = useState<InvoiceRow[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    const qs = buildFilterParams(filter); qs.set('top_n', '50');
    const s = qs.toString() ? `?${qs}` : '';
    api.get<unknown[]>(`/api/creditors/vendors${s}`)
      .then(r => { setVendors((r ?? []).map(x => norm(x as Record<string, unknown>))); setLoading(false); })
      .catch(() => api.get<unknown[]>(`/api/creditors/vendor-overview${s}`)
        .then(r => { setVendors((r ?? []).map(x => norm(x as Record<string, unknown>))); setLoading(false); })
        .catch(() => setLoading(false)));
  }, [filter]);

  const sorted = useMemo(() => {
    const l = [...vendors];
    l.sort((a, b) => {
      const va = cmpVal(a, sort.key), vb = cmpVal(b, sort.key);
      const c = va < vb ? -1 : va > vb ? 1 : 0;
      return sort.dir === 'asc' ? c : -c;
    });
    return l;
  }, [vendors, sort]);

  const { active, inactive } = useMemo(() => {
    let a = 0, i = 0;
    for (const v of vendors) isActive(v) ? a++ : i++;
    return { active: a, inactive: i };
  }, [vendors]);

  const catGroups = useMemo<CatGroup[]>(() => {
    const m = new Map<string, ExtVendor[]>();
    for (const v of vendors) {
      const c = v.category || 'Sonstig';
      m.set(c, [...(m.get(c) ?? []), v]);
    }
    return [...m.entries()]
      .map(([name, vl]) => ({ name, vendors: vl, totalSpend: vl.reduce((s, v) => s + v.total_chf, 0) }))
      .sort((a, b) => b.totalSpend - a.totalSpend);
  }, [vendors]);

  const toggleSort = useCallback((k: SortKey) => {
    setSort(p => p.key === k ? { key: k, dir: p.dir === 'asc' ? 'desc' : 'asc' } : { key: k, dir: 'desc' });
  }, []);

  const openDrawer = useCallback((v: ExtVendor) => {
    setSel(v); setOpen(true);
    api.get<InvoiceRow[]>(`/api/creditors/vendor/${encodeURIComponent(v.vendor)}`)
      .then(r => setDinv(r ?? [])).catch(() => setDinv([]));
  }, []);

  const closeDrawer = useCallback(() => {
    setOpen(false); setTimeout(() => { setSel(null); setDinv([]); }, 300);
  }, []);

  const sIcon = (k: SortKey) => sort.key === k ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '';

  const badge = (v: ExtVendor) => {
    const a = isActive(v);
    return (
      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${a
        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
        : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'}`}>
        {a ? 'Aktiv' : 'Inaktiv'}
      </span>
    );
  };

  const kpis = [
    { label: 'Aktive Kreditoren', value: active, cls: 'text-emerald-600 dark:text-emerald-400' },
    { label: 'Inaktive Kreditoren', value: inactive, cls: 'text-gray-500 dark:text-gray-400' },
    { label: 'Gesamt', value: vendors.length, cls: textPrimary },
  ];

  const hoverRow = hasBg ? 'hover:bg-white/5' : 'hover:bg-gray-50 dark:hover:bg-gray-700/40';
  const subBg = hasBg ? 'bg-white/5 ring-1 ring-white/10' : 'bg-gray-50 dark:bg-gray-800/60';
  const invBg = hasBg ? 'bg-white/5' : 'bg-gray-50 dark:bg-gray-800/50';

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-3 gap-4">
        {kpis.map(k => (
          <div key={k.label} className={card}>
            <p className={`text-xs ${textMuted} mb-1`}>{k.label}</p>
            <p className={`text-2xl font-bold tabular-nums ${k.cls}`}>{k.value}</p>
          </div>
        ))}
      </div>

      {/* Desktop Table */}
      <div className={`${card} overflow-x-auto hidden md:block`}>
        <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Anbieter-Lifecycle</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className={`border-b border-gray-200 dark:border-gray-700 ${textMuted}`}>
              <th className="py-2 pr-2 text-left text-xs font-medium w-8">#</th>
              {COLS.map(c => (
                <th key={c.key} onClick={() => toggleSort(c.key)}
                  className={`py-2 px-2 text-xs font-medium cursor-pointer select-none whitespace-nowrap ${c.right ? 'text-right' : 'text-left'}`}>
                  {c.label}{sIcon(c.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((v, i) => (
              <tr key={v.vendor + i} onClick={() => openDrawer(v)}
                className={`border-b border-gray-100 dark:border-gray-800 cursor-pointer transition-colors ${hoverRow}
                  ${i % 2 === 1 ? 'bg-gray-50/50 dark:bg-gray-800/20' : ''}`}>
                <td className={`py-2.5 pr-2 tabular-nums ${textMuted}`}>{i + 1}</td>
                <td className={`py-2.5 px-2 font-medium ${textPrimary}`}>{v.vendor}</td>
                <td className={`py-2.5 px-2 ${textSecondary}`}>{v.category ?? '–'}</td>
                <td className={`py-2.5 px-2 tabular-nums ${textSecondary}`}>{v.first_invoice || '–'}</td>
                <td className={`py-2.5 px-2 tabular-nums ${textSecondary}`}>{v.last_invoice || '–'}</td>
                <td className={`py-2.5 px-2 ${textSecondary}`}>{fmtTenure(tenureMonths(v.first_invoice, v.last_invoice))}</td>
                <td className={`py-2.5 px-2 text-right tabular-nums ${textSecondary}`}>{v.invoice_count}</td>
                <td className={`py-2.5 px-2 text-right tabular-nums ${textPrimary}`}>{formatCHF(v.total_chf)}</td>
                <td className={`py-2.5 px-2 text-right tabular-nums ${textSecondary}`}>{formatCHF(v.yearly_cost ?? 0)}</td>
                <td className="py-2.5 px-2">{badge(v)}</td>
              </tr>
            ))}
            {!vendors.length && (
              <tr><td colSpan={10} className={`py-8 text-center ${textMuted}`}>Keine Anbieterdaten vorhanden</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden flex flex-col gap-3">
        <h3 className={`text-sm font-semibold ${textPrimary}`}>Anbieter-Lifecycle</h3>
        {sorted.map((v, i) => (
          <div
            key={v.vendor + i}
            onClick={() => openDrawer(v)}
            className={`${card} cursor-pointer active:scale-[0.98] transition-transform`}
          >
            <div className="flex items-start justify-between mb-1.5">
              <div>
                <p className={`text-sm font-semibold ${textPrimary}`}>{v.vendor}</p>
                <p className={`text-xs ${textMuted}`}>{v.category ?? '–'}</p>
              </div>
              {badge(v)}
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className={textSecondary}>{v.invoice_count} Rechn.</span>
              <span className={`font-medium ${textPrimary}`}>{formatCHF(v.total_chf)}</span>
              <span className={`ml-auto ${textMuted}`}>{fmtTenure(tenureMonths(v.first_invoice, v.last_invoice))}</span>
            </div>
          </div>
        ))}
        {!vendors.length && <p className={`text-center py-8 ${textMuted}`}>Keine Anbieterdaten</p>}
      </div>

      {/* Vendor Consolidation */}
      <div className={card}>
        <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Konsolidierung nach Kategorie</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {catGroups.map(g => (
            <div key={g.name} className={`rounded-lg p-3 ${subBg}`}>
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${textPrimary}`}>{g.name}</span>
                <span className={`text-xs tabular-nums ${textMuted}`}>{g.vendors.length} Anbieter</span>
              </div>
              <p className={`text-xs tabular-nums ${textSecondary}`}>{formatCHF(g.totalSpend)}</p>
              {g.vendors.length >= 3 && (
                <p className="mt-1 text-xs font-medium text-amber-600 dark:text-amber-400">Konsolidierung prüfbar</p>
              )}
            </div>
          ))}
          {!catGroups.length && <p className={`text-xs ${textMuted}`}>Keine Kategoriedaten</p>}
        </div>
      </div>

      {/* Vendor Detail Drawer */}
      {sel && (<>
        <div
          className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
          onClick={closeDrawer}
        />
        <div className={`
          fixed z-50 overflow-y-auto shadow-2xl bg-white dark:bg-gray-900 transition-transform duration-300
          inset-0 sm:inset-auto sm:top-0 sm:right-0 sm:h-full sm:w-[min(50vw,36rem)]
          ${open ? 'translate-x-0' : 'translate-x-full'}
        `}>
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className={`text-base font-semibold ${textPrimary}`}>{sel.vendor}</h2>
            <button onClick={closeDrawer} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="p-4 flex flex-col gap-4">
            <div className="flex items-center gap-2 flex-wrap">
              {sel.category && (
                <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">{sel.category}</span>
              )}
              {badge(sel)}
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {([
                ['Erstrechnung', sel.first_invoice || '–'],
                ['Letztrechnung', sel.last_invoice || '–'],
                ['Laufzeit', fmtTenure(tenureMonths(sel.first_invoice, sel.last_invoice))],
                ['Rechnungen', String(sel.invoice_count)],
                ['Total', formatCHF(sel.total_chf)],
                ['Jahreskosten', formatCHF(sel.yearly_cost ?? 0)],
              ] as const).map(([lbl, val]) => (
                <div key={lbl}>
                  <p className={`text-xs ${textMuted}`}>{lbl}</p>
                  <p className={lbl === 'Total' ? `font-semibold ${textPrimary}` : textPrimary}>{val}</p>
                </div>
              ))}
            </div>
            <div>
              <h4 className={`text-xs font-semibold mb-2 ${textSecondary}`}>Rechnungen</h4>
              {!dinv.length ? <p className={`text-xs ${textMuted}`}>Keine Rechnungen geladen</p> : (
                <ul className="flex flex-col gap-1.5">
                  {dinv.map((inv, i) => (
                    <li key={inv.invoice_id ?? i} className={`flex justify-between text-xs rounded-lg px-3 py-2 ${invBg}`}>
                      <span className={`tabular-nums ${textSecondary}`}>{inv.date ?? '–'}</span>
                      <span className={`font-medium tabular-nums ${textPrimary}`}>{formatCHF(inv.amount_chf ?? inv.amount)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {dinv.length > 1 && (() => {
              const by = new Map<string, number>();
              for (const inv of dinv) { const y = (inv.date ?? '').slice(0, 4); if (y) by.set(y, (by.get(y) ?? 0) + (inv.amount_chf ?? inv.amount ?? 0)); }
              const e = [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
              if (e.length < 2) return null;
              const mx = Math.max(...e.map(([, v]) => v), 1);
              return (
                <div>
                  <h4 className={`text-xs font-semibold mb-2 ${textSecondary}`}>Kostentrend</h4>
                  <div className="flex items-end gap-1 h-20">
                    {e.map(([yr, v]) => (
                      <div key={yr} className="flex flex-col items-center flex-1 gap-0.5">
                        <div className="w-full rounded-t bg-indigo-500/80" style={{ height: `${(v / mx) * 100}%` }} />
                        <span className={`text-[10px] tabular-nums ${textMuted}`}>{yr}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      </>)}
    </div>
  );
}
