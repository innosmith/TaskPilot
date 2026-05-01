import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell, ComposedChart,
  LineChart, Line, LabelList, Legend,
} from 'recharts';
import { api } from '../api/client';
import { BackgroundPicker } from '../components/BackgroundPicker';

// ── Types ────────────────────────────────────────────

interface KpiOverview {
  bank_balance: number | null;
  bank_account_name: string | null;
  open_invoices_total: number;
  open_invoices_count: number;
  current_month_revenue: number;
  current_month_hours: number;
  forecast_year_revenue: number;
  forecast_year_end_cashflow: number;
  burn_rate: number;
  runway_months: number | null;
  runway_months_incl_debtors: number | null;
  profit_margin_ytd: number | null;
  revenue_ytd: number;
  revenue_ytd_net: number;
  expenses_ytd: number;
  ebitda_ytd: number | null;
  personalquote_ytd: number | null;
  dso_days: number | null;
  liquiditaet_2: number | null;
  ek_quote: number | null;
  revenue_ytd_prior: number;
  expenses_ytd_prior: number;
  ebitda_ytd_prior: number | null;
  personalquote_ytd_prior: number | null;
  profit_margin_ytd_prior: number | null;
  journal_data_from: string | null;
  journal_data_to: string | null;
  currency: string;
}

interface CashflowSpecialItem {
  label: string;
  amount: number;
}

interface CashflowMonth {
  month: string;
  revenue: number;
  expenses: number;
  fin_outflow: number;
  invest_outflow: number;
  delta: number;
  cumulative: number;
  is_forecast: boolean;
  special_items: CashflowSpecialItem[];
}

interface CashflowResponse {
  months: CashflowMonth[];
  forecast_revenue_monthly: number;
  forecast_expenses_monthly: number;
  start_balance: number;
}

interface TogglProject {
  project_name: string;
  client_name: string;
  hours: number;
  rate_per_hour: number;
  amount: number;
  currency: string;
}

interface YoyMonth {
  month_label: string;
  month_num: number;
  revenue_current: number;
  revenue_prior: number;
  expenses_current: number;
  expenses_prior: number;
}

interface YoyResponse {
  current_year: number;
  prior_year: number;
  months: YoyMonth[];
  revenue_current_ytd: number;
  revenue_prior_ytd: number;
  growth_pct: number | null;
}

interface WaterfallStep {
  label: string;
  value: number;
  step_type: string;
}

interface WaterfallResponse {
  steps: WaterfallStep[];
  period_label: string;
  revenue_total: number;
  expenses_total: number;
  result: number;
}

interface MarginMonth {
  month: string;
  label: string;
  ytd_margin: number | null;
  rolling_12m_margin: number | null;
  ytd_margin_prior: number | null;
}

interface MarginTrendResponse {
  months: MarginMonth[];
  current_year: number;
  prior_year: number;
}

interface ExpenseMonthRow {
  month: string;
  year: number;
  categories: Record<string, number>;
  total: number;
}

interface ExpenseMonthlyBreakdown {
  current_year: number;
  prior_year: number;
  months_current: ExpenseMonthRow[];
  months_prior: ExpenseMonthRow[];
  category_labels: Record<string, string>;
}

// ── Formatierung ────────────────────────────────────

function formatCHF(value: number | null | undefined): string {
  if (value == null) return '–';
  return new Intl.NumberFormat('de-CH', { style: 'currency', currency: 'CHF' }).format(value);
}

function formatK(value: number): string {
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(0)}k`;
  return value.toFixed(0);
}

function formatYoyDelta(current: number, prior: number): string {
  if (!prior || prior === 0) return '';
  const pct = ((current - prior) / Math.abs(prior)) * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(0)}% vs. VJ`;
}

function formatMonthLabel(month: string): string {
  const [y, m] = month.split('-');
  const names = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  return `${names[parseInt(m)]} ${y.slice(2)}`;
}

const CATEGORY_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6',
  '#14b8a6', '#f97316', '#ec4899', '#06b6d4', '#84cc16',
  '#d946ef', '#0ea5e9', '#a3e635',
];

const TOOLTIP_STYLE: React.CSSProperties = {
  borderRadius: '0.5rem',
  fontSize: '0.8rem',
  backgroundColor: '#1f2937',
  color: '#f3f4f6',
  border: '1px solid #374151',
  boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
};

const CURSOR_STYLE = { fill: 'rgba(99,102,241,0.06)' };

// ── Hauptkomponente ─────────────────────────────────

