import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, PieChart, Pie,
  LineChart, Line, Legend, ComposedChart,
} from 'recharts';
import { api } from '../api/client';
import { BackgroundPicker } from '../components/BackgroundPicker';

// ── Typen ──────────────────────────────────────────

interface DashboardData {
  kpis: Record<string, unknown>;
  cost_distribution: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

interface RenewalEntry {
  vendor: string;
  product?: string;
  next_date: string;
  days_until: number;
  amount_chf?: number;
  cycle?: string;
  currency?: string;
}

interface RenewalCalendar {
  critical?: RenewalEntry[];
  warning?: RenewalEntry[];
  info?: RenewalEntry[];
  stable?: RenewalEntry[];
  [key: string]: unknown;
}

interface AnomalyEntry {
  vendor: string;
  old_amount?: number;
  new_amount?: number;
  change_pct?: number;
  severity: string;
  detail?: string;
  [key: string]: unknown;
}

interface AnomalyData {
  critical?: AnomalyEntry[];
  warning?: AnomalyEntry[];
  info?: AnomalyEntry[];
  stable?: AnomalyEntry[];
  [key: string]: unknown;
}

interface VendorRow {
  vendor: string;
  total_chf: number;
  invoice_count: number;
  avg_chf?: number;
  share_pct?: number;
  category?: string;
  [key: string]: unknown;
}

interface InvoiceRow {
  index?: number;
  invoice_id?: number;
  vendor?: string;
  date?: string;
  amount?: number;
  amount_chf?: number;
  currency?: string;
  category?: string;
  product?: string;
  filename?: string;
  [key: string]: unknown;
}

// ── Helfer ─────────────────────────────────────────

function formatCHF(value: number | null | undefined): string {
  if (value == null) return '–';
  return new Intl.NumberFormat('de-CH', { style: 'currency', currency: 'CHF' }).format(value);
}

function formatK(v: number): string {
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(0)}k`;
  return v.toFixed(0);
}

const CATEGORY_COLORS: Record<string, string> = {
  SOFTWARE: '#6366f1',
  AI: '#8b5cf6',
  HARDWARE: '#f59e0b',
  HOSTING: '#22c55e',
  DOMAIN: '#14b8a6',
  CONSULTING: '#ec4899',
  TRAINING: '#f97316',
};
const FALLBACK_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316', '#ec4899', '#06b6d4', '#84cc16'];

const TOOLTIP_STYLE: React.CSSProperties = {
  borderRadius: '0.5rem',
  fontSize: '0.8rem',
  backgroundColor: '#1f2937',
  color: '#f3f4f6',
  border: '1px solid #374151',
  boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
};
const CURSOR_STYLE = { fill: 'rgba(99,102,241,0.06)' };

// ── Error Boundary ──────────────────────────────────

class CreditorsErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center dark:border-red-800 dark:bg-red-950/30">
            <h2 className="mb-2 text-lg font-bold text-red-700 dark:text-red-400">Rendering-Fehler</h2>
            <p className="mb-4 text-sm text-red-600 dark:text-red-300">{this.state.error?.message}</p>
            <button
              onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            >
              Seite neu laden
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Hauptkomponente (wrapped) ───────────────────────

export default function CreditorsPage() {
  return (
    <CreditorsErrorBoundary>
      <CreditorsPageInner />
    </CreditorsErrorBoundary>
  );
}

function CreditorsPageInner() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [renewals, setRenewals] = useState<RenewalCalendar | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyData | null>(null);
  const [vendors, setVendors] = useState<VendorRow[]>([]);
  const [trends, setTrends] = useState<Record<string, unknown>[]>([]);
  const [yoy, setYoy] = useState<Record<string, unknown> | null>(null);
  const [recurring, setRecurring] = useState<Record<string, unknown> | null>(null);
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchYear, setSearchYear] = useState<number | undefined>(undefined);
  const [researchPrompt, setResearchPrompt] = useState<string | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);
  const [expandedRenewal, setExpandedRenewal] = useState<string | null>(null);
  const [expandedAnomaly, setExpandedAnomaly] = useState<string | null>(null);
  const [selectedInvoice, setSelectedInvoice] = useState<Record<string, unknown> | null>(null);
  const [invoiceDetailLoading, setInvoiceDetailLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashR, renR, anomR, vendR, trendR, yoyR, recR] = await Promise.allSettled([
        api.get<DashboardData>('/api/creditors/dashboard'),
        api.get<RenewalCalendar>('/api/creditors/renewal-calendar'),
        api.get<AnomalyData>('/api/creditors/anomalies'),
        api.get<VendorRow[]>('/api/creditors/vendors?top_n=15'),
        api.get<Record<string, unknown>[]>('/api/creditors/trends'),
        api.get<Record<string, unknown>>('/api/creditors/yoy'),
        api.get<Record<string, unknown>>('/api/creditors/recurring'),
      ]);
      if (dashR.status === 'fulfilled') setDashboard(dashR.value);
      if (renR.status === 'fulfilled') setRenewals(renR.value);
      if (anomR.status === 'fulfilled') setAnomalies(anomR.value);
      if (vendR.status === 'fulfilled') {
        const v = vendR.value;
        let vendorArr: VendorRow[] = [];
        if (Array.isArray(v)) {
          vendorArr = v;
        } else if (v && typeof v === 'object') {
          const raw = (v as Record<string, unknown>).vendors ?? (v as Record<string, unknown>).lifecycle ?? [];
          vendorArr = Array.isArray(raw) ? raw as VendorRow[] : [];
        }
        setVendors(vendorArr.map(row => ({
          ...row,
          vendor: row.vendor ?? (row as Record<string, unknown>).Kreditor as string ?? '–',
          total_chf: row.total_chf ?? (row as Record<string, unknown>).Total_CHF as number ?? 0,
          invoice_count: row.invoice_count ?? (row as Record<string, unknown>).Anzahl as number ?? 0,
          avg_chf: row.avg_chf ?? (row as Record<string, unknown>).Avg_pro_Jahr as number,
          category: row.category ?? (row as Record<string, unknown>).Kategorie as string,
        })));
      }
      if (trendR.status === 'fulfilled') {
        const t = trendR.value;
        let trendArr: Record<string, unknown>[] = [];
        if (Array.isArray(t)) trendArr = t;
        else if (t && typeof t === 'object') {
          const raw = (t as Record<string, unknown>).months ?? (t as Record<string, unknown>).data ?? [];
          trendArr = Array.isArray(raw) ? raw : [];
        }
        setTrends(trendArr.map(row => ({
          ...row,
          month: row.month ?? row.Monatsname ?? `M${row.Monat ?? ''}`,
          total_chf: row.total_chf ?? row.Aktuell_CHF ?? 0,
          avg_chf: row.avg_chf ?? row.Vorjahr_CHF,
        })));
      }
      if (yoyR.status === 'fulfilled') setYoy(yoyR.value);
      if (recR.status === 'fulfilled') setRecurring(recR.value);

      const allFailed = [dashR, renR, anomR, vendR, trendR, yoyR, recR].every(r => r.status === 'rejected');
      if (allFailed) {
        const firstErr = (dashR as PromiseRejectedResult).reason;
        setError(firstErr instanceof Error ? firstErr.message : 'InvoiceInsight nicht erreichbar');
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Daten konnten nicht geladen werden');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSearch = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.set('query', searchQuery);
      if (searchYear) params.set('year', String(searchYear));
      params.set('limit', '50');
      const result = await api.get<unknown>(`/api/creditors/invoices?${params}`);
      const arr = Array.isArray(result) ? result : (result as Record<string, unknown>).invoices as InvoiceRow[] || [];
      setInvoices(arr as InvoiceRow[]);
    } catch { /* ignore */ }
  }, [searchQuery, searchYear]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    api.get<{ creditors_background_url: string | null }>('/api/settings')
      .then(s => { if (s.creditors_background_url) setBgUrl(s.creditors_background_url); })
      .catch(() => {});
  }, []);

  const handleRefresh = async () => {
    try { await api.post('/api/creditors/cache/clear', {}); } catch { /* ignore */ }
    loadData();
  };

  const handleBgSelect = async (url: string | null) => {
    await api.patch('/api/settings', { creditors_background_url: url });
    setBgUrl(url);
  };

  const handleInvoiceClick = async (row: InvoiceRow) => {
    const id = row.index ?? row.invoice_id;
    if (id == null) return;
    setInvoiceDetailLoading(true);
    try {
      const detail = await api.get<Record<string, unknown>>(`/api/creditors/invoice/${id}`);
      setSelectedInvoice(detail);
    } catch { /* ignore */ }
    setInvoiceDetailLoading(false);
  };

  const handleGenerateResearch = async () => {
    setResearchLoading(true);
    try {
      const result = await api.post<Record<string, unknown>>('/api/creditors/deep-research', {});
      const prompt = (result as Record<string, unknown>).prompt as string
        || (result as Record<string, unknown>).text as string
        || JSON.stringify(result, null, 2);
      setResearchPrompt(prompt);
    } catch (e: unknown) {
      setResearchPrompt(`Fehler: ${e instanceof Error ? e.message : 'unbekannt'}`);
    }
    setResearchLoading(false);
  };

  // ── Styling ──────────────────────────────────────
  const hasBg = !!bgUrl;
  const isGradient = bgUrl?.startsWith('gradient:') ?? false;
  const bgStyle = isGradient
    ? { background: bgUrl!.slice('gradient:'.length) }
    : hasBg ? { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover' as const, backgroundPosition: 'center' } : undefined;

  const cardClass = hasBg
    ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10'
    : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50';
  const sectionClass = `rounded-2xl p-4 sm:p-6 ${cardClass}`;
  const textPrimary = hasBg ? 'text-white' : 'text-gray-900 dark:text-white';
  const textSecondary = hasBg ? 'text-white/70' : 'text-gray-500 dark:text-gray-400';
  const textMuted = hasBg ? 'text-white/50' : 'text-gray-400 dark:text-gray-500';

  // ── KPI-Extraktion ───────────────────────────────
  const kpis = dashboard?.kpis || {};
  const totalVolume = (kpis.total_spend_chf ?? kpis.total_volume_chf ?? kpis.total_volume ?? 0) as number;
  const projectedAnnual = (kpis.total_yearly_chf ?? kpis.projected_annual_chf ?? kpis.projected_annual ?? 0) as number;
  const weightedMonthly = (kpis.monthly_burn_rate ?? kpis.weighted_monthly_chf ?? kpis.weighted_monthly ?? 0) as number;
  const invoiceCount = (kpis.invoice_count ?? kpis.total_invoices ?? 0) as number;
  const vendorCount = (kpis.provider_count ?? kpis.vendor_count ?? 0) as number;
  const aiShare = (kpis.ai_share_pct ?? 0) as number;
  const burnRate = (kpis.monthly_burn_rate ?? kpis.burn_rate_monthly ?? 0) as number;

  // ── Kostenverteilung ─────────────────────────────
  const costDistData = useMemo(() => {
    const dist = dashboard?.cost_distribution;
    if (!dist) return [];
    const arr = Array.isArray(dist) ? dist : (dist as Record<string, unknown>).categories as Record<string, unknown>[] ?? [];
    if (!Array.isArray(arr)) return [];
    return arr.map((item: Record<string, unknown>) => ({
      name: (item.name ?? item.Kategorie ?? item.kategorie ?? '?') as string,
      value: (item.value ?? item.Total_CHF ?? item.total_chf ?? 0) as number,
      share: (item.share ?? item.Anteil_Pct ?? item.anteil_pct ?? 0) as number,
    }));
  }, [dashboard?.cost_distribution]);

  // ── Renewals Aufbereitung ────────────────────────
  const renewalGroups = useMemo(() => {
    if (!renewals) return [];
    const groups: { label: string; color: string; dotColor: string; entries: RenewalEntry[] }[] = [];

    const normalize = (raw: unknown): RenewalEntry[] => {
      if (!Array.isArray(raw)) return [];
      return raw.map((e: Record<string, unknown>) => ({
        vendor: (e.vendor ?? e.Kreditor ?? '–') as string,
        product: (e.product ?? e.Produkt ?? '') as string,
        next_date: (e.next_date ?? e.Renewal_Date ?? e.Faelligkeitsdatum ?? '') as string,
        days_until: (e.days_until ?? e.Tage_bis_Renewal ?? 999) as number,
        amount_chf: (e.amount_chf ?? e.Betrag_CHF ?? e.Betrag) as number | undefined,
        cycle: (e.cycle ?? e.Abrechnungszyklus ?? '') as string,
        currency: (e.currency ?? e.Währung ?? 'CHF') as string,
      }));
    };

    const critical = normalize(renewals.critical);
    const warning = normalize(renewals.warning);
    const info = normalize(renewals.info);

    if (critical.length > 0) groups.push({ label: `Kritisch (<30 Tage) — ${critical.length}`, color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', dotColor: 'bg-red-500', entries: critical });
    if (warning.length > 0) groups.push({ label: `Bald (30–60 Tage) — ${warning.length}`, color: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400', dotColor: 'bg-amber-500', entries: warning });
    if (info.length > 0) groups.push({ label: `Info (60+ Tage) — ${info.length}`, color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', dotColor: 'bg-blue-500', entries: info });
    return groups;
  }, [renewals]);

  // ── Anomalien Aufbereitung ───────────────────────
  const anomalyGroups = useMemo(() => {
    if (!anomalies) return [];
    const groups: { label: string; color: string; entries: AnomalyEntry[] }[] = [];
    const normalizeAnomaly = (raw: unknown): AnomalyEntry[] => {
      if (!Array.isArray(raw)) return [];
      return raw.map((e: Record<string, unknown>) => ({
        vendor: (e.vendor ?? e.kreditor ?? '–') as string,
        old_amount: (e.old_amount ?? e.prev_betrag) as number | undefined,
        new_amount: (e.new_amount ?? e.curr_betrag) as number | undefined,
        change_pct: (e.change_pct) as number | undefined,
        severity: (e.severity ?? 'INFO') as string,
        detail: (e.detail ?? e.title ?? '') as string,
        ...(e as Record<string, unknown>),
      }));
    };

    const crit = normalizeAnomaly(anomalies.critical);
    const warn = normalizeAnomaly(anomalies.warning);
    const inf = normalizeAnomaly(anomalies.info);

    if (crit.length > 0) groups.push({ label: `Kritisch — ${crit.length} Auffälligkeit(en)`, color: 'text-red-600 dark:text-red-400', entries: crit });
    if (warn.length > 0) groups.push({ label: `Warnung — ${warn.length} Punkt(e)`, color: 'text-amber-600 dark:text-amber-400', entries: warn });
    if (inf.length > 0) groups.push({ label: `Info — ${inf.length} Hinweis(e)`, color: 'text-blue-600 dark:text-blue-400', entries: inf });
    return groups;
  }, [anomalies]);

  // ── YoY-Daten ────────────────────────────────────
  const yoyYears = useMemo(() => {
    if (!yoy) return [];
    return (yoy.years as number[] | undefined) ?? [];
  }, [yoy]);
  const yoyChartData = useMemo(() => {
    if (!yoy) return [];
    const cats = (yoy.categories ?? yoy.data) as Record<string, unknown>[] | undefined;
    if (!Array.isArray(cats)) return [];
    return cats.map((item: Record<string, unknown>) => ({
      ...item,
      name: item.name ?? item.Kategorie ?? item.kategorie ?? '–',
    }));
  }, [yoy]);

  // ── Recurring-Daten ──────────────────────────────
  const recurringData = useMemo(() => {
    if (!recurring) return { recurring_items: [], onetime_items: [], recurring_total: 0, onetime_total: 0 };
    const norm = (arr: unknown): Record<string, unknown>[] => {
      if (!Array.isArray(arr)) return [];
      return arr.map((item: Record<string, unknown>) => ({
        ...item,
        name: item.name ?? item.Kategorie ?? item.kategorie ?? '–',
        total_chf: item.Total_CHF ?? item.total_chf ?? 0,
        count: item.Anzahl ?? item.count ?? 0,
      }));
    };
    return {
      recurring_items: norm(recurring.recurring ?? recurring.recurring_items),
      onetime_items: norm(recurring.onetime ?? recurring.onetime_items),
      recurring_total: (recurring.recurring_total ?? recurring.recurring_total_chf ?? 0) as number,
      onetime_total: (recurring.onetime_total ?? recurring.onetime_total_chf ?? 0) as number,
    };
  }, [recurring]);

  // ── Metadaten ────────────────────────────────────
  const meta = dashboard?.metadata || {};
  const categories = ((meta as Record<string, unknown>).categories ?? []) as string[];
  const yearRangeObj = (meta as Record<string, unknown>).year_range as Record<string, unknown> | undefined;
  const years = useMemo(() => {
    const from = ((yearRangeObj?.min ?? (meta as Record<string, unknown>).year_from ?? 2023) as number);
    const to = ((yearRangeObj?.max ?? (meta as Record<string, unknown>).year_to ?? new Date().getFullYear()) as number);
    const arr = [];
    for (let y = to; y >= from; y--) arr.push(y);
    return arr;
  }, [yearRangeObj, meta]);

  return (
    <div className="relative flex h-full flex-col" style={hasBg ? bgStyle : undefined}>
      {!hasBg && <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-amber-50/20 dark:from-gray-950 dark:via-gray-900 dark:to-amber-950/10" />}
      {hasBg && !isGradient && <div className="absolute inset-0 bg-black/25 dark:bg-black/40" />}
      {isGradient && <div className="absolute inset-0 bg-black/10 dark:bg-black/25" />}

      <div className="relative z-10 flex-1 overflow-y-auto overflow-x-hidden overscroll-x-none p-4 sm:p-6">
        {/* Header */}
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className={`text-2xl font-bold ${hasBg ? 'text-white drop-shadow-sm' : 'text-gray-900 dark:text-white'}`}>
              Kreditoren
            </h1>
            <p className={`mt-1 text-xs ${textMuted}`}>
              InvoiceInsight · {invoiceCount} Rechnungen · {vendorCount} Kreditoren · Stand: {new Date().toLocaleString('de-CH')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="http://invoice.innosmith.ai"
              target="_blank"
              rel="noopener noreferrer"
              className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${hasBg ? 'bg-white/10 text-white/90 hover:bg-white/20 backdrop-blur-sm' : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}`}
            >
              <ExternalLinkIcon className="h-4 w-4" />
              <span className="hidden sm:inline">InvoiceInsight</span>
            </a>
            <button onClick={() => setBgPickerOpen(true)} className={`rounded-lg p-2 transition-colors ${hasBg ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`} title="Hintergrund ändern">
              <BgImageIcon className="h-5 w-5" />
            </button>
            <button onClick={handleRefresh} disabled={loading} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${hasBg ? 'bg-white/10 text-white/90 hover:bg-white/20 backdrop-blur-sm' : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}`}>
              <RefreshIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Aktualisieren</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">{error}</div>
        )}

        {/* KPI-Karten */}
        {dashboard && (
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            <KpiCard label="Gesamtausgaben" value={formatCHF(totalVolume)} sub={`${vendorCount} Kreditoren`} color="indigo" hasBg={hasBg} />
            <KpiCard label="Proj. Jahreskosten" value={formatCHF(projectedAnnual)} sub="Hochrechnung" color="amber" hasBg={hasBg} />
            <KpiCard label="Ø Monatskosten" value={formatCHF(weightedMonthly)} sub="gewichtet" color="emerald" hasBg={hasBg} />
            <KpiCard label="Rechnungen" value={String(invoiceCount)} sub="total erfasst" color="violet" hasBg={hasBg} />
            {aiShare > 0 && <KpiCard label="AI-Anteil" value={`${aiShare.toFixed(1)}%`} sub="der Gesamtkosten" color="purple" hasBg={hasBg} />}
            {burnRate > 0 && <KpiCard label="Burn-Rate" value={formatCHF(burnRate)} sub="pro Monat" color="rose" hasBg={hasBg} />}
          </div>
        )}

        {/* Erneuerungskalender */}
        {renewalGroups.length > 0 && (
          <div className={`mb-6 ${sectionClass}`}>
            <div className="mb-4 flex items-center gap-3">
              <CalendarIcon className={`h-5 w-5 ${hasBg ? 'text-white' : 'text-amber-500'}`} />
              <h2 className={`text-lg font-semibold ${textPrimary}`}>Erneuerungskalender</h2>
            </div>
            <div className="space-y-4">
              {renewalGroups.map(group => (
                <div key={group.label}>
                  <div className="mb-2 flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${group.dotColor}`} />
                    <h3 className={`text-sm font-semibold ${textPrimary}`}>{group.label}</h3>
                  </div>
                  <div className="space-y-1">
                    {group.entries.map((entry, idx) => {
                      const key = `${group.label}-${idx}`;
                      const isOpen = expandedRenewal === key;
                      return (
                        <button
                          key={key}
                          onClick={() => setExpandedRenewal(isOpen ? null : key)}
                          className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className={`${isOpen ? 'rotate-90' : ''} inline-block transition-transform`}>▸</span>
                              <span className={textPrimary}>{entry.vendor}{entry.product ? ` – ${entry.product}` : ''}</span>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className={`text-xs ${textMuted}`}>📅 {entry.next_date} ({entry.days_until} Tage)</span>
                              {entry.amount_chf != null && <span className={`font-medium ${textPrimary}`}>{formatCHF(entry.amount_chf)}</span>}
                              {entry.cycle && <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${hasBg ? 'bg-white/10 text-white/70' : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}>{entry.cycle}</span>}
                            </div>
                          </div>
                          {isOpen && (
                            <div className={`mt-2 grid grid-cols-2 gap-2 rounded-lg p-3 text-xs ${hasBg ? 'bg-white/5' : 'bg-gray-50 dark:bg-gray-800/50'}`}>
                              <div><span className={textMuted}>Kreditor:</span> <span className={textPrimary}>{entry.vendor}</span></div>
                              {entry.product && <div><span className={textMuted}>Produkt:</span> <span className={textPrimary}>{entry.product}</span></div>}
                              <div><span className={textMuted}>Betrag:</span> <span className={textPrimary}>{formatCHF(entry.amount_chf)} {entry.currency || 'CHF'}</span></div>
                              <div><span className={textMuted}>Zyklus:</span> <span className={textPrimary}>{entry.cycle || '–'}</span></div>
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Kostentrend-Chart */}
        {trends.length > 0 && (
          <div className={`mb-6 ${sectionClass}`}>
            <h2 className={`mb-4 text-lg font-semibold ${textPrimary}`}>Kostenentwicklung (monatlich)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={trends}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={formatK} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE} />
                <Bar dataKey="total_chf" name="Kosten (CHF)" fill="#6366f1" radius={[4, 4, 0, 0]} />
                {trends[0]?.avg_chf != null && <Line type="monotone" dataKey="avg_chf" name="Ø Monat" stroke="#f59e0b" strokeWidth={2} dot={false} />}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Jahresvergleich (YoY) + Kostenverteilung */}
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* YoY */}
          {yoyChartData.length > 0 && yoyYears.length >= 2 && (
            <div className={sectionClass}>
              <h2 className={`mb-4 text-lg font-semibold ${textPrimary}`}>Jahresvergleich nach Kategorie</h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={yoyChartData}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={formatK} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE} />
                  <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
                  {yoyYears.slice(-2).map((yr, i) => (
                    <Bar key={yr} dataKey={String(yr)} name={String(yr)} fill={i === 0 ? '#c7d2fe' : '#6366f1'} radius={[4, 4, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Kostenverteilung Donut */}
          {costDistData.length > 0 && (
            <div className={sectionClass}>
              <h2 className={`mb-4 text-lg font-semibold ${textPrimary}`}>Kostenverteilung</h2>
              <div className="flex items-center gap-6">
                <ResponsiveContainer width={200} height={200}>
                  <PieChart>
                    <Pie
                      data={costDistData as Record<string, unknown>[]}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={90}
                      strokeWidth={2}
                    >
                      {(costDistData as Record<string, unknown>[]).map((entry, i) => (
                        <Cell key={i} fill={CATEGORY_COLORS[(entry.name as string)?.toUpperCase?.()] || FALLBACK_COLORS[i % FALLBACK_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-col gap-1.5">
                  {(costDistData as Record<string, unknown>[]).slice(0, 8).map((entry, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="h-3 w-3 rounded" style={{ backgroundColor: CATEGORY_COLORS[(entry.name as string)?.toUpperCase?.()] || FALLBACK_COLORS[i % FALLBACK_COLORS.length] }} />
                      <span className={textSecondary}>{entry.name as string}</span>
                      <span className={`ml-auto font-medium ${textPrimary}`}>{formatCHF(entry.value as number)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Top-Kreditoren */}
        {vendors.length > 0 && (
          <div className={`mb-6 ${sectionClass}`}>
            <h2 className={`mb-4 text-lg font-semibold ${textPrimary}`}>Top-Kreditoren</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={`border-b ${hasBg ? 'border-white/10' : 'border-gray-200 dark:border-gray-700'}`}>
                    <th className={`px-3 py-2 text-left font-medium ${textSecondary}`}>#</th>
                    <th className={`px-3 py-2 text-left font-medium ${textSecondary}`}>Kreditor</th>
                    <th className={`px-3 py-2 text-right font-medium ${textSecondary}`}>Rechnungen</th>
                    <th className={`px-3 py-2 text-right font-medium ${textSecondary}`}>Total (CHF)</th>
                    <th className={`px-3 py-2 text-right font-medium ${textSecondary}`}>Ø (CHF)</th>
                    <th className={`px-3 py-2 text-right font-medium ${textSecondary}`}>Anteil</th>
                  </tr>
                </thead>
                <tbody>
                  {vendors.map((v, i) => (
                    <tr key={i} className={`border-b transition-colors ${hasBg ? 'border-white/5 hover:bg-white/5' : 'border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/40'}`}>
                      <td className={`px-3 py-2 ${textMuted}`}>{i + 1}</td>
                      <td className={`px-3 py-2 font-medium ${textPrimary}`}>{v.vendor}</td>
                      <td className={`px-3 py-2 text-right tabular-nums ${textSecondary}`}>{v.invoice_count}</td>
                      <td className={`px-3 py-2 text-right font-medium tabular-nums ${textPrimary}`}>{formatCHF(v.total_chf)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums ${textSecondary}`}>{formatCHF(v.avg_chf)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums ${textSecondary}`}>{v.share_pct != null ? `${(v.share_pct as number).toFixed(1)}%` : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Wiederkehrend vs. Einmalig */}
        {(recurringData.recurring_items.length > 0 || recurringData.onetime_items.length > 0) && (
          <div className={`mb-6 ${sectionClass}`}>
            <h2 className={`mb-4 text-lg font-semibold ${textPrimary}`}>Wiederkehrende vs. einmalige Kosten</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className={`text-sm font-semibold ${textPrimary}`}>Wiederkehrend</h3>
                  <span className={`text-sm font-bold ${textPrimary}`}>{formatCHF(recurringData.recurring_total)}</span>
                </div>
                <div className="space-y-1">
                  {recurringData.recurring_items.slice(0, 8).map((item, i) => (
                    <div key={i} className={`flex justify-between text-sm ${textSecondary}`}>
                      <span>{(item.category ?? item.name) as string}</span>
                      <span className={`font-medium ${textPrimary}`}>{formatCHF((item.total_chf ?? item.amount) as number)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className={`text-sm font-semibold ${textPrimary}`}>Einmalig</h3>
                  <span className={`text-sm font-bold ${textPrimary}`}>{formatCHF(recurringData.onetime_total)}</span>
                </div>
                <div className="space-y-1">
                  {recurringData.onetime_items.slice(0, 8).map((item, i) => (
                    <div key={i} className={`flex justify-between text-sm ${textSecondary}`}>
                      <span>{(item.category ?? item.name) as string}</span>
                      <span className={`font-medium ${textPrimary}`}>{formatCHF((item.total_chf ?? item.amount) as number)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Anomalie-Erkennung */}
        {anomalyGroups.length > 0 && (
          <div className={`mb-6 ${sectionClass}`}>
            <div className="mb-4 flex items-center gap-3">
              <SearchIcon className={`h-5 w-5 ${hasBg ? 'text-white' : 'text-amber-500'}`} />
              <h2 className={`text-lg font-semibold ${textPrimary}`}>Anomalie-Erkennung</h2>
            </div>
            <div className="space-y-4">
              {anomalyGroups.map(group => (
                <div key={group.label}>
                  <h3 className={`mb-2 text-sm font-semibold ${group.color}`}>
                    {group.label.startsWith('Kritisch') ? '🔴' : group.label.startsWith('Warnung') ? '🟡' : '🔵'} {group.label}
                  </h3>
                  <div className="space-y-1">
                    {group.entries.map((entry, idx) => {
                      const key = `${group.label}-${idx}`;
                      const isOpen = expandedAnomaly === key;
                      return (
                        <button
                          key={key}
                          onClick={() => setExpandedAnomaly(isOpen ? null : key)}
                          className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'}`}
                        >
                          <div className="flex items-center gap-2">
                            <span className={`${isOpen ? 'rotate-90' : ''} inline-block transition-transform`}>▸</span>
                            <span className={textPrimary}>{entry.vendor}</span>
                            {entry.change_pct != null && (
                              <span className={`text-xs font-medium ${(entry.change_pct ?? 0) > 0 ? 'text-red-500' : 'text-green-500'}`}>
                                {(entry.change_pct ?? 0) > 0 ? '+' : ''}{entry.change_pct?.toFixed(1)}%
                              </span>
                            )}
                            {entry.detail && <span className={`text-xs ${textMuted}`}>{entry.detail}</span>}
                          </div>
                          {isOpen && (
                            <div className={`mt-2 grid grid-cols-3 gap-2 rounded-lg p-3 text-xs ${hasBg ? 'bg-white/5' : 'bg-gray-50 dark:bg-gray-800/50'}`}>
                              <div><span className={textMuted}>Alt:</span> <span className={textPrimary}>{formatCHF(entry.old_amount)}</span></div>
                              <div><span className={textMuted}>Neu:</span> <span className={textPrimary}>{formatCHF(entry.new_amount)}</span></div>
                              <div><span className={textMuted}>Differenz:</span> <span className={`${(entry.change_pct ?? 0) > 0 ? 'text-red-500' : 'text-green-500'}`}>{entry.change_pct?.toFixed(1)}%</span></div>
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Rechnungssuche */}
        <div className={`mb-6 ${sectionClass}`}>
          <h2 className={`mb-4 text-lg font-semibold ${textPrimary}`}>Rechnungsübersicht</h2>
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Suche (Kreditor, Produkt, Datei...)"
              className={`flex-1 rounded-lg px-3 py-2 text-sm outline-none ${hasBg ? 'bg-white/10 text-white placeholder:text-white/40 ring-1 ring-white/20 focus:ring-white/40' : 'border border-gray-200 bg-white text-gray-900 placeholder:text-gray-400 focus:border-indigo-400 dark:border-gray-600 dark:bg-gray-800 dark:text-white dark:placeholder:text-gray-500'}`}
            />
            <select
              value={searchYear ?? ''}
              onChange={e => setSearchYear(e.target.value ? Number(e.target.value) : undefined)}
              className={`rounded-lg px-3 py-2 text-sm outline-none ${hasBg ? 'bg-white/10 text-white ring-1 ring-white/20' : 'border border-gray-200 bg-white text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300'}`}
            >
              <option value="">Alle Jahre</option>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <button onClick={handleSearch} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">
              Suchen
            </button>
          </div>

          {invoices.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={`border-b ${hasBg ? 'border-white/10' : 'border-gray-200 dark:border-gray-700'}`}>
                    <th className={`px-3 py-2 text-left font-medium ${textSecondary}`}>Datum</th>
                    <th className={`px-3 py-2 text-left font-medium ${textSecondary}`}>Kreditor</th>
                    <th className={`px-3 py-2 text-left font-medium ${textSecondary}`}>Produkt</th>
                    <th className={`px-3 py-2 text-left font-medium ${textSecondary}`}>Kategorie</th>
                    <th className={`px-3 py-2 text-right font-medium ${textSecondary}`}>Betrag</th>
                    <th className={`px-3 py-2 text-center font-medium ${textSecondary}`}>Währung</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv, i) => (
                    <tr
                      key={i}
                      onClick={() => handleInvoiceClick(inv)}
                      className={`cursor-pointer border-b transition-colors ${hasBg ? 'border-white/5 hover:bg-white/10' : 'border-gray-100 hover:bg-indigo-50/50 dark:border-gray-800 dark:hover:bg-gray-800/40'}`}
                    >
                      <td className={`px-3 py-2 tabular-nums ${textSecondary}`}>{inv.date || '–'}</td>
                      <td className={`px-3 py-2 font-medium ${textPrimary}`}>{inv.vendor || '–'}</td>
                      <td className={`px-3 py-2 ${textSecondary}`}>{inv.product || '–'}</td>
                      <td className={`px-3 py-2 ${textMuted}`}>
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${hasBg ? 'bg-white/10' : 'bg-gray-100 dark:bg-gray-700'}`}>
                          {inv.category || '–'}
                        </span>
                      </td>
                      <td className={`px-3 py-2 text-right font-medium tabular-nums ${textPrimary}`}>
                        {formatCHF(inv.amount_chf ?? inv.amount)}
                      </td>
                      <td className={`px-3 py-2 text-center ${textMuted}`}>{inv.currency || 'CHF'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {invoices.length === 0 && !loading && (
            <p className={`py-4 text-center text-sm ${textMuted}`}>
              Suchbegriff eingeben und &ldquo;Suchen&rdquo; klicken, um Rechnungen zu finden.
            </p>
          )}
        </div>

        {/* Deep Research */}
        <div className={`mb-6 ${sectionClass}`}>
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ResearchIcon className={`h-5 w-5 ${hasBg ? 'text-white' : 'text-violet-500'}`} />
              <h2 className={`text-lg font-semibold ${textPrimary}`}>Deep Research</h2>
            </div>
            <button
              onClick={handleGenerateResearch}
              disabled={researchLoading}
              className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
            >
              {researchLoading ? <RefreshIcon className="h-4 w-4 animate-spin" /> : <ResearchIcon className="h-4 w-4" />}
              Prompt generieren
            </button>
          </div>
          <p className={`mb-3 text-xs ${textMuted}`}>
            Generiert einen Deep-Research-Prompt basierend auf dem aktuellen IT-Portfolio für strategische Analysen via Perplexity oder Gemini.
          </p>
          {researchPrompt && (
            <div className="relative">
              <pre className={`max-h-96 overflow-auto rounded-lg p-4 text-xs whitespace-pre-wrap ${hasBg ? 'bg-black/20 text-white/80' : 'bg-gray-50 text-gray-800 dark:bg-gray-900 dark:text-gray-200'}`}>
                {researchPrompt}
              </pre>
              <button
                onClick={() => { navigator.clipboard.writeText(researchPrompt); }}
                className="absolute top-2 right-2 rounded bg-gray-600/80 px-2 py-1 text-xs text-white hover:bg-gray-500"
                title="In Zwischenablage kopieren"
              >
                Kopieren
              </button>
            </div>
          )}
        </div>

        {/* Loading / Empty State */}
        {loading && !dashboard && (
          <div className="flex items-center justify-center py-20">
            <RefreshIcon className="h-8 w-8 animate-spin text-indigo-400" />
          </div>
        )}
        {!loading && !dashboard && !error && (
          <div className={`mt-8 rounded-2xl p-8 text-center ${sectionClass}`}>
            <p className={`text-lg font-semibold ${textPrimary}`}>Keine Daten verfügbar</p>
            <p className={`mt-2 text-sm ${textSecondary}`}>
              InvoiceInsight konnte nicht erreicht werden. Bitte prüfe die Konfiguration und Erreichbarkeit des MCP-Servers.
            </p>
            <button onClick={handleRefresh} className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
              Erneut versuchen
            </button>
          </div>
        )}
      </div>

      {/* Rechnungsdetail-Dialog */}
      {selectedInvoice && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setSelectedInvoice(null)}>
          <div
            className="relative mx-4 max-h-[80vh] w-full max-w-2xl overflow-auto rounded-2xl bg-white p-6 shadow-2xl dark:bg-gray-900"
            onClick={e => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Rechnungsdetails</h2>
              <button onClick={() => setSelectedInvoice(null)} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
                ✕
              </button>
            </div>
            {invoiceDetailLoading ? (
              <div className="flex justify-center py-8"><RefreshIcon className="h-6 w-6 animate-spin text-indigo-400" /></div>
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                {Object.entries(selectedInvoice).map(([key, value]) => {
                  if (value == null || key === 'index') return null;
                  return (
                    <div key={key} className="flex flex-col">
                      <span className="text-xs font-medium text-gray-400 dark:text-gray-500">{key}</span>
                      <span className="text-gray-900 dark:text-white">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={bgUrl}
        onSelect={(url) => { handleBgSelect(url); setBgPickerOpen(false); }}
      />
    </div>
  );
}

// ── Sub-Komponenten ──────────────────────────────

function KpiCard({ label, value, sub, color, hasBg }: {
  label: string; value: string; sub: string; color: string; hasBg: boolean;
}) {
  const colorMap: Record<string, string> = {
    indigo: 'bg-indigo-500', amber: 'bg-amber-500', emerald: 'bg-emerald-500',
    violet: 'bg-violet-500', purple: 'bg-purple-500', rose: 'bg-rose-500',
  };
  return (
    <div className={`rounded-xl p-3 sm:p-4 ${hasBg ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10' : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50'}`}>
      <div className="mb-2 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${colorMap[color] || 'bg-gray-400'}`} />
        <span className={`text-xs font-medium ${hasBg ? 'text-white/60' : 'text-gray-400 dark:text-gray-500'}`}>{label}</span>
      </div>
      <p className={`text-lg font-bold tabular-nums ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>{value}</p>
      <p className={`text-xs ${hasBg ? 'text-white/40' : 'text-gray-400 dark:text-gray-500'}`}>{sub}</p>
    </div>
  );
}

// ── Icons ────────────────────────────────────────

function RefreshIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
    </svg>
  );
}

function BgImageIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
    </svg>
  );
}

function ExternalLinkIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  );
}

function CalendarIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
    </svg>
  );
}

function SearchIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
    </svg>
  );
}

function ResearchIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
    </svg>
  );
}
