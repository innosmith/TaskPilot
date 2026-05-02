import { useState, useEffect } from 'react';
import { AlertOctagon, AlertTriangle, Info, CheckCircle2 } from 'lucide-react';
import type { StyleCtx, CreditorsFilter, AnomalyData, AnomalyEntry } from './creditors-types';
import { formatCHF, normalizeAnomalies, buildFilterParams, Skeleton } from './creditors-helpers';
import { api } from '../../api/client';

interface Props { filter: CreditorsFilter; styleCtx: StyleCtx }

const SEVERITY = [
  { key: 'critical' as const, label: 'Kritisch', Icon: AlertOctagon, pill: 'bg-red-600',
    bg: 'bg-red-50 dark:bg-red-950/40', border: 'border-red-200 dark:border-red-800',
    bar: 'bg-red-600', iconColor: 'text-red-500' },
  { key: 'warning' as const, label: 'Warnung', Icon: AlertTriangle, pill: 'bg-amber-500',
    bg: 'bg-amber-50 dark:bg-amber-950/40', border: 'border-amber-200 dark:border-amber-800',
    bar: 'bg-amber-500', iconColor: 'text-amber-500' },
  { key: 'info' as const, label: 'Info', Icon: Info, pill: 'bg-blue-500',
    bg: 'bg-blue-50 dark:bg-blue-950/40', border: 'border-blue-200 dark:border-blue-800',
    bar: 'bg-blue-500', iconColor: 'text-blue-500' },
  { key: 'stable' as const, label: 'Stabil', Icon: CheckCircle2, pill: 'bg-green-600',
    bg: 'bg-green-50 dark:bg-green-950/40', border: 'border-green-200 dark:border-green-800',
    bar: 'bg-green-600', iconColor: 'text-green-500' },
] as const;

type SeverityKey = (typeof SEVERITY)[number]['key'];

function recommendation(severity: SeverityKey, vendor: string): string {
  switch (severity) {
    case 'critical': return `Dringend prüfen: Kostenexplosion bei ${vendor}. Vertrag und Nutzung sofort überprüfen.`;
    case 'warning':  return `Beobachten: Kostenanstieg bei ${vendor}. Vergleichsangebote einholen empfohlen.`;
    case 'info':     return `Hinweis: Geringfügige Änderung bei ${vendor}. Keine sofortige Handlung erforderlich.`;
    case 'stable':   return `Stabil: Keine auffälligen Veränderungen bei ${vendor}.`;
  }
}

function AmountBar({ oldVal, newVal, color }: { oldVal: number; newVal: number; color: string }) {
  const max = Math.max(oldVal, newVal, 1);
  return (
    <div className="flex flex-col gap-1 text-[10px]">
      <div className="flex items-center gap-2">
        <span className="w-8 text-right opacity-60">Alt</span>
        <div className="flex-1 h-3 rounded bg-gray-200 dark:bg-gray-700">
          <div className="h-full rounded bg-gray-400" style={{ width: `${(oldVal / max) * 100}%` }} />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="w-8 text-right opacity-60">Neu</span>
        <div className="flex-1 h-3 rounded bg-gray-200 dark:bg-gray-700">
          <div className={`h-full rounded ${color}`} style={{ width: `${(newVal / max) * 100}%` }} />
        </div>
      </div>
    </div>
  );
}