export function FinancePage() {
  const [overview, setOverview] = useState<KpiOverview | null>(null);
  const [cashflow, setCashflow] = useState<CashflowResponse | null>(null);
  const [togglProjects, setTogglProjects] = useState<TogglProject[]>([]);
  const [yoy, setYoy] = useState<YoyResponse | null>(null);
  const [waterfall, setWaterfall] = useState<WaterfallResponse | null>(null);
  const [expenseBreakdown, setExpenseBreakdown] = useState<ExpenseMonthlyBreakdown | null>(null);
  const [marginTrend, setMarginTrend] = useState<MarginTrendResponse | null>(null);
  const [pnlPeriod, setPnlPeriod] = useState('ytd');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);

  const loadData = useCallback(async (wfPeriod = 'ytd') => {
    setLoading(true);
    setError(null);
    try {
      const [ov, cf, tp, yoyR, wf, eb, mt] = await Promise.allSettled([
        api.get<KpiOverview>('/api/finance/overview'),
        api.get<CashflowResponse>('/api/finance/cashflow?months_back=6&months_forward=12'),
        api.get<TogglProject[]>('/api/finance/toggl-summary'),
        api.get<YoyResponse>('/api/finance/yoy'),
        api.get<WaterfallResponse>(`/api/finance/pnl-waterfall?period=${wfPeriod}`),
        api.get<ExpenseMonthlyBreakdown>('/api/finance/expense-monthly-breakdown'),
        api.get<MarginTrendResponse>('/api/finance/margin-trend'),
      ]);
      if (ov.status === 'fulfilled') setOverview(ov.value);
      if (cf.status === 'fulfilled') setCashflow(cf.value);
      if (tp.status === 'fulfilled') setTogglProjects(tp.value);
      if (yoyR.status === 'fulfilled') setYoy(yoyR.value);
      if (wf.status === 'fulfilled') setWaterfall(wf.value);
      if (eb.status === 'fulfilled') setExpenseBreakdown(eb.value);
      if (mt.status === 'fulfilled') setMarginTrend(mt.value);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Laden fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    api.get<{ finance_background_url: string | null }>('/api/settings')
      .then(s => setBgUrl(s.finance_background_url))
      .catch(() => {});
  }, [loadData]);

  const handleRefresh = async () => {
    try {
      await api.post('/api/finance/cache/clear', {});
      await api.post('/api/bexio/cache/clear', {});
      await api.post('/api/toggl/cache/clear', {});
    } catch { /* ignore */ }
    loadData();
  };

  const handleBgSelect = async (url: string | null) => {
    await api.patch('/api/settings', { finance_background_url: url });
    setBgUrl(url);
  };

  const hasBg = !!bgUrl;
  const isGradient = bgUrl?.startsWith('gradient:') ?? false;
  const bgStyle = isGradient
    ? { background: bgUrl!.slice('gradient:'.length) }
    : hasBg
      ? { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover' as const, backgroundPosition: 'center' }
      : undefined;

  const currentMonth = new Date().toISOString().slice(0, 7);
  const cardClass = hasBg
    ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10'
    : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50';
  const sectionClass = `rounded-2xl p-4 sm:p-6 ${cardClass}`;

  // Durchschnittswerte fuer Referenzlinien
  const avgRevenue = cashflow?.forecast_revenue_monthly ?? 0;
  const avgExpenses = cashflow?.forecast_expenses_monthly ?? 0;

  // VJ-Durchschnittsumsatz fuer Referenzlinie
  const avgRevenuePrior = useMemo(() => {
    if (!yoy) return 0;
    const priorMonths = yoy.months.filter(m => m.revenue_prior > 0);
    if (priorMonths.length === 0) return 0;
    return priorMonths.reduce((s, m) => s + m.revenue_prior, 0) / priorMonths.length;
  }, [yoy]);

  // marginTrend kommt direkt vom Backend

  // Stacked-Bar-Daten fuer Kostenstruktur
  const costBarData = useMemo(() => {
    if (!expenseBreakdown) return { data: [], keys: [] as string[], labels: {} as Record<string, string> };
    const labels = expenseBreakdown.category_labels;
    const allKeys = new Set<string>();
    const combined: Record<string, number>[] = [];
    for (let m = 0; m < 12; m++) {
      const cur = expenseBreakdown.months_current[m];
      const prior = expenseBreakdown.months_prior[m];
      if (!cur && !prior) continue;
      const curCats = cur?.categories || {};
      const priorCats = prior?.categories || {};
      Object.keys(curCats).forEach(k => allKeys.add(k));
      Object.keys(priorCats).forEach(k => allKeys.add(k));

      const row: Record<string, number> = {
        month: m,
        _label_cur: cur?.month ? `${cur.month} ${String(expenseBreakdown.current_year).slice(2)}` : '',
        _label_prior: prior?.month ? `${prior.month} ${String(expenseBreakdown.prior_year).slice(2)}` : '',
        _total_cur: cur?.total || 0,
        _total_prior: prior?.total || 0,
      };
      Object.keys(curCats).forEach(k => { row[`cur_${k}`] = curCats[k]; });
      Object.keys(priorCats).forEach(k => { row[`prior_${k}`] = priorCats[k]; });
      combined.push(row);
    }
    const sortedKeys = [...allKeys].sort((a, b) => {
      const sumA = expenseBreakdown.months_current.reduce((s, m) => s + (m.categories[a] || 0), 0);
      const sumB = expenseBreakdown.months_current.reduce((s, m) => s + (m.categories[b] || 0), 0);
      return sumB - sumA;
    });
    return { data: combined, keys: sortedKeys, labels };
  }, [expenseBreakdown]);

  // Waterfall-Chart-Daten aufbereiten
  const waterfallChartData = useMemo(() => {
    if (!waterfall) return [];
    let running = 0;
    return waterfall.steps.map(step => {
      if (step.step_type === 'income') {
        const d = { name: step.label, base: 0, bar: step.value, value: step.value, type: step.step_type };
        running = step.value;
        return d;
      } else if (step.step_type === 'expense') {
        const absVal = Math.abs(step.value);
        running -= absVal;
        return { name: step.label, base: running, bar: absVal, value: step.value, type: step.step_type };
      } else {
        return { name: step.label, base: 0, bar: running, value: running, type: step.step_type };
      }
    });
  }, [waterfall]);

  return (
    <div className="relative flex h-full flex-col" style={hasBg ? bgStyle : undefined}>
      {!hasBg && <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-indigo-50/30 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950/20" />}
      {hasBg && !isGradient && <div className="absolute inset-0 bg-black/25 dark:bg-black/40" />}
      {isGradient && <div className="absolute inset-0 bg-black/10 dark:bg-black/25" />}

      <div className="relative z-10 flex-1 overflow-y-auto overflow-x-hidden overscroll-x-none p-4 sm:p-6">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className={`text-2xl font-bold ${hasBg ? 'text-white drop-shadow-sm' : 'text-gray-900 dark:text-white'}`}>Finanz-Controlling</h1>
            {overview && (
              <p className={`mt-1 text-xs ${hasBg ? 'text-white/60' : 'text-gray-400 dark:text-gray-500'}`}>
                Datenstand: Journal{' '}
                {overview.journal_data_from && overview.journal_data_to
                  ? `${formatMonthLabel(overview.journal_data_from.slice(0, 7))} – ${formatMonthLabel(overview.journal_data_to.slice(0, 7))}`
                  : '–'}
                {` · Toggl: live · Aktualisiert: ${new Date().toLocaleString('de-CH')}`}
              </p>
            )}
            {!overview && (
              <p className={`mt-1 text-sm ${hasBg ? 'text-white/70' : 'text-gray-500 dark:text-gray-400'}`}>
                Cashflow-Übersicht, Prognosen und Kostenanalyse
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setBgPickerOpen(true)}
              className={`rounded-lg p-2 transition-colors ${hasBg ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`}
              title="Hintergrund ändern"
            >
              <BgImageIcon className="h-5 w-5" />
            </button>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${hasBg ? 'bg-white/10 text-white/90 hover:bg-white/20 backdrop-blur-sm' : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}`}
            >
              <RefreshIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Aktualisieren
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}

        {/* KPI-Leiste: 9 Karten */}
        <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3">
          <KpiCard
            label="Banksaldo"
            value={formatCHF(overview?.bank_balance)}
            sublabel={overview?.bank_account_name || ''}
            icon={<BankIcon />}
            status={overview?.runway_months != null
              ? (overview.runway_months > 6 ? 'green' : overview.runway_months > 2 ? 'yellow' : 'red')
              : 'neutral'}
          />
          <KpiCard
            label="Offene Debitoren"
            value={formatCHF(overview?.open_invoices_total)}
            sublabel={overview?.dso_days != null ? `DSO: ${overview.dso_days} Tage` : `${overview?.open_invoices_count ?? 0} Rechnungen`}
            icon={<InvoiceIcon />}
            status={overview?.dso_days != null
              ? (overview.dso_days <= 30 ? 'green' : overview.dso_days <= 60 ? 'yellow' : 'red')
              : 'neutral'}
          />
          <KpiCard
            label="Lfd. Monat (Toggl)"
            value={formatCHF(overview?.current_month_revenue)}
            sublabel={`${overview?.current_month_hours ?? 0}h erfasst`}
            icon={<ClockIcon />}
            status="neutral"
          />
          <KpiCard
            label="Prog. Jahresumsatz (brutto)"
            value={formatCHF(overview?.forecast_year_revenue)}
            sublabel={overview?.revenue_ytd_prior
              ? `YTD: ${formatCHF(overview?.revenue_ytd_net)} · ${formatYoyDelta(overview?.revenue_ytd ?? 0, overview.revenue_ytd_prior)}`
              : `YTD netto: ${formatCHF(overview?.revenue_ytd_net)}`}
            icon={<TrendIcon />}
            status={overview?.forecast_year_revenue && overview.forecast_year_revenue > 0 ? 'green' : 'neutral'}
          />
          <KpiCard
            label="EBITDA YTD"
            value={formatCHF(overview?.ebitda_ytd)}
            sublabel={overview?.ebitda_ytd_prior != null
              ? `VJ: ${formatCHF(overview.ebitda_ytd_prior)} · ${formatYoyDelta(overview?.ebitda_ytd ?? 0, overview.ebitda_ytd_prior)}`
              : overview?.revenue_ytd_net
                ? `${((overview.ebitda_ytd ?? 0) / overview.revenue_ytd_net * 100).toFixed(1)}% Marge`
                : '–'}
            icon={<CashflowIcon />}
            status={overview?.ebitda_ytd != null
              ? (overview.ebitda_ytd > 0 ? 'green' : 'red')
              : 'neutral'}
          />
          <KpiCard
            label="Personalquote"
            value={overview?.personalquote_ytd != null ? `${overview.personalquote_ytd}%` : '–'}
            sublabel={overview?.personalquote_ytd_prior != null
              ? `VJ: ${overview.personalquote_ytd_prior}%`
              : 'Personalaufwand / Netto-Ertrag'}
            icon={<ClockIcon />}
            status={overview?.personalquote_ytd != null
              ? (overview.personalquote_ytd <= 70 ? 'green' : overview.personalquote_ytd <= 85 ? 'yellow' : 'red')
              : 'neutral'}
          />
          <KpiCard
            label="Cashflow Ende Jahr"
            value={formatCHF(overview?.forecast_year_end_cashflow)}
            sublabel="Prognose Dezember"
            icon={<TrendIcon />}
            status={overview?.forecast_year_end_cashflow != null
              ? (overview.forecast_year_end_cashflow > 0 ? 'green' : 'red')
              : 'neutral'}
          />
          <KpiCard
            label="Runway"
            value={overview?.runway_months != null ? `${overview.runway_months} Mt.` : '–'}
            sublabel={overview?.runway_months_incl_debtors != null
              ? `inkl. Debitoren: ${overview.runway_months_incl_debtors} Mt.`
              : `Burn Rate: ${formatCHF(overview?.burn_rate)}/Mt.`}
            icon={<RunwayIcon />}
            status={overview?.runway_months != null
              ? (overview.runway_months > 6 ? 'green' : overview.runway_months > 2 ? 'yellow' : 'red')
              : 'neutral'}
          />
          <KpiCard
            label="Gewinnmarge YTD"
            value={overview?.profit_margin_ytd != null ? `${overview.profit_margin_ytd}%` : '–'}
            sublabel={overview?.profit_margin_ytd_prior != null
              ? `VJ: ${overview.profit_margin_ytd_prior}%`
              : `Aufwand YTD: ${formatCHF(overview?.expenses_ytd)}`}
            icon={<CashflowIcon />}
            status={overview?.profit_margin_ytd != null
              ? (overview.profit_margin_ytd >= 10 ? 'green' : overview.profit_margin_ytd >= 0 ? 'yellow' : 'red')
              : 'neutral'}
          />
        </div>

        {/* Cashflow-Chart: Dreistufig (Operativ / Finanzierung / Investition) */}
        {cashflow && cashflow.months.length > 0 && (
          <div className={`mb-6 ${sectionClass}`}>
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
              Cashflow (direkte Methode)
            </h2>
            <ResponsiveContainer width="100%" height={380}>
              <ComposedChart data={cashflow.months.map(m => ({
                ...m,
                label: formatMonthLabel(m.month),
                opNeg: -m.expenses,
                finNeg: -(m.fin_outflow || 0),
                invNeg: -(m.invest_outflow || 0),
                hasSpecial: (m.special_items?.length ?? 0) > 0,
              }))}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${formatK(v)}`} />
                <Tooltip
                  cursor={CURSOR_STYLE}
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0]?.payload;
                    if (!d) return null;
                    const items = d.special_items || [];
                    return (
                      <div className="rounded-lg border border-gray-700 bg-gray-800 p-3 text-xs text-gray-100 shadow-lg">
                        <p className="mb-2 font-semibold text-white">{label}</p>
                        <div className="space-y-1">
                          <div className="flex justify-between gap-4">
                            <span className="text-green-400">Einnahmen (brutto)</span>
                            <span className="font-medium">{formatCHF(d.revenue)}</span>
                          </div>
                          <div className="flex justify-between gap-4">
                            <span className="text-red-400">Operativ</span>
                            <span className="font-medium">-{formatCHF(d.expenses)}</span>
                          </div>
                          {d.fin_outflow > 0 && (
                            <div className="flex justify-between gap-4">
                              <span className="text-orange-400">Finanzierung</span>
                              <span className="font-medium">-{formatCHF(d.fin_outflow)}</span>
                            </div>
                          )}
                          {d.invest_outflow > 0 && (
                            <div className="flex justify-between gap-4">
                              <span className="text-gray-400">Investitionen</span>
                              <span className="font-medium">-{formatCHF(d.invest_outflow)}</span>
                            </div>
                          )}
                          {items.length > 0 && (
                            <>
                              <hr className="my-1 border-gray-600" />
                              <p className="text-[10px] font-medium text-gray-400">Sonderposten:</p>
                              {items.map((si: CashflowSpecialItem, idx: number) => (
                                <div key={idx} className="flex justify-between gap-4 text-[11px]">
                                  <span className="text-gray-400">{si.label}</span>
                                  <span className="font-medium text-orange-400">{formatCHF(si.amount)}</span>
                                </div>
                              ))}
                            </>
                          )}
                          <hr className="my-1 border-gray-600" />
                          <div className="flex justify-between gap-4 font-semibold">
                            <span className={d.delta >= 0 ? 'text-green-400' : 'text-red-400'}>Delta</span>
                            <span>{d.delta >= 0 ? '+' : ''}{formatCHF(d.delta)}</span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                {avgRevenue > 0 && (
                  <ReferenceLine
                    y={avgRevenue}
                    stroke="#22c55e"
                    strokeDasharray="6 4"
                    label={{ value: `Ø ${formatK(avgRevenue)}`, position: 'insideTopRight', fontSize: 10, fill: '#22c55e' }}
                  />
                )}
                {avgExpenses > 0 && (
                  <ReferenceLine
                    y={-avgExpenses}
                    stroke="#ef4444"
                    strokeDasharray="6 4"
                    label={{ value: `Ø -${formatK(avgExpenses)}`, position: 'insideBottomRight', fontSize: 10, fill: '#ef4444' }}
                  />
                )}
                {avgRevenuePrior > 0 && (
                  <ReferenceLine
                    y={avgRevenuePrior}
                    stroke="#94a3b8"
                    strokeDasharray="4 4"
                    label={{ value: `Ø VJ: ${formatK(avgRevenuePrior)}`, position: 'insideTopLeft', fontSize: 9, fill: '#94a3b8' }}
                  />
                )}
                <ReferenceLine
                  x={formatMonthLabel(currentMonth)}
                  stroke="#6366f1"
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  label={{ value: '▼ Heute', fontSize: 11, fill: '#6366f1', position: 'top' }}
                />
                <Bar dataKey="revenue" name="revenue" radius={[4, 4, 0, 0]}>
                  {cashflow.months.map((m, i) => (
                    <Cell
                      key={i}
                      fill={m.is_forecast ? '#86efac80' : '#22c55e'}
                      stroke={m.is_forecast ? '#86efac' : undefined}
                      strokeDasharray={m.is_forecast ? '4 2' : undefined}
                    />
                  ))}
                  <LabelList
                    dataKey="revenue"
                    position="top"
                    fontSize={9}
                    fill="#16a34a"
                    formatter={(v: number) => v > 0 ? formatK(v) : ''}
                  />
                </Bar>
                <Bar dataKey="opNeg" name="opNeg" stackId="out" radius={[0, 0, 0, 0]}>
                  {cashflow.months.map((m, i) => (
                    <Cell
                      key={i}
                      fill={m.is_forecast ? '#fca5a580' : '#ef4444'}
                      stroke={m.is_forecast ? '#fca5a5' : undefined}
                      strokeDasharray={m.is_forecast ? '4 2' : undefined}
                    />
                  ))}
                </Bar>
                <Bar dataKey="finNeg" name="finNeg" stackId="out" fill="#f97316" radius={[0, 0, 0, 0]}>
                  {cashflow.months.map((m, i) => (
                    <Cell key={i} fill={(m.fin_outflow || 0) > 0 ? '#f97316' : 'transparent'} />
                  ))}
                </Bar>
                <Bar dataKey="invNeg" name="invNeg" stackId="out" fill="#9ca3af" radius={[0, 0, 4, 4]}>
                  {cashflow.months.map((m, i) => (
                    <Cell key={i} fill={(m.invest_outflow || 0) > 0 ? '#9ca3af' : 'transparent'} />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded bg-green-500" /> Einnahmen (brutto)</span>
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded bg-red-500" /> Operativ</span>
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded bg-orange-500" /> Finanzierung</span>
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded bg-gray-400" /> Investitionen</span>
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded border-2 border-dashed border-green-300 bg-green-200/50" /> Prognose</span>
            </div>
          </div>
        )}

        {/* 2-Spalten: Vorjahresvergleich + Kostenstruktur */}
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {/* Vorjahresvergleich */}
          {yoy && (
            <div className={sectionClass}>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Vorjahresvergleich (brutto)</h2>
                {yoy.growth_pct != null && (
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                    yoy.growth_pct >= 0
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  }`}>
                    {yoy.growth_pct >= 0 ? '+' : ''}{yoy.growth_pct}% YTD
                  </span>
                )}
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={yoy.months.filter(m => m.revenue_current > 0 || m.revenue_prior > 0)}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="month_label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => formatK(v)} />
                  <Tooltip
                    formatter={(value: number, name: string) => {
                      const labels: Record<string, string> = {
                        revenue_current: `Umsatz ${yoy.current_year} (brutto)`,
                        revenue_prior: `Umsatz ${yoy.prior_year} (brutto)`,
                      };
                      return [formatCHF(value), labels[name] || name];
                    }}
                    contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE}
                  />
                  <Legend
                    formatter={(value: string) => {
                      if (value === 'revenue_current') return `${yoy.current_year}`;
                      if (value === 'revenue_prior') return `${yoy.prior_year}`;
                      return value;
                    }}
                    wrapperStyle={{ fontSize: '0.75rem' }}
                  />
                  <Bar dataKey="revenue_prior" name="revenue_prior" fill="#c7d2fe" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="revenue_current" name="revenue_current" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Kostenstruktur: Stacked Bar (Monatsvergleich) */}
          {costBarData.data.length > 0 && expenseBreakdown && (
            <div className={sectionClass}>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
                Kostenstruktur {expenseBreakdown.current_year} vs. {expenseBreakdown.prior_year}
              </h2>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={costBarData.data.filter(d => (d._total_cur as number) > 0 || (d._total_prior as number) > 0)}
                  barCategoryGap="15%"
                  barGap={2}
                >
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="_label_cur" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => formatK(v)} />
                  <Tooltip
                    cursor={CURSOR_STYLE}
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0]?.payload;
                      if (!d) return null;
                      return (
                        <div className="rounded-lg border border-gray-700 bg-gray-800 p-3 text-xs text-gray-100 shadow-lg">
                          <p className="mb-2 font-semibold text-white">{label}</p>
                          <div className="space-y-0.5">
                            {costBarData.keys.filter(k => (d[`cur_${k}`] || 0) > 0).map((k) => (
                              <div key={k} className="flex justify-between gap-4">
                                <span className="text-gray-400">{costBarData.labels[k] || k}</span>
                                <span className="font-medium">{formatCHF(d[`cur_${k}`])}</span>
                              </div>
                            ))}
                            <hr className="my-1 border-gray-600" />
                            <div className="flex justify-between gap-4 font-semibold">
                              <span>Total</span>
                              <span>{formatCHF(d._total_cur)}</span>
                            </div>
                          </div>
                        </div>
                      );
                    }}
                  />
                  {costBarData.keys.slice(0, 8).map((k, i) => (
                    <Bar key={`cur_${k}`} dataKey={`cur_${k}`} stackId="cur" name={costBarData.labels[k] || k}
                      fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                      radius={i === 0 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-gray-500 dark:text-gray-400">
                {costBarData.keys.slice(0, 8).map((k, i) => (
                  <span key={k} className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }} />
                    {costBarData.labels[k] || k}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 2-Spalten: P&L Wasserfall + Gewinnmarge-Trend */}
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {/* P&L Wasserfall */}
          {waterfall && waterfallChartData.length > 0 && (
            <div className={sectionClass}>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Erfolgsrechnung {waterfall.period_label} (netto)
                </h2>
                <div className="flex items-center gap-2">
                  <select
                    value={pnlPeriod}
                    onChange={async (e) => {
                      const p = e.target.value;
                      setPnlPeriod(p);
                      try {
                        const wf = await api.get<WaterfallResponse>(`/api/finance/pnl-waterfall?period=${p}`);
                        setWaterfall(wf);
                      } catch { /* ignore */ }
                    }}
                    className="rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-300"
                  >
                    <option value="ytd">YTD {new Date().getFullYear()}</option>
                    {(() => {
                      const y = new Date().getFullYear();
                      const m = new Date().getMonth() + 1;
                      const names = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
                      const opts = [];
                      for (let i = m; i >= 1; i--) {
                        opts.push(<option key={`${y}-${i}`} value={`${y}-${String(i).padStart(2, '0')}`}>{names[i]} {y}</option>);
                      }
                      for (let i = 12; i >= Math.max(1, 12 - 3); i--) {
                        opts.push(<option key={`${y - 1}-${i}`} value={`${y - 1}-${String(i).padStart(2, '0')}`}>{names[i]} {y - 1}</option>);
                      }
                      return opts;
                    })()}
                  </select>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                    waterfall.result >= 0
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  }`}>
                    {formatCHF(waterfall.result)}
                  </span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={waterfallChartData} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => formatK(v)} />
                  <Tooltip
                    formatter={(value: number, name: string) => {
                      if (name === 'base') return [null, null];
                      return [formatCHF(value), 'Betrag'];
                    }}
                    contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE}
                  />
                  <Bar dataKey="base" stackId="stack" fill="transparent" />
                  <Bar dataKey="bar" stackId="stack" radius={[4, 4, 0, 0]}>
                    {waterfallChartData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={entry.type === 'income' ? '#22c55e' : entry.type === 'total' ? '#6366f1' : '#ef4444'}
                      />
                    ))}
                    <LabelList
                      dataKey="value"
                      position="top"
                      fontSize={9}
                      formatter={(v: number) => formatK(v)}
                      fill="#6b7280"
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Gewinnmarge-Trend (YTD-kumuliert + VJ-Benchmark) */}
          {marginTrend && marginTrend.months.length > 1 && (
            <div className={sectionClass}>
              <div className="mb-4 flex items-center justify-between">
                <h2 className={`text-lg font-semibold ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
                  Gewinnmarge YTD
                </h2>
                {overview?.profit_margin_ytd != null && (
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                    overview.profit_margin_ytd >= 0
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  }`}>
                    {overview.profit_margin_ytd}%
                  </span>
                )}
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={marginTrend.months}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${v}%`} domain={['auto', 'auto']} />
                  <Tooltip
                    formatter={(value: number | null, name: string) => {
                      if (value == null) return ['–', ''];
                      const labels: Record<string, string> = {
                        ytd_margin: `YTD ${marginTrend.current_year}`,
                        ytd_margin_prior: `YTD ${marginTrend.prior_year}`,
                        rolling_12m_margin: '12-Mt. Rolling',
                      };
                      return [`${value}%`, labels[name] || name];
                    }}
                    contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE}
                  />
                  <Legend
                    formatter={(value: string) => {
                      const labels: Record<string, string> = {
                        ytd_margin: `YTD ${marginTrend.current_year}`,
                        ytd_margin_prior: `VJ ${marginTrend.prior_year}`,
                        rolling_12m_margin: '12-Mt. Rolling',
                      };
                      return labels[value] || value;
                    }}
                    wrapperStyle={{ fontSize: '0.7rem' }}
                  />
                  <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: 'Break-Even', fontSize: 10, fill: '#94a3b8' }} />
                  <Line
                    type="monotone"
                    dataKey="ytd_margin"
                    stroke="#6366f1"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: '#6366f1', stroke: '#fff', strokeWidth: 2 }}
                    activeDot={{ r: 6 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="ytd_margin_prior"
                    stroke="#94a3b8"
                    strokeWidth={1.5}
                    strokeDasharray="6 4"
                    dot={{ r: 3, fill: '#94a3b8', stroke: '#fff', strokeWidth: 1 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="rolling_12m_margin"
                    stroke="#22c55e"
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Quell-Karten */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <SourceCard title="Bexio" subtitle="Buchhaltung" color="blue" linkUrl="https://office.bexio.com" linkLabel="Bexio öffnen">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Banksaldo</span>
                <span className="font-medium text-gray-900 dark:text-white">{formatCHF(overview?.bank_balance)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Umsatz YTD (brutto)</span>
                <span className="font-medium text-gray-900 dark:text-white">{formatCHF(overview?.revenue_ytd)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Umsatz YTD (netto)</span>
                <span className="font-medium text-gray-900 dark:text-white">{formatCHF(overview?.revenue_ytd_net)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">EBITDA YTD</span>
                <span className={`font-medium ${(overview?.ebitda_ytd ?? 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
                  {formatCHF(overview?.ebitda_ytd)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Personalquote</span>
                <span className={`font-medium ${(overview?.personalquote_ytd ?? 0) <= 80 ? 'text-green-600 dark:text-green-400' : 'text-amber-500'}`}>
                  {overview?.personalquote_ytd != null ? `${overview.personalquote_ytd}%` : '–'}
                </span>
              </div>
            </div>
          </SourceCard>

          <SourceCard title="Toggl Track" subtitle="Leistungserfassung" color="violet" linkUrl="https://track.toggl.com" linkLabel="Toggl öffnen">
            {togglProjects.length === 0 ? (
              <p className="text-sm text-gray-400">Keine Daten für diesen Monat</p>
            ) : (
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1 text-sm">
                {togglProjects.slice(0, 5).map((p, i) => (
                  <React.Fragment key={i}>
                    <span className="truncate text-gray-600 dark:text-gray-300">
                      {p.client_name ? `${p.client_name} – ` : ''}{p.project_name}
                    </span>
                    <span className="text-right text-xs text-gray-400 tabular-nums">{p.hours}h</span>
                    <span className="text-right font-medium text-gray-900 tabular-nums dark:text-white">{formatCHF(p.amount)}</span>
                  </React.Fragment>
                ))}
              </div>
            )}
          </SourceCard>

          <InvoiceInsightPreview />
        </div>

        {/* Detailtabelle */}
        {cashflow && (
          <div className={`rounded-2xl ${cardClass}`}>
            <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700 sm:px-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Monatsübersicht</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <th className="px-4 py-3 sm:px-6">Monat</th>
                    <th className="px-4 py-3 text-right sm:px-6">Einnahmen (brutto)</th>
                    <th className="px-4 py-3 text-right sm:px-6">Operativ</th>
                    <th className="hidden px-4 py-3 text-right sm:table-cell sm:px-6">Finanz.</th>
                    <th className="px-4 py-3 text-right sm:px-6">Delta</th>
                    <th className="px-4 py-3 text-right sm:px-6">Kum. Saldo</th>
                    <th className="px-4 py-3 sm:px-6"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                  {cashflow.months.map((m) => {
                    const hasSpecials = (m.special_items?.length ?? 0) > 0;
                    return (
                      <React.Fragment key={m.month}>
                        <tr
                          className={`transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/40 ${
                            m.month === currentMonth ? 'bg-indigo-50/50 dark:bg-indigo-950/20'
                              : m.is_forecast ? 'bg-amber-50/30 dark:bg-amber-950/10' : ''
                          }`}
                        >
                          <td className="whitespace-nowrap px-4 py-2.5 font-medium text-gray-900 dark:text-white sm:px-6">
                            {formatMonthLabel(m.month)}
                            {m.is_forecast && (
                              <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">
                                Schätzung
                              </span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-right text-green-600 dark:text-green-400 sm:px-6">
                            {formatCHF(m.revenue)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-right text-red-500 dark:text-red-400 sm:px-6">
                            {formatCHF(m.expenses)}
                          </td>
                          <td className="hidden whitespace-nowrap px-4 py-2.5 text-right text-orange-500 sm:table-cell sm:px-6">
                            {(m.fin_outflow || 0) > 0 ? formatCHF(m.fin_outflow) : '–'}
                          </td>
                          <td className={`whitespace-nowrap px-4 py-2.5 text-right font-medium sm:px-6 ${
                            m.delta >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'
                          }`}>
                            {m.delta >= 0 ? '+' : ''}{formatCHF(m.delta)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-right font-semibold text-gray-900 dark:text-white sm:px-6">
                            {formatCHF(m.cumulative)}
                          </td>
                          <td className="px-4 py-2.5 sm:px-6">
                            {m.month === currentMonth && (
                              <span className="inline-block h-2 w-2 rounded-full bg-indigo-500" title="Aktueller Monat" />
                            )}
                          </td>
                        </tr>
                        {hasSpecials && (
                          <tr className="bg-orange-50/40 dark:bg-orange-950/10">
                            <td colSpan={7} className="px-8 py-1.5 sm:px-10">
                              <div className="flex flex-wrap gap-x-5 gap-y-0.5 text-xs text-orange-600 dark:text-orange-400">
                                {m.special_items.map((si, idx) => (
                                  <span key={idx}>
                                    {si.label}: {formatCHF(si.amount)}
                                  </span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {loading && !cashflow && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
          </div>
        )}
      </div>

      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={bgUrl}
        onSelect={(url) => { handleBgSelect(url); setBgPickerOpen(false); }}
      />
    </div>
  );
}

// ── Sub-Komponenten ─────────────────────────────────

function KpiCard({
  label, value, sublabel, icon, status = 'neutral',
}: {
  label: string; value: string; sublabel: string; icon: React.ReactNode;
  status?: 'green' | 'yellow' | 'red' | 'neutral';
}) {
  const statusColors: Record<string, string> = {
    green: 'border-l-green-500',
    yellow: 'border-l-amber-500',
    red: 'border-l-red-500',
    neutral: 'border-l-gray-200 dark:border-l-gray-700',
  };
  return (
    <div className={`rounded-xl border border-gray-200 border-l-4 ${statusColors[status]} bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50`}>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-50 text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</p>
          <p className="truncate text-lg font-bold text-gray-900 dark:text-white">{value}</p>
          <p className="truncate text-xs text-gray-400 dark:text-gray-500">{sublabel}</p>
        </div>
      </div>
    </div>
  );
}

function SourceCard({
  title, subtitle, color, linkUrl, linkLabel, comingSoon, children,
}: {
  title: string; subtitle: string; color: string;
  linkUrl?: string; linkLabel?: string; comingSoon?: boolean;
  children: React.ReactNode;
}) {
  const borderColors: Record<string, string> = {
    blue: 'border-t-blue-500',
    violet: 'border-t-violet-500',
    rose: 'border-t-rose-400',
  };
  return (
    <div className={`rounded-2xl border border-gray-200 border-t-4 ${borderColors[color] || 'border-t-gray-400'} bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50`}>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
        </div>
        {comingSoon && (
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            Coming Soon
          </span>
        )}
      </div>
      {children}
      {linkUrl && (
        <a
          href={linkUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-600 transition-colors hover:text-indigo-500 dark:text-indigo-400"
        >
          {linkLabel || 'Öffnen'}
          <ExternalLinkIcon className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

// ── Icons ────────────────────────────────────────────

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
    </svg>
  );
}

function BankIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0 1 15.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 0 1 3 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 0 0-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 0 1-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 0 0 3 15h-.75M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3 0h.008v.008H18V10.5Zm-12 0h.008v.008H6V10.5Z" />
    </svg>
  );
}

function InvoiceIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function TrendIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.518l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941" />
    </svg>
  );
}

function CashflowIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
    </svg>
  );
}

function RunwayIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.91 11.672a.375.375 0 0 1 0 .656l-5.603 3.113a.375.375 0 0 1-.557-.328V8.887c0-.286.307-.466.557-.327l5.603 3.112Z" />
    </svg>
  );
}

function BgImageIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Zm6-13.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Z" />
    </svg>
  );
}

function ExternalLinkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  );
}

function InvoiceInsightPreview() {
  const [kpis, setKpis] = useState<Record<string, unknown> | null>(null);
  const [upcoming, setUpcoming] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    api.get<{ kpis: Record<string, unknown> }>('/api/creditors/dashboard')
      .then(d => setKpis(d.kpis))
      .catch(() => {});
    api.get<unknown>('/api/creditors/upcoming?n=3')
      .then(data => {
        const raw = Array.isArray(data) ? data : (data as Record<string, unknown>)?.payments as Record<string, unknown>[] || [];
        setUpcoming(raw.map((p: Record<string, unknown>) => ({
          vendor: (p.vendor ?? p.Kreditor ?? '–') as string,
          amount_chf: (p.amount_chf ?? p.Betrag_CHF) as number | undefined,
        })));
      })
      .catch(() => {});
  }, []);

  const totalVol = (kpis?.total_spend_chf ?? kpis?.total_volume_chf ?? kpis?.total_volume ?? 0) as number;
  const invoiceN = (kpis?.invoice_count ?? kpis?.total_invoices ?? 0) as number;

  return (
    <SourceCard title="InvoiceInsight" subtitle="Kreditorenrechnungen" color="rose" linkUrl="/kreditoren" linkLabel="Kreditoren öffnen">
      {kpis ? (
        <div className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Gesamtausgaben</span>
            <span className="font-medium text-gray-900 dark:text-white">{formatCHF(totalVol)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">Rechnungen</span>
            <span className="font-medium text-gray-900 dark:text-white">{invoiceN}</span>
          </div>
          {upcoming.length > 0 && (
            <>
              <div className="border-t border-gray-200 pt-2 dark:border-gray-700">
                <p className="mb-1 text-xs font-medium text-gray-400">Nächste Zahlungen:</p>
                {upcoming.map((p, i) => (
                  <div key={i} className="flex justify-between text-xs">
                    <span className="text-gray-600 dark:text-gray-300">{(p.vendor as string) || '–'}</span>
                    <span className="font-medium text-gray-900 dark:text-white">
                      {p.amount_chf != null ? formatCHF(p.amount_chf as number) : '–'}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <p className="py-2 text-center text-sm text-gray-400">Laden...</p>
      )}
    </SourceCard>
  );
}
