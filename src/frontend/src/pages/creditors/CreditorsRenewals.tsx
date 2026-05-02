import { useState, useEffect, useCallback } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import type { StyleCtx, CreditorsFilter, RenewalEntry, RenewalCalendar } from './creditors-types';
import { formatCHF, normalizeRenewals, buildFilterParams, TOOLTIP_STYLE, Skeleton } from './creditors-helpers';
import { api } from '../../api/client';

interface Props { filter: CreditorsFilter; styleCtx: StyleCtx }

interface ScatterPoint {
  x: number; y: number; z: number;
  vendor: string; product: string; date: string; days: number;
}

const COLOR_RED = '#dc2626';
const COLOR_AMBER = '#f59e0b';
const COLOR_GREEN = '#22c55e';
const dayColor = (d: number) => (d < 30 ? COLOR_RED : d < 60 ? COLOR_AMBER : COLOR_GREEN);

const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('de-CH');
};

const monthLabel = (ts: number) => {
  const d = new Date(ts);
  return d.toLocaleDateString('de-CH', { month: 'short', year: '2-digit' });
};

function bucketRenewals(entries: RenewalEntry[]) {
  const critical: RenewalEntry[] = [];
  const soon: RenewalEntry[] = [];
  const info: RenewalEntry[] = [];
  for (const e of entries) {
    if (e.days_until < 30) critical.push(e);
    else if (e.days_until < 60) soon.push(e);
    else info.push(e);
  }
  return { critical, soon, info };
}

function summaryFromEntries(entries: RenewalEntry[], maxDays: number) {
  const filtered = entries.filter(e => e.days_until <= maxDays);
  return {
    count: filtered.length,
    total: filtered.reduce((s, e) => s + (e.amount_chf ?? 0), 0),
  };
}

function buildScatterData(entries: RenewalEntry[]): { points: ScatterPoint[]; vendors: string[] } {
  const vendorSet = [...new Set(entries.map(e => e.vendor))];
  const vendorIdx = Object.fromEntries(vendorSet.map((v, i) => [v, i]));
  const points = entries.map(e => ({
    x: new Date(e.next_date).getTime(),
    y: vendorIdx[e.vendor] ?? 0,
    z: e.amount_chf ?? 100,
    vendor: e.vendor,
    product: e.product ?? '',
    date: e.next_date,
    days: e.days_until,
  }));
  return { points, vendors: vendorSet };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: { payload: ScatterPoint }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={TOOLTIP_STYLE} className="p-2 space-y-0.5 text-xs">
      <p className="font-semibold">{d.vendor}</p>
      {d.product && <p>{d.product}</p>}
      <p>{formatCHF(d.z)} &middot; {fmtDate(d.date)}</p>
      <p style={{ color: dayColor(d.days) }}>
        {d.days < 0 ? 'Überfällig' : `${d.days} Tage`}
      </p>
    </div>
  );
}

function RenewalRow({ entry, ctx }: { entry: RenewalEntry; ctx: StyleCtx }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className={`border-b cursor-pointer transition-colors ${
        ctx.hasBg ? 'border-white/10 hover:bg-white/5' : 'border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/40'
      }`}
      onClick={() => setOpen(o => !o)}
    >
      <div className="flex items-center gap-2 py-2.5 px-3 text-sm">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dayColor(entry.days_until) }} />
        <span className={`font-medium truncate ${ctx.textPrimary}`}>{entry.vendor}</span>
        {entry.product && <span className={`hidden sm:inline truncate ${ctx.textSecondary}`}>– {entry.product}</span>}
        <span className={`ml-auto whitespace-nowrap ${ctx.textSecondary}`}>{fmtDate(entry.next_date)}</span>
        <span className="text-xs whitespace-nowrap" style={{ color: dayColor(entry.days_until) }}>
          ({entry.days_until} Tage)
        </span>
        <span className={`hidden md:inline whitespace-nowrap font-medium ${ctx.textPrimary}`}>{formatCHF(entry.amount_chf)}</span>
        {entry.cycle && (
          <span className={`hidden lg:inline text-[10px] rounded px-1.5 py-0.5 ${
            ctx.hasBg ? 'bg-white/10' : 'bg-gray-100 dark:bg-gray-700'
          }`}>
            {entry.cycle}
          </span>
        )}
      </div>
      {open && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5 px-6 pb-3 text-xs">
          <div><span className={ctx.textMuted}>Kreditor</span><br />{entry.vendor}</div>
          <div><span className={ctx.textMuted}>Produkt</span><br />{entry.product || '–'}</div>
          <div><span className={ctx.textMuted}>Betrag</span><br />{formatCHF(entry.amount_chf)}</div>
          <div><span className={ctx.textMuted}>Zyklus</span><br />{entry.cycle || '–'}</div>
          <div><span className={ctx.textMuted}>Währung</span><br />{entry.currency ?? 'CHF'}</div>
        </div>
      )}
    </div>
  );
}

