import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ComposedChart, Line,
} from 'recharts';
import { api } from '../../api/client';
import type { CreditorsFilter, StyleCtx } from './creditors-types';
import {
  formatCHF, formatK, TOOLTIP_STYLE, CURSOR_STYLE,
  getCategoryColor, FALLBACK_COLORS, buildFilterParams, Skeleton,
} from './creditors-helpers';

interface Props {
  filter: CreditorsFilter;
  styleCtx: StyleCtx;
}

interface TrendRow {
  month: string;
  count: number;
  total_chf: number;
}

interface CategoryRow {
  name: string;
  count: number;
  total_chf: number;
  avg_chf: number;
  share: number;
}

interface YoyData {
  categories: string[];
  years: string[];
  rows: Record<string, unknown>[];
}

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
  'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez',
];

function normalizeTrend(raw: Record<string, unknown>): TrendRow {
  return {
    month: String(raw.month ?? raw.Monatsname ?? ''),
    count: Number(raw.count ?? raw.Anzahl ?? 0),
    total_chf: Number(raw.total_chf ?? raw.Aktuell_CHF ?? 0),
  };
}

function normalizeCategoryRow(raw: Record<string, unknown>): CategoryRow {
  return {
    name: String(raw.name ?? raw.Kategorie ?? '–'),
    count: Number(raw.count ?? raw.Anzahl ?? 0),
    total_chf: Number(raw.total_chf ?? raw.Total_CHF ?? 0),
    avg_chf: Number(raw.avg_chf ?? raw.Avg_CHF ?? 0),
    share: Number(raw.share ?? raw.Anteil_Pct ?? 0),
  };
}

function intensityColor(value: number, max: number): string {
  if (max === 0) return 'bg-gray-100 dark:bg-gray-800';
  const ratio = Math.min(value / max, 1);
  if (ratio < 0.15) return 'bg-indigo-50 dark:bg-indigo-950/40';
  if (ratio < 0.35) return 'bg-indigo-100 dark:bg-indigo-900/50';
  if (ratio < 0.55) return 'bg-indigo-200 dark:bg-indigo-800/60';
  if (ratio < 0.75) return 'bg-indigo-400 dark:bg-indigo-600 text-white';
  return 'bg-indigo-600 dark:bg-violet-600 text-white';
}

