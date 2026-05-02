import { useState, useEffect } from 'react';
import {
  PieChart, Pie, Cell,
  ComposedChart, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../../api/client';
import type { CreditorsFilter, StyleCtx } from './creditors-types';
import {
  formatCHF, formatK, extractKpi,
  TOOLTIP_STYLE, CURSOR_STYLE,
  getCategoryColor, normalizeRenewals,
  FALLBACK_COLORS, buildFilterParams, Skeleton,
} from './creditors-helpers';

interface Props {
  filter: CreditorsFilter;
  styleCtx: StyleCtx;
}

interface UpcomingPayment {
  vendor: string;
  product: string;
  amount_chf: number;
  days_until: number;
}

interface RecurringItem {
  name: string;
  total: number;
}

function urgencyDot(days: number): string {
  if (days < 7) return 'bg-red-500';
  if (days < 30) return 'bg-amber-500';
  return 'bg-emerald-500';
}

function AiGauge({ pct }: { pct: number }) {
  const r = 60;
  const stroke = 14;
  const cx = 80;
  const cy = 70;
  const circumference = Math.PI * r;
  const filled = circumference * (Math.min(pct, 100) / 100);

  return (
    <svg viewBox="0 0 160 90" className="w-full max-w-[220px] mx-auto">
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="#e2e8f0"
        strokeWidth={stroke}
        strokeLinecap="round"
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="url(#gaugeGrad)"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circumference}`}
      />
      <defs>
        <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <text
        x={cx} y={cy - 8}
        textAnchor="middle"
        className="fill-current text-gray-900 dark:text-gray-100"
        fontSize="22"
        fontWeight="bold"
      >
        {pct.toFixed(1)}%
      </text>
      <text
        x={cx} y={cy + 10}
        textAnchor="middle"
        className="fill-current text-gray-500 dark:text-gray-400"
        fontSize="10"
      >
        AI-Anteil
      </text>
    </svg>
  );
}

export function CreditorsOverview({ filter, styleCtx }: Props) {
  const { hasBg, cardClass, sectionClass, textPrimary, textSecondary, textMuted } = styleCtx;

  const card = `rounded-xl p-3 sm:p-4 ${
    hasBg
      ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10'
      : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50'
  }`;

  const [kpis, setKpis] = useState<Record<string, unknown>>({});
  const [costDist, setCostDist] = useState<Record<string, unknown>[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingPayment[]>([]);
  const [recurring, setRecurring] = useState<RecurringItem[]>([]);
  const [onetime, setOnetime] = useState<RecurringItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const qs = buildFilterParams(filter);
    const suffix = qs.toString() ? `?${qs}` : '';

    api.get<{ kpis: Record<string, unknown>; cost_distribution: Record<string, unknown>[] }>(
      `/api/creditors/dashboard${suffix}`,
    ).then(d => {
      setKpis(d.kpis ?? {});
      setCostDist(Array.isArray(d.cost_distribution) ? d.cost_distribution : []);
      setLoading(false);
    }).catch(() => setLoading(false));

    api.get<unknown[]>(`/api/creditors/upcoming?n=5${suffix ? '&' + qs : ''}`)
      .then(raw => {
        const norm = normalizeRenewals(raw);
        setUpcoming(norm.map(r => ({
          vendor: r.vendor,
          product: r.product ?? '',
          amount_chf: r.amount_chf ?? 0,
          days_until: r.days_until,
        })));
      }).catch(() => {});

    api.get<{ recurring?: unknown[]; onetime?: unknown[] }>(`/api/creditors/recurring${suffix}`)
      .then(d => {
        const norm = (items: unknown[]): RecurringItem[] =>
          (items ?? []).map((it: any) => ({
            name: it.name ?? it.Kategorie ?? it.category ?? '–',
            total: it.total ?? it.Total_CHF ?? it.total_chf ?? 0,
          }));
        setRecurring(norm(d.recurring ?? []));
        setOnetime(norm(d.onetime ?? []));
      }).catch(() => {});
  }, [filter]);

  const totalSpend = extractKpi(kpis, 'total_spend_chf');
  const yearlyProj = extractKpi(kpis, 'total_yearly_chf');
  const monthlyBurn = extractKpi(kpis, 'monthly_burn_rate');
  const invoiceCount = extractKpi(kpis, 'invoice_count');
  const providerCount = extractKpi(kpis, 'provider_count');
  const aiShare = extractKpi(kpis, 'ai_share_pct');

  const kpiCards = [
    { label: 'Gesamtausgaben', value: formatCHF(totalSpend) },
    { label: 'Proj. Jahreskosten', value: formatCHF(yearlyProj) },
    { label: 'Ø Monatskosten', value: formatCHF(monthlyBurn) },
    { label: 'Rechnungen', value: `${invoiceCount} / ${providerCount} Anbieter` },
  ];

  const categories = [...new Set(costDist.map(d => String(d.category ?? d.Kategorie ?? 'Sonstig')))];

  const chartData = costDist.reduce<Record<string, Record<string, number>>>((acc, row) => {
    const year = String(row.year ?? row.Jahr ?? '?');
    const cat = String(row.category ?? row.Kategorie ?? 'Sonstig');
    const val = Number(row.total_chf ?? row.Total_CHF ?? 0);
    if (!acc[year]) acc[year] = { year: Number(year) } as any;
    (acc[year] as any)[cat] = ((acc[year] as any)[cat] ?? 0) + val;
    return acc;
  }, {});
  const costChartRows = Object.values(chartData).sort((a: any, b: any) => a.year - b.year);

  const currencyData = costDist.reduce<Record<string, number>>((acc, row) => {
    const cur = String(row.currency ?? row.Währung ?? 'CHF');
    acc[cur] = (acc[cur] ?? 0) + Number(row.total_chf ?? row.Total_CHF ?? 0);
    return acc;
  }, {});
  const currencyPie = Object.entries(currencyData).map(([name, value]) => ({ name, value }));
  if (!currencyPie.length) currencyPie.push({ name: 'CHF', value: totalSpend || 1 });

  const recurringTotal = recurring.reduce((s, i) => s + i.total, 0);
  const onetimeTotal = onetime.reduce((s, i) => s + i.total, 0);

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Skeleton className="h-72 rounded-xl lg:col-span-2" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-48 rounded-xl" />
          <Skeleton className="h-48 rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpiCards.map(k => (
          <div key={k.label} className={card}>
            <p className={`text-xs ${textMuted} mb-1`}>{k.label}</p>
            <p className={`text-lg font-semibold ${textPrimary}`}>{k.value}</p>
          </div>
        ))}
      </div>

      {/* Kostenentwicklung + AI-Anteil */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className={`${card} lg:col-span-2`}>
          <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Kostenentwicklung</h3>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={costChartRows} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="year" tick={{ fontSize: 11 }} stroke="#9ca3af" />
              <YAxis tickFormatter={v => formatK(v)} tick={{ fontSize: 11 }} stroke="#9ca3af" />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v: number) => formatCHF(v)}
                cursor={CURSOR_STYLE}
              />
              <Legend wrapperStyle={{ fontSize: '11px' }} />
              {categories.map((cat, i) => (
                <Bar
                  key={cat}
                  dataKey={cat}
                  stackId="costs"
                  fill={getCategoryColor(cat, i)}
                  radius={i === categories.length - 1 ? [3, 3, 0, 0] : undefined}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className={`${card} flex flex-col items-center justify-center`}>
          <h3 className={`text-sm font-semibold mb-2 ${textPrimary}`}>AI-Anteil</h3>
          <AiGauge pct={aiShare} />
          <p className={`text-xs mt-2 ${textMuted}`}>
            {formatCHF(totalSpend * aiShare / 100)} von {formatCHF(totalSpend)}
          </p>
        </div>
      </div>

      {/* Nächste fällige Kosten + Wiederkehrend vs Einmalig */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className={card}>
          <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Nächste fällige Kosten</h3>
          {upcoming.length === 0 ? (
            <p className={`text-xs ${textMuted}`}>Keine Daten</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {upcoming.map((u, i) => (
                <li key={i} className="flex items-center gap-3 text-sm">
                  <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${urgencyDot(u.days_until)}`} />
                  <span className={`flex-1 truncate ${textPrimary}`}>
                    {u.vendor}{u.product ? ` – ${u.product}` : ''}
                  </span>
                  <span className={`font-medium tabular-nums ${textSecondary}`}>{formatCHF(u.amount_chf)}</span>
                  <span className={`text-xs tabular-nums ${textMuted}`}>{u.days_until}d</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={card}>
          <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Wiederkehrend vs Einmalig</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className={`text-xs font-medium mb-2 ${textSecondary}`}>
                Wiederkehrend <span className={textMuted}>({formatCHF(recurringTotal)})</span>
              </p>
              <ul className="flex flex-col gap-1">
                {recurring.map((r, i) => (
                  <li key={i} className={`flex justify-between text-xs ${textPrimary}`}>
                    <span className="truncate mr-2">{r.name}</span>
                    <span className={`tabular-nums ${textMuted}`}>{formatCHF(r.total)}</span>
                  </li>
                ))}
                {recurring.length === 0 && <li className={`text-xs ${textMuted}`}>–</li>}
              </ul>
            </div>
            <div>
              <p className={`text-xs font-medium mb-2 ${textSecondary}`}>
                Einmalig <span className={textMuted}>({formatCHF(onetimeTotal)})</span>
              </p>
              <ul className="flex flex-col gap-1">
                {onetime.map((r, i) => (
                  <li key={i} className={`flex justify-between text-xs ${textPrimary}`}>
                    <span className="truncate mr-2">{r.name}</span>
                    <span className={`tabular-nums ${textMuted}`}>{formatCHF(r.total)}</span>
                  </li>
                ))}
                {onetime.length === 0 && <li className={`text-xs ${textMuted}`}>–</li>}
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Währungsexposure */}
      <div className={card}>
        <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Währungsexposure</h3>
        <div className="flex items-center justify-center">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={currencyPie}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {currencyPie.map((entry, i) => (
                  <Cell key={entry.name} fill={FALLBACK_COLORS[i % FALLBACK_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => formatCHF(v)} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