export function CreditorsRenewals({ filter, styleCtx }: Props) {
  const [entries, setEntries] = useState<RenewalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const qs = buildFilterParams(filter);
        const suffix = qs.toString() ? `?${qs}` : '';
        const raw = await api.get<RenewalCalendar | RenewalEntry[]>(`/api/creditors/renewal-calendar${suffix}`);
        let flat: RenewalEntry[];
        if (Array.isArray(raw)) {
          flat = normalizeRenewals(raw);
        } else {
          const cal = raw as RenewalCalendar;
          flat = normalizeRenewals([
            ...(cal.critical ?? []), ...(cal.warning ?? []),
            ...(cal.info ?? []), ...(cal.stable ?? []),
          ]);
        }
        if (!cancelled) setEntries(flat.sort((a, b) => a.days_until - b.days_until));
      } catch { /* leere Liste */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [filter]);

  const s30 = summaryFromEntries(entries, 30);
  const s60 = summaryFromEntries(entries, 60);
  const { critical, soon, info } = bucketRenewals(entries);
  const { points, vendors } = buildScatterData(entries);

  const groups = [
    { key: 'critical', label: 'Kritisch (<30 Tage)', color: COLOR_RED, items: critical },
    { key: 'soon', label: 'Bald (30–60 Tage)', color: COLOR_AMBER, items: soon },
    { key: 'info', label: 'Info (60+ Tage)', color: COLOR_GREEN, items: info },
  ] as const;

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex gap-4">
          <Skeleton className="h-32 flex-1" />
          <Skeleton className="h-32 flex-1" />
        </div>
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      <div className="flex-1 min-w-0 space-y-6">
        {points.length > 0 && (
          <section className={styleCtx.sectionClass}>
            <h3 className={`text-sm font-semibold mb-3 ${styleCtx.textPrimary}`}>
              Erneuerungs-Timeline
            </h3>
            <ResponsiveContainer width="100%" height={Math.max(220, vendors.length * 40 + 60)}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis
                  type="number" dataKey="x" domain={['dataMin', 'dataMax']}
                  tickFormatter={monthLabel} tick={{ fill: '#9ca3af', fontSize: 11 }}
                  stroke="transparent"
                />
                <YAxis
                  type="number" dataKey="y" domain={[-0.5, vendors.length - 0.5]}
                  ticks={vendors.map((_, i) => i)}
                  tickFormatter={(i: number) => vendors[i]?.slice(0, 14) ?? ''}
                  tick={{ fill: '#9ca3af', fontSize: 11 }} width={110} stroke="transparent"
                />
                <ZAxis type="number" dataKey="z" range={[60, 400]} />
                <Tooltip content={<CustomTooltip />} cursor={false} />
                <Scatter data={points} isAnimationActive={false}>
                  {points.map((p, i) => (
                    <Cell key={i} fill={dayColor(p.days)} fillOpacity={0.75} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </section>
        )}

        {groups.map(g => g.items.length > 0 && (
          <section key={g.key} className={styleCtx.sectionClass}>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: g.color }} />
              <h3 className={`text-sm font-semibold ${styleCtx.textPrimary}`}>
                {g.label}
              </h3>
              <span className={`text-xs ${styleCtx.textMuted}`}>({g.items.length})</span>
            </div>
            {g.items.map((e, i) => (
              <RenewalRow key={`${g.key}-${i}`} entry={e} ctx={styleCtx} />
            ))}
          </section>
        ))}

        {entries.length === 0 && (
          <p className={`text-center py-8 ${styleCtx.textMuted}`}>Keine Erneuerungen vorhanden.</p>
        )}
      </div>

      {/* Sidebar */}
      <div className="w-full lg:w-56 shrink-0 flex flex-row lg:flex-col gap-4">
        <div className="flex-1 rounded-xl bg-red-600 text-white p-4 space-y-1">
          <p className="text-xs font-medium opacity-80">Nächste 30 Tage</p>
          <p className="text-2xl font-bold">{s30.count}</p>
          <p className="text-xs">Rechnungen</p>
          <p className="text-sm font-semibold">{formatCHF(s30.total)}</p>
        </div>
        <div className="flex-1 rounded-xl bg-amber-500 text-white p-4 space-y-1">
          <p className="text-xs font-medium opacity-80">Nächste 60 Tage</p>
          <p className="text-2xl font-bold">{s60.count}</p>
          <p className="text-xs">Rechnungen</p>
          <p className="text-sm font-semibold">{formatCHF(s60.total)}</p>
        </div>
      </div>
    </div>
  );
}