export function CreditorsAnalysis({ filter, styleCtx }: Props) {
  const { hasBg, textPrimary, textSecondary, textMuted } = styleCtx;

  const card = `rounded-xl p-3 sm:p-4 ${
    hasBg
      ? 'bg-black/30 backdrop-blur-xl ring-1 ring-white/10'
      : 'border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800/50'
  }`;

  const [trends, setTrends] = useState<TrendRow[]>([]);
  const [catRows, setCatRows] = useState<CategoryRow[]>([]);
  const [yoy, setYoy] = useState<YoyData>({ categories: [], years: [], rows: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const qs = buildFilterParams(filter);
    const suffix = qs.toString() ? `?${qs}` : '';
    let done = 0;
    const check = () => { done++; if (done >= 3) setLoading(false); };

    api.get<unknown[]>(`/api/creditors/trends${suffix}`)
      .then(raw => { setTrends((raw ?? []).map((r: any) => normalizeTrend(r))); check(); })
      .catch(() => check());

    api.get<unknown[]>(`/api/creditors/category-trend${suffix}`)
      .then(raw => {
        const rows = (raw ?? []).map((r: any) => normalizeCategoryRow(r));
        rows.sort((a, b) => b.total_chf - a.total_chf);
        setCatRows(rows);
        check();
      })
      .catch(() => check());

    api.get<YoyData>(`/api/creditors/yoy${suffix}`)
      .then(d => {
        setYoy({
          categories: d?.categories ?? [],
          years: d?.years ?? [],
          rows: Array.isArray((d as any)?.rows ?? (d as any)?.data)
            ? ((d as any).rows ?? (d as any).data)
            : [],
        });
        check();
      })
      .catch(() => check());
  }, [filter]);

  /* --- Heatmap: pivotiere Trends nach Monat × Jahr --- */
  const heatYears: string[] = [];
  const heatGrid: Record<string, Record<string, number>> = {};
  let heatMax = 0;

  for (const t of trends) {
    const parts = t.month.match(/(\w+)\s+(\d{4})/);
    if (!parts) continue;
    const [, mLabel, year] = parts;
    if (!heatYears.includes(year)) heatYears.push(year);
    if (!heatGrid[mLabel]) heatGrid[mLabel] = {};
    heatGrid[mLabel][year] = (heatGrid[mLabel][year] ?? 0) + t.total_chf;
    if (heatGrid[mLabel][year] > heatMax) heatMax = heatGrid[mLabel][year];
  }
  heatYears.sort();

  /* --- YoY Chart-Daten --- */
  const yoyRows = yoy.rows.map(r => {
    const out: Record<string, unknown> = { name: r.name ?? r.Kategorie ?? '–' };
    for (const y of yoy.years) out[y] = Number((r as any)[y] ?? 0);
    return out;
  });

  const catTotal = catRows.reduce((s, c) => s + c.total_chf, 0);

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 1 ─ Monatliches Rechnungsvolumen */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className={card}>
          <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Anzahl Rechnungen / Monat</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={trends} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} stroke="#9ca3af" angle={-35} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE} />
              <Bar dataKey="count" name="Rechnungen" fill="#6366f1" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className={card}>
          <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>CHF Volumen / Monat</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={trends} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} stroke="#9ca3af" angle={-35} textAnchor="end" height={50} />
              <YAxis tickFormatter={v => formatK(v)} tick={{ fontSize: 11 }} stroke="#9ca3af" />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE} formatter={(v: number) => formatCHF(v)} />
              <Bar dataKey="total_chf" name="Volumen CHF" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 2 ─ Monatliche Heatmap */}
      <div className={card}>
        <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Monatliche Heatmap</h3>
        {heatYears.length === 0 ? (
          <p className={`text-xs ${textMuted}`}>Keine Daten</p>
        ) : (
          <div className="overflow-x-auto">
            <div
              className="grid gap-1"
              style={{ gridTemplateColumns: `80px repeat(${heatYears.length}, minmax(60px, 1fr))` }}
            >
              <div />
              {heatYears.map(y => (
                <div key={y} className={`text-xs font-medium text-center ${textSecondary}`}>{y}</div>
              ))}

              {MONTH_LABELS.map(ml => (
                <React.Fragment key={ml}>
                  <div className={`text-xs ${textMuted} flex items-center`}>{ml}</div>
                  {heatYears.map(yr => {
                    const val = heatGrid[ml]?.[yr] ?? 0;
                    return (
                      <div
                        key={`${ml}-${yr}`}
                        title={formatCHF(val)}
                        className={`min-h-[32px] rounded-md text-xs flex items-center justify-center ${intensityColor(val, heatMax)}`}
                      >
                        {val > 0 ? formatK(val) : ''}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 3 ─ Kategorie-Details */}
      <div className={card}>
        <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Kategorie-Details</h3>
        {catRows.length === 0 ? (
          <p className={`text-xs ${textMuted}`}>Keine Daten</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b border-gray-200 dark:border-gray-700 ${textSecondary}`}>
                  <th className="text-left py-2 pr-4 font-medium">Kategorie</th>
                  <th className="text-right py-2 px-3 font-medium">Rechnungen</th>
                  <th className="text-right py-2 px-3 font-medium">Total CHF</th>
                  <th className="text-right py-2 px-3 font-medium">Ø CHF</th>
                  <th className="text-right py-2 pl-3 font-medium">Anteil %</th>
                </tr>
              </thead>
              <tbody>
                {catRows.map((c, i) => {
                  const share = catTotal > 0 ? (c.total_chf / catTotal) * 100 : c.share;
                  return (
                    <tr key={c.name} className="border-b border-gray-100 dark:border-gray-700/50">
                      <td className={`py-2 pr-4 flex items-center gap-2 ${textPrimary}`}>
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: getCategoryColor(c.name, i) }}
                        />
                        {c.name}
                      </td>
                      <td className={`text-right py-2 px-3 tabular-nums ${textSecondary}`}>{c.count}</td>
                      <td className={`text-right py-2 px-3 tabular-nums ${textPrimary}`}>{formatCHF(c.total_chf)}</td>
                      <td className={`text-right py-2 px-3 tabular-nums ${textMuted}`}>
                        {c.count > 0 ? formatCHF(c.total_chf / c.count) : '–'}
                      </td>
                      <td className={`text-right py-2 pl-3 tabular-nums ${textSecondary}`}>
                        {share.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 4 ─ YoY-Vergleich */}
      <div className={card}>
        <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>Jahresvergleich (YoY)</h3>
        {yoyRows.length === 0 ? (
          <p className={`text-xs ${textMuted}`}>Keine Daten</p>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={yoyRows} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#9ca3af" />
              <YAxis tickFormatter={v => formatK(v)} tick={{ fontSize: 11 }} stroke="#9ca3af" />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR_STYLE} formatter={(v: number) => formatCHF(v)} />
              <Legend wrapperStyle={{ fontSize: '11px' }} />
              {yoy.years.map((yr, i) => (
                <Bar
                  key={yr}
                  dataKey={yr}
                  name={yr}
                  fill={i === 0 ? '#a5b4fc' : '#4f46e5'}
                  radius={[3, 3, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
