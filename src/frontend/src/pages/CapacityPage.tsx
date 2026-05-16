import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Bar, ComposedChart,
} from 'recharts';
import {
  Plus, Trash2, ArrowRightLeft,
  ChevronLeft, ChevronRight, RefreshCw, Calendar, X, GripVertical, Palmtree,
} from 'lucide-react';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { api } from '../api/client';
import { ProjectIcon } from '../components/ProjectIcon';
import { BackgroundPicker } from '../components/BackgroundPicker';

// ── Types ────────────────────────────────────────────────────────────────────

interface CapProject {
  id: string;
  name: string;
  color: string;
  client_name: string | null;
  hourly_rate: number | null;
  is_billable: boolean;
  status: 'bestätigt' | 'vorläufig';
  project_id: string | null;
  toggl_project_id: number | null;
  pipedrive_deal_id: number | null;
  sort_order: number;
  notes: string | null;
  icon_url: string | null;
  icon_emoji: string | null;
}

interface Allocation {
  id: string;
  capacity_project_id: string;
  week_start: string;
  minutes: number;
  is_billable: boolean;
  series_id: string | null;
  notes: string | null;
}

interface WeeklySummary {
  week_start: string;
  available_minutes: number;
  planned_minutes: number;
  tentative_minutes: number;
  utilization_pct: number;
}

interface TimeOffEntry {
  id: string;
  date: string;
  type: string;
  label: string | null;
  hours: number;
}

interface PlanVsActualProject {
  toggl_project_id: number;
  name: string;
  weeks: { week_start: string; planned_minutes: number; actual_minutes: number }[];
}

type ViewRange = '3m' | '6m' | '1y';

// ── Helpers ──────────────────────────────────────────────────────────────────