function AnomalyCard({ entry, severity, ctx }: { entry: AnomalyEntry; severity: SeverityKey; ctx: StyleCtx }) {
  const [open, setOpen] = useState(false);
  const pct = entry.change_pct ?? 0;
  const pctColor = pct > 0 ? 'text-red-500 dark:text-red-400' : pct < 0 ? 'text-green-500 dark:text-green-400' : ctx.textMuted;
  const sev = SEVERITY.find(s => s.key === severity)!;

  return (
    <div
      className={`border ${sev.border} rounded-lg cursor-pointer hover:brightness-105 transition-all`}
      onClick={() => setOpen(o => !o)}
    >
      <div className="flex items-center gap-2 py-2.5 px-3 text-sm">
        <span className={`transition-transform duration-200 text-xs ${open ? 'rotate-90' : ''} ${ctx.textMuted}`}>▸</span>
        <span className={`font-medium truncate ${ctx.textPrimary}`}>{entry.vendor}</span>
        {entry.detail && (
          <span className={`hidden sm:inline truncate text-xs ${ctx.textMuted}`}>– {entry.detail}</span>
        )}
        <span className="ml-auto flex items-center gap-3 shrink-0">
          <span className={`text-xs font-semibold ${pctColor}`}>
            {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
          </span>
          <span className={`hidden md:inline text-xs ${ctx.textMuted}`}>
            {formatCHF(entry.old_amount)} → {formatCHF(entry.new_amount)}
          </span>
        </span>
      </div>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="px-4 pb-3 pt-1 space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-1 text-xs">
              <div><span className={ctx.textMuted}>Alter Betrag</span><br />{formatCHF(entry.old_amount)}</div>
              <div><span className={ctx.textMuted}>Neuer Betrag</span><br />{formatCHF(entry.new_amount)}</div>
              <div><span className={ctx.textMuted}>Veränderung</span><br />
                <span className={pctColor}>{pct > 0 ? '+' : ''}{pct.toFixed(1)}%</span>
              </div>
              <div><span className={ctx.textMuted}>Schweregrad</span><br />
                <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] text-white ${sev.pill}`}>
                  {sev.label}
                </span>
              </div>
            </div>

            <div className={`text-xs rounded-lg p-2.5 ${sev.bg}`}>
              <span className="font-semibold">Handlungsempfehlung: </span>
              {recommendation(severity, entry.vendor)}
            </div>

            <AmountBar
              oldVal={entry.old_amount ?? 0}
              newVal={entry.new_amount ?? 0}
              color={sev.bar}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export function CreditorsAnomalies({ filter, styleCtx }: Props) {
  const [data, setData] = useState<Record<SeverityKey, AnomalyEntry[]>>({
    critical: [], warning: [], info: [], stable: [],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const qs = buildFilterParams(filter);
        const suffix = qs.toString() ? `?${qs}` : '';
        const raw = await api.get<AnomalyData>(`/api/creditors/anomalies${suffix}`);
        if (!cancelled) {
          setData({
            critical: normalizeAnomalies(raw.critical),
            warning:  normalizeAnomalies(raw.warning),
            info:     normalizeAnomalies(raw.info),
            stable:   normalizeAnomalies(raw.stable),
          });
        }
      } catch { /* leer bei Fehler */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [filter]);

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  const total = SEVERITY.reduce((s, g) => s + data[g.key].length, 0);

  if (total === 0) {
    return (
      <div className={`flex flex-col items-center justify-center py-16 ${styleCtx.textMuted}`}>
        <CheckCircle2 className="h-12 w-12 mb-3 text-green-500" />
        <p className={`text-lg font-medium ${styleCtx.textPrimary}`}>Keine Anomalien erkannt</p>
        <p className="text-sm mt-1">Alle Kosten im normalen Bereich</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className={`${styleCtx.sectionClass} flex flex-wrap items-center gap-3`}>
        <h3 className={`text-sm font-semibold ${styleCtx.textPrimary}`}>
          Anomalie-Analyse
        </h3>
        {SEVERITY.map(s => {
          const n = data[s.key].length;
          if (!n) return null;
          return (
            <span key={s.key} className={`text-[11px] text-white font-medium rounded-full px-2.5 py-0.5 ${s.pill}`}>
              {n} {s.label}
            </span>
          );
        })}
      </div>

      {/* Grouped sections */}
      {SEVERITY.map(s => {
        const items = data[s.key];
        if (!items.length) return null;
        const Icon = s.Icon;
        return (
          <section key={s.key} className="space-y-2">
            <div className={`flex items-center gap-2 rounded-lg px-3 py-2 ${s.bg}`}>
              <Icon className={`h-4 w-4 ${s.iconColor}`} />
              <span className={`text-sm font-semibold ${styleCtx.textPrimary}`}>{s.label}</span>
              <span className={`text-xs ${styleCtx.textMuted}`}>({items.length})</span>
            </div>
            <div className="space-y-1.5">
              {items.map((e, i) => (
                <AnomalyCard key={`${s.key}-${i}`} entry={e} severity={s.key} ctx={styleCtx} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
