import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell, ComposedChart,
  PieChart, Pie, LineChart, Line, LabelList, Legend,
} from 'recharts';
import { api } from '../api/client';

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
  journal_data_from: string | null;
  journal_data_to: string | null;
  currency: string;
}

interface CashflowMonth {
  month: string;
  revenue: number;
  expenses: number;
  delta: number;
  cumulative: number;
  is_forecast: boolean;
}

interface CashflowResponse {
  months: CashflowMonth[];
  forecast_revenue_monthly: number;
  forecast_expenses_monthly: number;
  start_balance: number;
}

interface TogglProject {
  project_name: string;
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

interface ExpenseCat {
  key: string;
  label: string;
  total_12m: number;
  monthly_average: number;
  recurrence: string;
}

interface ExpenseCatResponse {
  categories: ExpenseCat[];
  period_from: string;
  period_to: string;
  months_covered: number;
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

// ── Formatierung ────────────────────────────────────

function formatCHF(value: number | null | undefined): string {
  if (value == null) return '–';
  return new Intl.NumberFormat('de-CH', { style: 'currency', currency: 'CHF' }).format(value);
}

function formatK(value: number): string {
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(0)}k`;
  return value.toFixed(0);
}

function formatMonthLabel(month: string): string {
  const [y, m] = month.split('-');
  const names = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  return `${names[parseInt(m)]} ${y.slice(2)}`;
}

const DONUT_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6',
  '#14b8a6', '#f97316', '#ec4899', '#06b6d4', '#84cc16',
  '#d946ef', '#0ea5e9', '#a3e635',
];

// ── Hauptkomponente ─────────────────────────────────

export function FinancePage() {
  const [overview, setOverview] = useState<KpiOverview | null>(null);
  const [cashflow, setCashflow] = useState<CashflowResponse | null>(null);
  const [togglProjects, setTogglProjects] = useState<TogglProject[]>([]);
  const [yoy, setYoy] = useState<YoyResponse | null>(null);
  const [expenseCats, setExpenseCats] = useState<ExpenseCat[]>([]);
  const [expensePeriod, setExpensePeriod] = useState({ from: '', to: '', months: 0 });
  const [waterfall, setWaterfall] = useState<WaterfallResponse | null>(null);
  const [pnlPeriod, setPnlPeriod] = useState('ytd');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async (wfPeriod = 'ytd') => {
    setLoading(true);
    setError(null);
    try {
      const [ov, cf, tp, yoyR, ec, wf] = await Promise.allSettled([
        api.get<KpiOverview>('/api/finance/overview'),
        api.get<CashflowResponse>('/api/finance/cashflow?months_back=6&months_forward=12'),
        api.get<TogglProject[]>('/api/finance/toggl-summary'),
        api.get<YoyResponse>('/api/finance/yoy'),
        api.get<ExpenseCatResponse>('/api/finance/expense-categories'),
        api.get<WaterfallResponse>(`/api/finance/pnl-waterfall?period=${wfPeriod}`),
      ]);
      if (ov.status === 'fulfilled') setOverview(ov.value);
      if (cf.status === 'fulfilled') setCashflow(cf.value);
      if (tp.status === 'fulfilled') setTogglProjects(tp.value);
      if (yoyR.status === 'fulfilled') setYoy(yoyR.value);
      if (ec.status === 'fulfilled') {
        const resp = ec.value;
        setExpenseCats(resp.categories);
        setExpensePeriod({ from: resp.period_from, to: resp.period_to, months: resp.months_covered });
      }
      if (wf.status === 'fulfilled') setWaterfall(wf.value);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Laden fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleRefresh = async () => {
    try {
      await api.post('/api/finance/cache/clear', {});
      await api.post('/api/bexio/cache/clear', {});
      await api.post('/api/toggl/cache/clear', {});
    } catch { /* ignore */ }
    loadData();
  };

  const currentMonth = new Date().toISOString().slice(0, 7);

  // Durchschnittswerte fuer Referenzlinien
  const avgRevenue = cashflow?.forecast_revenue_monthly ?? 0;
  const avgExpenses = cashflow?.forecast_expenses_monthly ?? 0;

  // Marge-Trend: 3-Monats-rollierender Durchschnitt
  const marginData = useMemo(() => {
    if (!cashflow) return [];
    const hist = cashflow.months.filter(m => !m.is_forecast && m.revenue > 0);
    return hist.map((m, i) => {
      const window = hist.slice(Math.max(0, i - 2), i + 1);
      const avgRev = window.reduce((s, w) => s + w.revenue, 0) / window.length;
      const avgExp = window.reduce((s, w) => s + w.expenses, 0) / window.length;
      return {
        label: formatMonthLabel(m.month),
        margin: avgRev > 0 ? Math.round((avgRev - avgExp) / avgRev * 100) : 0,
      };
    });
  }, [cashflow]);

  // Donut-Daten: Monatsdurchschnitt statt Total
  const donutData = useMemo(() => {
    return expenseCats
      .filter(c => c.monthly_average > 0)
      .map((c, i) => ({
        name: c.label,
        value: Math.round(c.monthly_average),
        fill: DONUT_COLORS[i % DONUT_COLORS.length],
      }));
  }, [expenseCats]);

  const donutTotal = useMemo(() => donutData.reduce((s, d) => s + d.value, 0), [donutData]);

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
    <div className="relative flex h-full flex-col">
      <div className="relative z-10 flex-1 overflow-y-auto overflow-x-hidden overscroll-x-none p-4 sm:p-6">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Finanz-Controlling</h1>
            {overview && (
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Datenstand: Journal{' '}
                {overview.journal_data_from && overview.journal_data_to
                  ? `${formatMonthLabel(overview.journal_data_from.slice(0, 7))} – ${formatMonthLabel(overview.journal_data_to.slice(0, 7))}`
                  : '–'}
                {` · Toggl: live · Aktualisiert: ${new Date().toLocaleString('de-CH')}`}
              </p>
            )}
            {!overview && (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Cashflow-Übersicht, Prognosen und Kostenanalyse
              </p>
            )}
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <RefreshIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </button>
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
            label="Prog. Jahresumsatz"
            value={formatCHF(overview?.forecast_year_revenue)}
            sublabel={`YTD netto: ${formatCHF(overview?.revenue_ytd_net)}`}
            icon={<TrendIcon />}
            status={overview?.forecast_year_revenue && overview.forecast_year_revenue > 0 ? 'green' : 'neutral'}
          />
          <KpiCard
            label="EBITDA YTD"
            value={formatCHF(overview?.ebitda_ytd)}
            sublabel={overview?.revenue_ytd_net
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
            sublabel="Personalaufwand / Netto-Ertrag"
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
            sublabel={`Aufwand YTD: ${formatCHF(overview?.expenses_ytd)}`}
            icon={<CashflowIcon />}
            status={overview?.profit_margin_ytd != null
              ? (overview.profit_margin_ytd >= 10 ? 'green' : overview.profit_margin_ytd >= 0 ? 'yellow' : 'red')
              : 'neutral'}
          />
        </div>

        {/* Cashflow-Chart (verbessert) */}
        {cashflow && cashflow.months.length > 0 && (
          <div className="mb-6 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50 sm:p-6">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
              Einnahmen vs. Ausgaben
            </h2>
            <ResponsiveContainer width="100%" height={350}>
              <ComposedChart data={cashflow.months.map(m => ({
                ...m,
                label: formatMonthLabel(m.month),
                expensesNeg: -m.expenses,
              }))}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${formatK(v)}`} />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    const labels: Record<string, string> = {
                      revenue: 'Einnahmen',
                      expensesNeg: 'Ausgaben',
                    };
                    return [formatCHF(Math.abs(value)), labels[name] || name];
                  }}
                  labelFormatter={(label: string) => label}
                  contentStyle={{ borderRadius: '0.5rem', fontSize: '0.8rem' }}
                />
                {avgRevenue > 0 && (
                  <ReferenceLine
                    y={avgRevenue}
                    stroke="#22c55e"
                    strokeDasharray="6 4"
                    label={{ value: `Ø ${formatCHF(avgRevenue)}`, position: 'right', fontSize: 10, fill: '#22c55e' }}
                  />
                )}
                {avgExpenses > 0 && (
                  <ReferenceLine
                    y={-avgExpenses}
                    stroke="#ef4444"
                    strokeDasharray="6 4"
                    label={{ value: `Ø -${formatCHF(avgExpenses)}`, position: 'right', fontSize: 10, fill: '#ef4444' }}
                  />
                )}
                <ReferenceLine x={formatMonthLabel(currentMonth)} stroke="#6366f1" strokeDasharray="4 4" label={{ value: 'Heute', fontSize: 11, fill: '#6366f1' }} />
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
                <Bar dataKey="expensesNeg" name="expensesNeg" radius={[0, 0, 4, 4]}>
                  {cashflow.months.map((m, i) => (
                    <Cell
                      key={i}
                      fill={m.is_forecast ? '#fca5a580' : '#ef4444'}
                      stroke={m.is_forecast ? '#fca5a5' : undefined}
                      strokeDasharray={m.is_forecast ? '4 2' : undefined}
                    />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded bg-green-500" /> Einnahmen</span>
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded bg-red-500" /> Ausgaben</span>
              <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded border-2 border-dashed border-green-300 bg-green-200/50" /> Prognose</span>
              <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-green-500" /> Ø Einnahmen</span>
              <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-red-500" /> Ø Ausgaben</span>
            </div>
          </div>
        )}

        {/* 2-Spalten: Vorjahresvergleich + Kostenstruktur */}
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {/* Vorjahresvergleich */}
          {yoy && (
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50 sm:p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Vorjahresvergleich</h2>
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
                        revenue_current: `Umsatz ${yoy.current_year}`,
                        revenue_prior: `Umsatz ${yoy.prior_year}`,
                      };
                      return [formatCHF(value), labels[name] || name];
                    }}
                    contentStyle={{ borderRadius: '0.5rem', fontSize: '0.8rem' }}
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

          {/* Kostenstruktur-Donut */}
          {donutData.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50 sm:p-6">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
                Kostenstruktur Ø/Mt.
                {expensePeriod.from && expensePeriod.to && (
                  <span className="ml-2 text-xs font-normal text-gray-400">
                    ({formatMonthLabel(expensePeriod.from)} – {formatMonthLabel(expensePeriod.to)}, {expensePeriod.months} Mt.)
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-4">
                <div className="relative">
                  <ResponsiveContainer width={200} height={200}>
                    <PieChart>
                      <Pie
                        data={donutData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={90}
                        dataKey="value"
                        stroke="none"
                      >
                        {donutData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: number) => [formatCHF(value), 'Ø/Mt.']} contentStyle={{ borderRadius: '0.5rem', fontSize: '0.8rem' }} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center">
                      <p className="text-xs text-gray-400">Ø/Mt.</p>
                      <p className="text-sm font-bold text-gray-900 dark:text-white">{formatK(donutTotal)}</p>
                    </div>
                  </div>
                </div>
                <div className="flex-1 space-y-1.5 overflow-hidden">
                  {donutData.slice(0, 8).map((d, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: d.fill }} />
                      <span className="truncate text-gray-600 dark:text-gray-300">{d.name}</span>
                      <span className="ml-auto shrink-0 font-medium text-gray-900 dark:text-white">{formatCHF(d.value)}</span>
                    </div>
                  ))}
                  {donutData.length > 8 && (
                    <p className="text-[10px] text-gray-400">+{donutData.length - 8} weitere</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 2-Spalten: P&L Wasserfall + Gewinnmarge-Trend */}
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {/* P&L Wasserfall */}
          {waterfall && waterfallChartData.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50 sm:p-6">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Erfolgsrechnung {waterfall.period_label}
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
                    contentStyle={{ borderRadius: '0.5rem', fontSize: '0.8rem' }}
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

          {/* Gewinnmarge-Trend */}
          {marginData.length > 1 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/50 sm:p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Gewinnmarge (3-Mt. Ø)</h2>
                {overview?.profit_margin_ytd != null && (
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                    overview.profit_margin_ytd >= 0
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  }`}>
                    YTD: {overview.profit_margin_ytd}%
                  </span>
                )}
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={marginData}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${v}%`} domain={['auto', 'auto']} />
                  <Tooltip
                    formatter={(value: number) => [`${value}%`, 'Marge']}
                    contentStyle={{ borderRadius: '0.5rem', fontSize: '0.8rem' }}
                  />
                  <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: 'Break-Even', fontSize: 10, fill: '#94a3b8' }} />
                  <Line
                    type="monotone"
                    dataKey="margin"
                    stroke="#6366f1"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: '#6366f1', stroke: '#fff', strokeWidth: 2 }}
                    activeDot={{ r: 6 }}
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
            <div className="space-y-1.5 text-sm">
              {togglProjects.length === 0 ? (
                <p className="text-gray-400">Keine Daten für diesen Monat</p>
              ) : (
                togglProjects.slice(0, 5).map((p, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <span className="truncate text-gray-600 dark:text-gray-300">{p.project_name}</span>
                    <span className="shrink-0 text-xs text-gray-400">{p.hours}h</span>
                    <span className="shrink-0 font-medium text-gray-900 dark:text-white">{formatCHF(p.amount)}</span>
                  </div>
                ))
              )}
            </div>
          </SourceCard>

          <SourceCard title="InvoiceInsight" subtitle="Kreditorenrechnungen" color="rose" comingSoon>
            <div className="flex flex-col items-center justify-center py-4 text-center text-sm text-gray-400">
              <ComingSoonIcon className="mb-2 h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p>Integration in Vorbereitung</p>
              <p className="mt-1 text-xs">Wiederkehrende Zahlungen, fällige Rechnungen, Deep Research</p>
            </div>
          </SourceCard>
        </div>

        {/* Detailtabelle */}
        {cashflow && (
          <div className="rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50">
            <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-700 sm:px-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Monatsübersicht</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <th className="px-4 py-3 sm:px-6">Monat</th>
                    <th className="px-4 py-3 text-right sm:px-6">Einnahmen</th>
                    <th className="px-4 py-3 text-right sm:px-6">Ausgaben</th>
                    <th className="px-4 py-3 text-right sm:px-6">Delta</th>
                    <th className="px-4 py-3 text-right sm:px-6">Marge</th>
                    <th className="px-4 py-3 text-right sm:px-6">Kum. Saldo</th>
                    <th className="px-4 py-3 sm:px-6"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                  {cashflow.months.map((m) => {
                    const margin = m.revenue > 0 ? Math.round((m.revenue - m.expenses) / m.revenue * 100) : null;
                    return (
                      <tr
                        key={m.month}
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
                        <td className={`whitespace-nowrap px-4 py-2.5 text-right font-medium sm:px-6 ${
                          m.delta >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'
                        }`}>
                          {m.delta >= 0 ? '+' : ''}{formatCHF(m.delta)}
                        </td>
                        <td className={`whitespace-nowrap px-4 py-2.5 text-right text-xs sm:px-6 ${
                          margin != null && margin >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'
                        }`}>
                          {margin != null ? `${margin}%` : '–'}
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

function ExternalLinkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  );
}

function ComingSoonIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
    </svg>
  );
}