function getMonday(d: Date): Date {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function addWeeks(d: Date, weeks: number): Date {
  return new Date(d.getTime() + weeks * 7 * 86400000);
}

function formatWeek(d: Date): string {
  const day = d.getDate();
  const month = d.toLocaleDateString('de-CH', { month: 'short' });
  return `${day}. ${month}`;
}

function toIso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function getWeeksForRange(start: Date, range: ViewRange): Date[] {
  const weeks: Date[] = [];
  const count = range === '3m' ? 13 : range === '6m' ? 26 : 52;
  for (let i = 0; i < count; i++) {
    weeks.push(addWeeks(start, i));
  }
  return weeks;
}

function minutesToDisplay(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function getColClass(range: ViewRange): string {
  if (range === '1y') return 'w-8 min-w-8';
  if (range === '6m') return 'w-12 min-w-12';
  return 'w-16 min-w-16';
}

// ── Sortable Project Row ─────────────────────────────────────────────────────

function SortableProjectRow({
  project, weeks, allocations, onCellClick, onContextMenu, colClass, compact,
}: {
  project: CapProject;
  weeks: Date[];
  allocations: Allocation[];
  onCellClick: (projectId: string, weekStart: string) => void;
  colClass: string;
  compact: boolean;
  onContextMenu: (e: React.MouseEvent, alloc: Allocation) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: project.id });
  const style = { transform: CSS.Transform.toString(transform), transition };

  const allocMap = useMemo(() => {
    const map: Record<string, Allocation> = {};
    for (const a of allocations) {
      map[a.week_start] = a;
    }
    return map;
  }, [allocations]);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-stretch border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50/50 dark:hover:bg-gray-800/30"
      data-testid={`capacity-project-row-${project.id}`}
    >
      {/* Projekt-Label (fixed) */}
      <div className="sticky left-0 z-10 flex w-56 min-w-56 items-center gap-2 border-r border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900">
        <button {...attributes} {...listeners} className="cursor-grab text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" data-testid="capacity-project-drag">
          <GripVertical className="h-4 w-4" />
        </button>
        <ProjectIcon iconUrl={project.icon_url} iconEmoji={project.icon_emoji} color={project.color} size={20} />
        <div className="flex flex-col min-w-0">
          <span className="truncate text-sm font-medium text-gray-800 dark:text-gray-200">{project.name}</span>
          {project.client_name && (
            <span className="truncate text-xs text-gray-500 dark:text-gray-400">{project.client_name}</span>
          )}
        </div>
        {project.status === 'vorläufig' && (
          <span className="ml-auto rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            vorl.
          </span>
        )}
      </div>

      {/* Wochen-Zellen */}
      <div className="flex flex-1">
        {weeks.map(week => {
          const weekStr = toIso(week);
          const alloc = allocMap[weekStr];
          return (
            <div
              key={weekStr}
              className={`relative flex h-full min-h-[44px] ${colClass} items-center justify-center border-r border-gray-100 dark:border-gray-800 cursor-pointer`}
              onClick={() => onCellClick(project.id, weekStr)}
              onContextMenu={alloc ? (e) => onContextMenu(e, alloc) : undefined}
              data-testid={`capacity-cell-${project.id}-${weekStr}`}
            >
              {alloc && (
                <div
                  className={`absolute inset-0.5 rounded-md flex items-center justify-center font-medium text-white transition-all hover:scale-105 ${compact ? 'text-[9px]' : 'text-xs'}`}
                  style={{
                    backgroundColor: project.status === 'vorläufig'
                      ? `${project.color}80`
                      : project.color,
                    border: project.status === 'vorläufig' ? `2px dashed ${project.color}` : 'none',
                  }}
                  data-testid={`capacity-block-${alloc.id}`}
                >
                  {compact ? '' : minutesToDisplay(alloc.minutes)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Allocation Dialog ────────────────────────────────────────────────────────

function AllocationDialog({
  open, onClose, onSave, projects, initialProjectId, initialWeek,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (data: {
    capacity_project_id: string;
    week_start: string;
    minutes: number;
    is_billable: boolean;
    repeat: boolean;
    end_date?: string;
    interval_weeks?: number;
    notes?: string;
  }) => void;
  projects: CapProject[];
  initialProjectId: string;
  initialWeek: string;
}) {
  const [projectId, setProjectId] = useState(initialProjectId);
  const [weekStart, setWeekStart] = useState(initialWeek);
  const [inputMode, setInputMode] = useState<'time' | 'days'>('time');
  const [hoursInput, setHoursInput] = useState('8');
  const [minutesInput, setMinutesInput] = useState('0');
  const [daysInput, setDaysInput] = useState('1');
  const [hoursPerDay, setHoursPerDay] = useState('8');
  const [isBillable, setIsBillable] = useState(true);
  const [repeat, setRepeat] = useState(false);
  const [endDate, setEndDate] = useState('');
  const [intervalWeeks, setIntervalWeeks] = useState(1);
  const [notes, setNotes] = useState('');

  useEffect(() => {
    setProjectId(initialProjectId);
    setWeekStart(initialWeek);
  }, [initialProjectId, initialWeek]);

  const totalMinutes = useMemo(() => {
    if (inputMode === 'time') {
      return (parseInt(hoursInput) || 0) * 60 + (parseInt(minutesInput) || 0);
    }
    return (parseFloat(daysInput) || 0) * (parseFloat(hoursPerDay) || 8) * 60;
  }, [inputMode, hoursInput, minutesInput, daysInput, hoursPerDay]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" data-testid="capacity-alloc-dialog">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-700 dark:bg-gray-900">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Zuweisung hinzufügen</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" data-testid="capacity-dialog-close">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Projekt */}
        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Projekt</label>
          <select
            value={projectId}
            onChange={e => setProjectId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            data-testid="capacity-dialog-project"
          >
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.name}{p.client_name ? ` (${p.client_name})` : ''}</option>
            ))}
          </select>
        </div>

        {/* Woche */}
        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Woche (Montag)</label>
          <input
            type="date"
            value={weekStart}
            onChange={e => setWeekStart(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            data-testid="capacity-dialog-week"
          />
        </div>

        {/* Eingabemodus */}
        <div className="mb-4">
          <div className="mb-2 flex gap-2">
            <button
              onClick={() => setInputMode('time')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${inputMode === 'time' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
              data-testid="capacity-dialog-mode-time"
            >
              Stunden/Minuten
            </button>
            <button
              onClick={() => setInputMode('days')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${inputMode === 'days' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
              data-testid="capacity-dialog-mode-days"
            >
              Arbeitstage
            </button>
          </div>

          {inputMode === 'time' ? (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0" max="80"
                value={hoursInput}
                onChange={e => setHoursInput(e.target.value)}
                className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-dialog-hours"
              />
              <span className="text-sm text-gray-500">h</span>
              <input
                type="number"
                min="0" max="59"
                value={minutesInput}
                onChange={e => setMinutesInput(e.target.value)}
                className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-dialog-minutes"
              />
              <span className="text-sm text-gray-500">min</span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0" max="7" step="0.5"
                value={daysInput}
                onChange={e => setDaysInput(e.target.value)}
                className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-dialog-days"
              />
              <span className="text-sm text-gray-500">Tage à</span>
              <input
                type="number"
                min="1" max="12"
                value={hoursPerDay}
                onChange={e => setHoursPerDay(e.target.value)}
                className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-dialog-hours-per-day"
              />
              <span className="text-sm text-gray-500">h</span>
            </div>
          )}

          {/* Live-Vorschau */}
          <div className="mt-2 rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300" data-testid="capacity-dialog-preview">
            Total: <strong>{minutesToDisplay(totalMinutes)}</strong> pro Woche
            {totalMinutes > 0 && ` (${Math.round(totalMinutes / 24)}% Auslastung)`}
          </div>
        </div>

        {/* Nicht-verrechenbar */}
        <div className="mb-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={isBillable}
              onChange={e => setIsBillable(e.target.checked)}
              className="rounded border-gray-300"
              data-testid="capacity-dialog-billable"
            />
            Verrechenbar
          </label>
        </div>

        {/* Wiederholung */}
        <div className="mb-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={repeat}
              onChange={e => setRepeat(e.target.checked)}
              className="rounded border-gray-300"
              data-testid="capacity-dialog-repeat"
            />
            Wiederholen
          </label>
          {repeat && (
            <div className="mt-2 flex items-center gap-2 pl-6">
              <span className="text-xs text-gray-500">Alle</span>
              <input
                type="number"
                min="1" max="4"
                value={intervalWeeks}
                onChange={e => setIntervalWeeks(parseInt(e.target.value) || 1)}
                className="w-14 rounded-lg border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-dialog-interval"
              />
              <span className="text-xs text-gray-500">Woche(n) bis</span>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-dialog-end-date"
              />
            </div>
          )}
        </div>

        {/* Notiz */}
        <div className="mb-5">
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Notiz</label>
          <input
            type="text"
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Optional..."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            data-testid="capacity-dialog-notes"
          />
        </div>

        {/* Aktionen */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Abbrechen
          </button>
          <button
            onClick={() => {
              if (totalMinutes <= 0 || !projectId) return;
              onSave({
                capacity_project_id: projectId,
                week_start: weekStart,
                minutes: totalMinutes,
                is_billable: isBillable,
                repeat,
                end_date: endDate || undefined,
                interval_weeks: intervalWeeks,
                notes: notes || undefined,
              });
            }}
            disabled={totalMinutes <= 0}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            data-testid="capacity-dialog-save"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Project Dialog ───────────────────────────────────────────────────────────

interface TogglProjectOption {
  id: number;
  name: string;
  client: string;
  billable: boolean;
  color: string;
}

function ProjectDialog({
  open, onClose, onSave, initial,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (data: Partial<CapProject> & { toggl_project_id?: number }) => void;
  initial?: CapProject | null;
}) {
  const [tab, setTab] = useState<'manual' | 'toggl'>('manual');
  const [name, setName] = useState(initial?.name || '');
  const [color, setColor] = useState(initial?.color || '#3B82F6');
  const [clientName, setClientName] = useState(initial?.client_name || '');
  const [hourlyRate, setHourlyRate] = useState(initial?.hourly_rate?.toString() || '');
  const [isBillable, setIsBillable] = useState(initial?.is_billable ?? true);
  const [status, setStatus] = useState<'bestätigt' | 'vorläufig'>(initial?.status || 'bestätigt');
  const [notes, setNotes] = useState(initial?.notes || '');
  const [iconEmoji, setIconEmoji] = useState(initial?.icon_emoji || '');
  const [iconUrl, setIconUrl] = useState(initial?.icon_url || '');

  const [togglProjects, setTogglProjects] = useState<TogglProjectOption[]>([]);
  const [togglLoading, setTogglLoading] = useState(false);
  const [togglFilter, setTogglFilter] = useState('');
  const [selectedToggl, setSelectedToggl] = useState<TogglProjectOption | null>(null);

  useEffect(() => {
    setName(initial?.name || '');
    setColor(initial?.color || '#3B82F6');
    setClientName(initial?.client_name || '');
    setHourlyRate(initial?.hourly_rate?.toString() || '');
    setIsBillable(initial?.is_billable ?? true);
    setStatus(initial?.status || 'bestätigt');
    setNotes(initial?.notes || '');
    setIconEmoji(initial?.icon_emoji || '');
    setIconUrl(initial?.icon_url || '');
    setTab('manual');
    setSelectedToggl(null);
  }, [initial]);

  useEffect(() => {
    if (open && tab === 'toggl' && togglProjects.length === 0) {
      setTogglLoading(true);
      api.get<TogglProjectOption[]>('/api/capacity/toggl-projects')
        .then(setTogglProjects)
        .catch(() => {})
        .finally(() => setTogglLoading(false));
    }
  }, [open, tab]);

  const filteredToggl = useMemo(() => {
    if (!togglFilter) return togglProjects;
    const term = togglFilter.toLowerCase();
    return togglProjects.filter(p =>
      p.name.toLowerCase().includes(term) || p.client.toLowerCase().includes(term)
    );
  }, [togglProjects, togglFilter]);

  if (!open) return null;

  const colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#6366F1', '#84CC16', '#F97316'];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" data-testid="capacity-project-dialog">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-700 dark:bg-gray-900">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {initial ? 'Projekt bearbeiten' : 'Neues Kapazitätsprojekt'}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs: Manuell / Aus Toggl */}
        {!initial && (
          <div className="mb-4 flex rounded-lg border border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setTab('manual')}
              className={`flex-1 rounded-l-lg px-3 py-2 text-xs font-medium transition ${tab === 'manual' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'}`}
              data-testid="capacity-project-tab-manual"
            >
              Neues Projekt
            </button>
            <button
              onClick={() => setTab('toggl')}
              className={`flex-1 rounded-r-lg px-3 py-2 text-xs font-medium transition ${tab === 'toggl' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'}`}
              data-testid="capacity-project-tab-toggl"
            >
              Aus Toggl importieren
            </button>
          </div>
        )}

        {tab === 'toggl' && !initial ? (
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Projekt suchen..."
              value={togglFilter}
              onChange={e => setTogglFilter(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              data-testid="capacity-toggl-search"
              autoFocus
            />
            <div className="max-h-60 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
              {togglLoading ? (
                <div className="flex items-center justify-center py-6">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                </div>
              ) : filteredToggl.length === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-gray-400">Keine Toggl-Projekte gefunden</p>
              ) : (
                filteredToggl.map(tp => (
                  <button
                    key={tp.id}
                    onClick={() => {
                      setSelectedToggl(tp);
                      setName(tp.name);
                      setClientName(tp.client);
                      setIsBillable(tp.billable);
                      setColor(tp.color || '#3B82F6');
                    }}
                    className={`flex w-full items-center gap-2 border-b border-gray-100 px-3 py-2 text-left text-sm transition last:border-b-0 dark:border-gray-800 ${selectedToggl?.id === tp.id ? 'bg-indigo-50 dark:bg-indigo-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'}`}
                    data-testid={`capacity-toggl-option-${tp.id}`}
                  >
                    <span className="h-3 w-3 rounded-full flex-shrink-0" style={{ backgroundColor: tp.color || '#3B82F6' }} />
                    <span className="flex-1 truncate font-medium text-gray-800 dark:text-gray-200">{tp.name}</span>
                    {tp.client && <span className="text-xs text-gray-400">{tp.client}</span>}
                  </button>
                ))
              )}
            </div>
            {selectedToggl && (
              <div className="rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700 dark:bg-green-900/20 dark:text-green-400">
                Ausgewählt: <strong>{selectedToggl.name}</strong>{selectedToggl.client ? ` (${selectedToggl.client})` : ''}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
              <input
                type="text" value={name} onChange={e => setName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-project-name"
                autoFocus
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Icon / Farbe</label>
              <div className="flex items-center gap-3">
                <div className="flex flex-wrap gap-1.5">
                  {colors.map(c => (
                    <button
                      key={c}
                      onClick={() => { setColor(c); setIconEmoji(''); setIconUrl(''); }}
                      className={`h-6 w-6 rounded-full border-2 transition ${color === c && !iconEmoji && !iconUrl ? 'border-gray-800 dark:border-white scale-110' : 'border-transparent'}`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
                <span className="text-xs text-gray-400">oder</span>
                <input
                  type="text"
                  placeholder="Emoji / Icon-Name"
                  value={iconEmoji}
                  onChange={e => { setIconEmoji(e.target.value); setIconUrl(''); }}
                  className="w-28 rounded-lg border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                  data-testid="capacity-project-icon-emoji"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Kunde</label>
                <input
                  type="text" value={clientName} onChange={e => setClientName(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                  data-testid="capacity-project-client"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Stundensatz (CHF)</label>
                <input
                  type="number" value={hourlyRate} onChange={e => setHourlyRate(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                  data-testid="capacity-project-rate"
                />
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input type="checkbox" checked={isBillable} onChange={e => setIsBillable(e.target.checked)} className="rounded border-gray-300" />
                Verrechenbar
              </label>
              <select
                value={status} onChange={e => setStatus(e.target.value as 'bestätigt' | 'vorläufig')}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-project-status"
              >
                <option value="bestätigt">Bestätigt</option>
                <option value="vorläufig">Vorläufig</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Notizen</label>
              <textarea
                value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                data-testid="capacity-project-notes"
              />
            </div>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
            Abbrechen
          </button>
          <button
            onClick={() => {
              if (!name.trim()) return;
              onSave({
                name: name.trim(),
                color,
                client_name: clientName || null,
                hourly_rate: hourlyRate ? parseFloat(hourlyRate) : null,
                is_billable: isBillable,
                status,
                notes: notes || null,
                icon_emoji: iconEmoji || null,
                icon_url: iconUrl || null,
                toggl_project_id: selectedToggl?.id || undefined,
              });
            }}
            disabled={!name.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            data-testid="capacity-project-save"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Context Menu ─────────────────────────────────────────────────────────────

function ContextMenu({
  x, y, alloc, onClose, onDelete, onDeleteSeries, onDeleteFrom, onShift,
}: {
  x: number; y: number;
  alloc: Allocation;
  onClose: () => void;
  onDelete: () => void;
  onDeleteSeries: () => void;
  onDeleteFrom: () => void;
  onShift: (weeks: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="fixed z-50 min-w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-xl dark:border-gray-700 dark:bg-gray-800"
      style={{ left: x, top: y }}
      data-testid="capacity-context-menu"
    >
      <button onClick={onDelete} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
        <Trash2 className="h-4 w-4" /> Zuweisung löschen
      </button>
      {alloc.series_id && (
        <>
          <button onClick={onDeleteSeries} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20">
            <Trash2 className="h-4 w-4" /> Ganze Serie löschen
          </button>
          <button onClick={onDeleteFrom} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <Trash2 className="h-4 w-4" /> Serie ab hier löschen
          </button>
          <hr className="my-1 border-gray-200 dark:border-gray-700" />
          <button onClick={() => onShift(1)} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <ArrowRightLeft className="h-4 w-4" /> Serie +1 Woche verschieben
          </button>
          <button onClick={() => onShift(-1)} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <ArrowRightLeft className="h-4 w-4" /> Serie −1 Woche verschieben
          </button>
        </>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export function CapacityPage() {
  const [projects, setProjects] = useState<CapProject[]>([]);
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [summary, setSummary] = useState<WeeklySummary[]>([]);
  const [timeOff, setTimeOff] = useState<TimeOffEntry[]>([]);
  const [planVsActual, setPlanVsActual] = useState<PlanVsActualProject[]>([]);
  const [viewRange, setViewRange] = useState<ViewRange>('3m');
  const [startDate, setStartDate] = useState<Date>(getMonday(new Date()));
  const [showTentative, setShowTentative] = useState(true);
  const [loading, setLoading] = useState(true);

  // Background
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);

  // Dialogs
  const [allocDialog, setAllocDialog] = useState<{ open: boolean; projectId: string; weekStart: string }>({ open: false, projectId: '', weekStart: '' });
  const [projectDialog, setProjectDialog] = useState<{ open: boolean; editing: CapProject | null }>({ open: false, editing: null });
  const [timeOffDialog, setTimeOffDialog] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; alloc: Allocation } | null>(null);

  // Time-off dialog state
  const [toFromDate, setToFromDate] = useState('');
  const [toToDate, setToToDate] = useState('');
  const [toType, setToType] = useState('ferien');
  const [toLabel, setToLabel] = useState('');
  const [toHours, setToHours] = useState('8');

  const weeks = useMemo(() => getWeeksForRange(startDate, viewRange), [startDate, viewRange]);
  const endDate = useMemo(() => addWeeks(startDate, weeks.length), [startDate, weeks.length]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  // ── Data Fetching ──────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const from = toIso(startDate);
      const to = toIso(endDate);
      const [projRes, allocRes, summaryRes, timeOffRes] = await Promise.all([
        api.get<CapProject[]>('/api/capacity/projects'),
        api.get<Allocation[]>(`/api/capacity/allocations?from=${from}&to=${to}&include_tentative=${showTentative}`),
        api.get<WeeklySummary[]>(`/api/capacity/weekly-summary?from=${from}&to=${to}&include_tentative=${showTentative}`),
        api.get<TimeOffEntry[]>(`/api/capacity/time-off?year=${startDate.getFullYear()}`),
      ]);
      setProjects(projRes);
      setAllocations(allocRes);
      setSummary(summaryRes);
      setTimeOff(timeOffRes);
    } catch (err) {
      console.error('Kapazitätsdaten laden fehlgeschlagen:', err);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, showTentative]);

  const fetchPlanVsActual = useCallback(async () => {
    try {
      const from = toIso(startDate);
      const to = toIso(endDate);
      const res = await api.get<{ projects: PlanVsActualProject[] }>(`/api/capacity/plan-vs-actual?from=${from}&to=${to}`);
      setPlanVsActual(res.projects);
    } catch {
      /* optional */
    }
  }, [startDate, endDate]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { fetchPlanVsActual(); }, [fetchPlanVsActual]);
  useEffect(() => {
    api.get<Record<string, string | null>>('/api/settings')
      .then(s => setBgUrl(s.capacity_background_url ?? null))
      .catch(() => {});
  }, []);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleCellClick = (projectId: string, weekStart: string) => {
    setAllocDialog({ open: true, projectId, weekStart });
  };

  const handleSaveAllocation = async (data: {
    capacity_project_id: string;
    week_start: string;
    minutes: number;
    is_billable: boolean;
    repeat: boolean;
    end_date?: string;
    interval_weeks?: number;
    notes?: string;
  }) => {
    try {
      if (data.repeat && data.end_date) {
        await api.post('/api/capacity/allocations/repeat', {
          capacity_project_id: data.capacity_project_id,
          week_start: data.week_start,
          end_date: data.end_date,
          minutes: data.minutes,
          interval_weeks: data.interval_weeks || 1,
          is_billable: data.is_billable,
          notes: data.notes,
        });
      } else {
        await api.post('/api/capacity/allocations', {
          capacity_project_id: data.capacity_project_id,
          week_start: data.week_start,
          minutes: data.minutes,
          is_billable: data.is_billable,
          notes: data.notes,
        });
      }
      setAllocDialog({ open: false, projectId: '', weekStart: '' });
      fetchData();
    } catch (err) {
      console.error('Zuweisung speichern fehlgeschlagen:', err);
    }
  };

  const handleSaveProject = async (data: Partial<CapProject>) => {
    try {
      if (projectDialog.editing) {
        await api.patch(`/api/capacity/projects/${projectDialog.editing.id}`, data);
      } else {
        await api.post('/api/capacity/projects', data);
      }
      setProjectDialog({ open: false, editing: null });
      fetchData();
    } catch (err) {
      console.error('Projekt speichern fehlgeschlagen:', err);
    }
  };

  const handleDeleteAllocation = async (allocId: string) => {
    await api.delete(`/api/capacity/allocations/${allocId}`);
    setContextMenu(null);
    fetchData();
  };

  const handleBulkAction = async (action: string, seriesId: string, fromWeek?: string, weeks?: number) => {
    await api.post('/api/capacity/allocations/bulk', {
      action, series_id: seriesId, from_week: fromWeek, weeks,
    });
    setContextMenu(null);
    fetchData();
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = projects.findIndex(p => p.id === active.id);
    const newIndex = projects.findIndex(p => p.id === over.id);
    const reordered = arrayMove(projects, oldIndex, newIndex);
    setProjects(reordered);
    const items = reordered.map((p, i) => ({ id: p.id, sort_order: i }));
    await api.patch('/api/capacity/projects/reorder', items);
  };

  const handleRefreshToggl = async () => {
    await api.post('/api/capacity/refresh-toggl');
    fetchPlanVsActual();
  };

  const handleBgSelect = async (url: string | null, _type?: string | null) => {
    await api.patch('/api/settings', { capacity_background_url: url });
    setBgUrl(url);
  };

  const handleSaveTimeOff = async () => {
    if (!toFromDate) return;
    const start = new Date(toFromDate);
    const end = toToDate ? new Date(toToDate) : start;
    const hours = parseFloat(toHours) || 8;
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const day = d.getDay();
      if (day === 0 || day === 6) continue;
      try {
        await api.post('/api/capacity/time-off', {
          date: d.toISOString().slice(0, 10),
          type: toType,
          label: toLabel || null,
          hours,
        });
      } catch { /* Duplikat ignorieren */ }
    }
    setTimeOffDialog(false);
    setToFromDate(''); setToToDate(''); setToLabel(''); setToHours('8');
    fetchData();
  };

  // ── Plan vs. Ist Chart Data ────────────────────────────────────────────────

  const chartData = useMemo(() => {
    if (!planVsActual.length) return [];
    const weekMap: Record<string, { week: string; planned: number; actual: number }> = {};
    for (const proj of planVsActual) {
      for (const w of proj.weeks) {
        if (!weekMap[w.week_start]) {
          weekMap[w.week_start] = { week: w.week_start, planned: 0, actual: 0 };
        }
        weekMap[w.week_start].planned += w.planned_minutes / 60;
        weekMap[w.week_start].actual += w.actual_minutes / 60;
      }
    }
    return Object.values(weekMap).sort((a, b) => a.week.localeCompare(b.week));
  }, [planVsActual]);

  // ── Time off weeks map ─────────────────────────────────────────────────────

  const timeOffWeekMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const t of timeOff) {
      const d = new Date(t.date);
      const monday = getMonday(d);
      const key = toIso(monday);
      map[key] = (map[key] || 0) + t.hours;
    }
    return map;
  }, [timeOff]);

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading && projects.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div
      className="flex h-full flex-col overflow-hidden"
      data-testid="capacity-page"
      style={bgUrl ? { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white/80 px-6 py-3 backdrop-blur dark:border-gray-700 dark:bg-gray-900/80">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-800 dark:text-gray-100">Kapazitätsplanung</h1>
          <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
            Anthony Smith · 40h/Woche
          </span>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
            <input
              type="checkbox"
              checked={showTentative}
              onChange={e => setShowTentative(e.target.checked)}
              className="rounded border-gray-300"
              data-testid="capacity-toggle-tentative"
            />
            Vorläufige anzeigen
          </label>
          <div className="ml-3 flex rounded-lg border border-gray-200 dark:border-gray-700">
            {(['3m', '6m', '1y'] as ViewRange[]).map(r => (
              <button
                key={r}
                onClick={() => setViewRange(r)}
                className={`px-3 py-1.5 text-xs font-medium transition ${viewRange === r ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'}`}
                data-testid={`capacity-range-${r}`}
              >
                {r === '3m' ? '3 Monate' : r === '6m' ? '6 Monate' : '1 Jahr'}
              </button>
            ))}
          </div>
          <button onClick={() => setStartDate(addWeeks(startDate, -4))} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" data-testid="capacity-nav-prev">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button onClick={() => setStartDate(getMonday(new Date()))} className="rounded-lg px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800" data-testid="capacity-nav-today">
            Heute
          </button>
          <button onClick={() => setStartDate(addWeeks(startDate, 4))} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" data-testid="capacity-nav-next">
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            onClick={() => setTimeOffDialog(true)}
            className="ml-3 flex items-center gap-1.5 rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900/20"
            data-testid="capacity-add-timeoff"
          >
            <Palmtree className="h-3.5 w-3.5" /> Ferien
          </button>
          <button
            onClick={() => setProjectDialog({ open: true, editing: null })}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
            data-testid="capacity-add-project"
          >
            <Plus className="h-3.5 w-3.5" /> Projekt
          </button>
          <button
            onClick={() => setBgPickerOpen(true)}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
            title="Hintergrund ändern"
            data-testid="capacity-bg-picker"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-auto" data-testid="capacity-timeline">
        <div className="min-w-max">
          {/* Auslastungs-Header */}
          <div className="sticky top-0 z-20 flex border-b border-gray-200 bg-white/95 backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
            <div className="sticky left-0 z-30 flex w-56 min-w-56 items-center border-r border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900">
              <span className="text-xs font-semibold text-gray-500 uppercase dark:text-gray-400">Auslastung</span>
            </div>
            <div className="flex">
              {weeks.map((week) => {
                const weekStr = toIso(week);
                const s = summary.find(s => s.week_start === weekStr);
                const util = s?.utilization_pct || 0;
                const hasTimeOff = timeOffWeekMap[weekStr] > 0;
                let barColor = 'bg-emerald-500';
                if (util > 100) barColor = 'bg-red-500';
                else if (util > 85) barColor = 'bg-amber-500';

                const isCompact = viewRange === '1y';
                const isMedium = viewRange === '6m';
                const barW = isCompact ? 'w-5' : isMedium ? 'w-7' : 'w-10';

                return (
                  <div key={weekStr} className={`flex ${getColClass(viewRange)} flex-col items-center border-r border-gray-100 py-1 dark:border-gray-800`}>
                    {!isCompact && (
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">{formatWeek(week)}</span>
                    )}
                    {isCompact && week.getDate() <= 7 && (
                      <span className="text-[9px] font-medium text-gray-500 dark:text-gray-400">
                        {week.toLocaleDateString('de-CH', { month: 'short' })}
                      </span>
                    )}
                    <div className={`relative mt-0.5 h-3 ${barW} overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700`}>
                      <div
                        className={`h-full rounded-full transition-all ${barColor}`}
                        style={{ width: `${Math.min(util, 100)}%` }}
                      />
                    </div>
                    {!isCompact && (
                      <span className={`mt-0.5 text-[10px] font-medium ${util > 100 ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-gray-400'}`}>
                        {Math.round(util)}%
                      </span>
                    )}
                    {hasTimeOff && (
                      <Calendar className={`mt-0.5 ${isCompact ? 'h-2.5 w-2.5' : 'h-3 w-3'} text-amber-500`} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Ferien-Zeile */}
          {timeOff.length > 0 && (
            <div className="flex items-stretch border-b border-amber-200 dark:border-amber-800/50 bg-amber-50/50 dark:bg-amber-900/10">
              <div className="sticky left-0 z-10 flex w-56 min-w-56 items-center gap-2 border-r border-gray-200 bg-amber-50 px-3 py-1.5 dark:border-gray-700 dark:bg-amber-900/20">
                <Palmtree className="h-4 w-4 text-amber-500" />
                <span className="text-xs font-medium text-amber-700 dark:text-amber-400">Ferien / Frei</span>
              </div>
              <div className="flex flex-1">
                {weeks.map(week => {
                  const weekStr = toIso(week);
                  const hoursOff = timeOffWeekMap[weekStr] || 0;
                  return (
                    <div key={weekStr} className={`flex ${getColClass(viewRange)} items-center justify-center border-r border-amber-100 dark:border-amber-900/30`}>
                      {hoursOff > 0 && (
                        <div className={`rounded px-1 py-0.5 text-[9px] font-medium ${hoursOff >= 40 ? 'bg-amber-200 text-amber-800 dark:bg-amber-800/40 dark:text-amber-300' : 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400'}`}>
                          {viewRange === '1y' ? '' : `${hoursOff}h`}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Projekte */}
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={projects.map(p => p.id)} strategy={verticalListSortingStrategy}>
              {projects.filter(p => showTentative || p.status === 'bestätigt').map(project => (
                <SortableProjectRow
                  key={project.id}
                  project={project}
                  weeks={weeks}
                  allocations={allocations.filter(a => a.capacity_project_id === project.id)}
                  onCellClick={handleCellClick}
                  onContextMenu={(e, alloc) => {
                    e.preventDefault();
                    setContextMenu({ x: e.clientX, y: e.clientY, alloc });
                  }}
                  colClass={getColClass(viewRange)}
                  compact={viewRange === '1y'}
                />
              ))}
            </SortableContext>
          </DndContext>

          {projects.length === 0 && (
            <div className="flex h-32 items-center justify-center text-sm text-gray-400 dark:text-gray-500">
              Noch keine Kapazitätsprojekte. Erstelle eines mit dem Button oben rechts.
            </div>
          )}
        </div>
      </div>

      {/* Plan vs. Ist Chart */}
      {chartData.length > 0 && (
        <div className="border-t border-gray-200 bg-white px-6 py-4 dark:border-gray-700 dark:bg-gray-900" data-testid="capacity-plan-vs-actual-chart">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Plan vs. Ist (Toggl)</h3>
            <button
              onClick={handleRefreshToggl}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-indigo-600 dark:text-gray-400"
              data-testid="capacity-refresh-toggl"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Aktualisieren
            </button>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis dataKey="week" tick={{ fontSize: 10 }} tickFormatter={v => {
                const d = new Date(v);
                return `${d.getDate()}.${d.getMonth() + 1}`;
              }} />
              <YAxis tick={{ fontSize: 10 }} unit="h" />
              <Tooltip formatter={(value) => `${Number(value).toFixed(1)}h`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="planned" name="Geplant" fill="#818CF8" radius={[3, 3, 0, 0]} />
              <Line dataKey="actual" name="Effektiv" stroke="#10B981" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Dialogs */}
      <AllocationDialog
        open={allocDialog.open}
        onClose={() => setAllocDialog({ open: false, projectId: '', weekStart: '' })}
        onSave={handleSaveAllocation}
        projects={projects}
        initialProjectId={allocDialog.projectId}
        initialWeek={allocDialog.weekStart}
      />

      <ProjectDialog
        open={projectDialog.open}
        onClose={() => setProjectDialog({ open: false, editing: null })}
        onSave={handleSaveProject}
        initial={projectDialog.editing}
      />

      {/* Context Menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          alloc={contextMenu.alloc}
          onClose={() => setContextMenu(null)}
          onDelete={() => handleDeleteAllocation(contextMenu.alloc.id)}
          onDeleteSeries={() => handleBulkAction('delete', contextMenu.alloc.series_id!)}
          onDeleteFrom={() => handleBulkAction('delete_from', contextMenu.alloc.series_id!, contextMenu.alloc.week_start)}
          onShift={(w) => handleBulkAction('shift', contextMenu.alloc.series_id!, undefined, w)}
        />
      )}

      {/* Ferien-Dialog */}
      {timeOffDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" data-testid="capacity-timeoff-dialog">
          <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-700 dark:bg-gray-900">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Ferien / freie Tage</h3>
              <button onClick={() => setTimeOffDialog(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">Von</label>
                  <input type="date" value={toFromDate} onChange={e => setToFromDate(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                    data-testid="capacity-timeoff-from" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">Bis (optional)</label>
                  <input type="date" value={toToDate} onChange={e => setToToDate(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                    data-testid="capacity-timeoff-to" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">Typ</label>
                <select value={toType} onChange={e => setToType(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                  data-testid="capacity-timeoff-type">
                  <option value="ferien">Ferien</option>
                  <option value="feiertag">Feiertag</option>
                  <option value="krank">Krank</option>
                  <option value="sonstiges">Sonstiges</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">Bezeichnung</label>
                  <input type="text" value={toLabel} onChange={e => setToLabel(e.target.value)}
                    placeholder="z.B. Sommerferien"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                    data-testid="capacity-timeoff-label" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">Stunden/Tag</label>
                  <input type="number" min="1" max="12" value={toHours} onChange={e => setToHours(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                    data-testid="capacity-timeoff-hours" />
                </div>
              </div>
              <p className="text-xs text-gray-400">8h = ganzer Tag, 4h = halber Tag. Wochenenden werden übersprungen.</p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setTimeOffDialog(false)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
                Abbrechen
              </button>
              <button onClick={handleSaveTimeOff} disabled={!toFromDate}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                data-testid="capacity-timeoff-save">
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* BackgroundPicker */}
      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={bgUrl}
        onSelect={handleBgSelect}
      />
    </div>
  );
}
