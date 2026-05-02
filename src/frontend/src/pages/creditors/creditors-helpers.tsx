import type React from 'react';
import type { RenewalEntry, AnomalyEntry, VendorRow, CreditorsFilter } from './creditors-types';

export function formatCHF(value: number | null | undefined): string {
  if (value == null) return '–';
  return new Intl.NumberFormat('de-CH', { style: 'currency', currency: 'CHF' }).format(value);
}

export function formatK(v: number): string {
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(0)}k`;
  return v.toFixed(0);
}

export const CATEGORY_COLORS: Record<string, string> = {
  SOFTWARE: '#6366f1',
  AI: '#8b5cf6',
  HARDWARE: '#f59e0b',
  HOSTING: '#22c55e',
  DOMAIN: '#14b8a6',
  CONSULTING: '#ec4899',
  BERATUNG: '#ec4899',
  TRAINING: '#f97316',
  PERSONAL: '#3b82f6',
  VERSICHERUNG: '#ef4444',
  STEUERN_GEBUEHREN: '#64748b',
  TELEKOM: '#06b6d4',
  FAHRZEUG: '#a855f7',
  LOGISTIK: '#84cc16',
  MARKETING: '#f43f5e',
  SONSTIGES: '#94a3b8',
};

export const FALLBACK_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6',
  '#14b8a6', '#f97316', '#ec4899', '#06b6d4', '#84cc16',
  '#3b82f6', '#a855f7', '#64748b', '#f43f5e',
];

export function getCategoryColor(name: string, index: number): string {
  return CATEGORY_COLORS[name?.toUpperCase?.()] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

export const TOOLTIP_STYLE: React.CSSProperties = {
  borderRadius: '0.5rem',
  fontSize: '0.8rem',
  backgroundColor: '#1f2937',
  color: '#f3f4f6',
  border: '1px solid #374151',
  boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
};

export const CURSOR_STYLE = { fill: 'rgba(99,102,241,0.06)' };

export function normalizeRenewal(e: Record<string, unknown>): RenewalEntry {
  return {
    vendor: (e.vendor ?? e.Kreditor ?? '–') as string,
    product: (e.product ?? e.Produkt ?? '') as string,
    next_date: (e.next_date ?? e.Renewal_Date ?? e.Faelligkeitsdatum ?? '') as string,
    days_until: (e.days_until ?? e.Tage_bis_Renewal ?? 999) as number,
    amount_chf: (e.amount_chf ?? e.Betrag_CHF ?? e.Betrag) as number | undefined,
    cycle: (e.cycle ?? e.Abrechnungszyklus ?? '') as string,
    currency: (e.currency ?? e.Währung ?? 'CHF') as string,
    ...e,
  };
}

export function normalizeRenewals(raw: unknown): RenewalEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeRenewal);
}

export function normalizeAnomaly(e: Record<string, unknown>): AnomalyEntry {
  return {
    vendor: (e.vendor ?? e.kreditor ?? '–') as string,
    old_amount: (e.old_amount ?? e.prev_betrag) as number | undefined,
    new_amount: (e.new_amount ?? e.curr_betrag) as number | undefined,
    change_pct: e.change_pct as number | undefined,
    severity: (e.severity ?? 'INFO') as string,
    detail: (e.detail ?? e.title ?? '') as string,
    ...e,
  };
}

export function normalizeAnomalies(raw: unknown): AnomalyEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeAnomaly);
}

export function normalizeVendor(row: Record<string, unknown>): VendorRow {
  return {
    ...row,
    vendor: (row.vendor ?? row.Kreditor ?? '–') as string,
    total_chf: (row.total_chf ?? row.Total_CHF ?? 0) as number,
    invoice_count: (row.invoice_count ?? row.Anzahl ?? 0) as number,
    avg_chf: (row.avg_chf ?? row.Avg_pro_Jahr) as number | undefined,
    category: (row.category ?? row.Kategorie) as string | undefined,
    share_pct: row.share_pct as number | undefined,
  };
}

export function buildFilterParams(filter: CreditorsFilter): URLSearchParams {
  const p = new URLSearchParams();
  if (filter.yearFrom) p.set('year_from', String(filter.yearFrom));
  if (filter.yearTo) p.set('year_to', String(filter.yearTo));
  if (filter.categories?.length) p.set('categories', filter.categories.join(','));
  if (filter.vendors?.length) p.set('vendors', filter.vendors.join(','));
  return p;
}

export function extractKpi(kpis: Record<string, unknown>, ...keys: string[]): number {
  for (const k of keys) {
    const v = kpis[k];
    if (typeof v === 'number') return v;
  }
  return 0;
}

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700/50 ${className}`} />
  );
}

export function activeFilterCount(filter: CreditorsFilter): number {
  let n = 0;
  if (filter.yearFrom != null) n++;
  if (filter.yearTo != null) n++;
  if (filter.categories?.length) n++;
  if (filter.vendors?.length) n++;
  return n;
}
