import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Plus, Trash2, ArrowRightLeft,
  ChevronLeft, ChevronRight, Calendar, X, GripVertical, Palmtree,
} from 'lucide-react';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent, useDroppable, useDraggable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToHorizontalAxis } from '@dnd-kit/modifiers';
import { api } from '../api/client';
import { ProjectIcon } from '../components/ProjectIcon';
import { BackgroundPicker } from '../components/BackgroundPicker';
import { LucideIconPicker } from '../components/LucideIconPicker';

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
  allocation_type?: 'week' | 'day';
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
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + weeks * 7);
}

function formatWeek(d: Date): string {
  const day = d.getDate();
  const month = d.toLocaleDateString('de-CH', { month: 'short' });
  return `${day}. ${month}`;
}

function toIso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
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

function getColClass(_range: ViewRange): string {
  return 'flex-1 min-w-0';
}

function getTodayOffset(weekStart: Date): number | null {
  const today = new Date();
  const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const weekEnd = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + 7);
  if (todayMidnight >= weekStart && todayMidnight < weekEnd) {
    const diffDays = Math.round((todayMidnight.getTime() - weekStart.getTime()) / 86400000);
    return Math.round((diffDays / 7) * 100);
  }
  return null;
}

// ── Allocation DnD helpers ───────────────────────────────────────────────────

function DroppableWeekCell({ id, colClass, measureRef, children }: {
  id: string; colClass: string; measureRef?: React.Ref<HTMLDivElement>; children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div
      ref={(node) => {
        setNodeRef(node);
        if (measureRef && typeof measureRef === 'function') measureRef(node);
        else if (measureRef && 'current' in measureRef) (measureRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
      }}
      className={`relative flex h-full min-h-[44px] ${colClass} items-center justify-center border-r border-gray-100 dark:border-gray-800 ${isOver ? 'ring-2 ring-inset ring-indigo-400 bg-indigo-50/40 dark:bg-indigo-900/20' : ''}`}
    >
      {children}
    </div>
  );
}

function DraggableAllocBlock({ allocId, children }: { allocId: string; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: `alloc-${allocId}` });
  const style: React.CSSProperties = transform ? {
    transform: `translate3d(${transform.x}px, 0, 0)`,
    zIndex: isDragging ? 40 : undefined,
    opacity: isDragging ? 0.7 : 1,
    cursor: 'grab',
  } : { cursor: 'grab' };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      {children}
    </div>
  );
}

// ── Sortable Project Row ─────────────────────────────────────────────────────

function SortableProjectRow({
  project, weeks, allocations, onCellClick, onContextMenu, onEditProject, colClass, viewRange: _viewRange, onAllocDrop, planVsActualByProject,
}: {
  project: CapProject;
  weeks: Date[];
  allocations: Allocation[];
  onCellClick: (projectId: string, weekStart: string) => void;
  onEditProject: (project: CapProject) => void;
  colClass: string;
  viewRange: ViewRange;
  onContextMenu: (e: React.MouseEvent, alloc: Allocation) => void;
  onAllocDrop: (allocId: string, targetWeekStr: string) => void;
  planVsActualByProject: Record<string, Record<string, number>>;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: project.id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const allocDndSensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const cellMeasureRef = useRef<HTMLDivElement>(null);
  const [cellWidth, setCellWidth] = useState(80);

  useEffect(() => {
    if (!cellMeasureRef.current) return;
    const observer = new ResizeObserver(entries => {
      if (entries[0]) setCellWidth(entries[0].contentRect.width);
    });
    observer.observe(cellMeasureRef.current);
    return () => observer.disconnect();
  }, []);

  const showDaySlots = cellWidth >= 30;

  const allocMap = useMemo(() => {
    const map: Record<string, Allocation[]> = {};
    for (const a of allocations) {
      let weekKey: string;
      if (a.allocation_type === 'day') {
        const d = new Date(a.week_start + 'T00:00:00');
        weekKey = toIso(getMonday(d));
      } else {
        weekKey = a.week_start;
      }
      if (!map[weekKey]) map[weekKey] = [];
      map[weekKey].push(a);
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
      {/* Projekt-Label */}
      <div className="flex w-56 min-w-56 shrink-0 items-center gap-2 border-r border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900">
        <button {...attributes} {...listeners} className="cursor-grab text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" data-testid="capacity-project-drag">
          <GripVertical className="h-4 w-4" />
        </button>
        <button
          onClick={() => onEditProject(project)}
          className="flex flex-1 items-center gap-2 min-w-0 rounded-md px-1 py-0.5 -mx-1 transition hover:bg-gray-100 dark:hover:bg-gray-800"
          data-testid="capacity-project-edit-btn"
        >
          <ProjectIcon iconUrl={project.icon_url} iconEmoji={project.icon_emoji} color={project.color} size={20} />
          <div className="flex flex-col min-w-0 text-left">
            <span className="truncate text-sm font-medium text-gray-800 dark:text-gray-200">{project.name}</span>
            {project.client_name && (
              <span className="truncate text-xs text-gray-500 dark:text-gray-400">{project.client_name}</span>
            )}
          </div>
        </button>
        {project.status === 'vorläufig' && (
          <span className="ml-auto rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            vorl.
          </span>
        )}
      </div>

      {/* Wochen-Zellen mit Allocation-DnD */}
      <DndContext
        sensors={allocDndSensors}
        modifiers={[restrictToHorizontalAxis]}
        onDragEnd={(event) => {
          const { active, over } = event;
          if (!over) return;
          const allocId = String(active.id).replace('alloc-', '');
          const targetWeek = String(over.id).replace(`drop-${project.id}-`, '');
          if (targetWeek && allocId) onAllocDrop(allocId, targetWeek);
        }}
      >
        <div className="flex flex-1">
          {weeks.map((week, idx) => {
            const weekStr = toIso(week);
            const weekAllocs = allocMap[weekStr];
            const totalMin = weekAllocs ? weekAllocs.reduce((s, a) => s + a.minutes, 0) : 0;
            const weekOnlyAllocs = weekAllocs?.filter(a => a.allocation_type !== 'day') || [];
            const dayAllocs = weekAllocs?.filter(a => a.allocation_type === 'day') || [];
            const firstAlloc = weekAllocs?.[0];
            const todayOffset = getTodayOffset(week);
            const isPast = week < new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
            const projectActualMin = planVsActualByProject[project.id]?.[weekStr] || 0;
            return (
              <DroppableWeekCell key={weekStr} id={`drop-${project.id}-${weekStr}`} colClass={colClass} measureRef={idx === 0 ? cellMeasureRef : undefined}>
                <div
                  className="absolute inset-0 cursor-pointer"
                  onClick={(e) => {
                    if (firstAlloc) {
                      e.preventDefault();
                      onContextMenu(e, firstAlloc);
                    } else {
                      onCellClick(project.id, weekStr);
                    }
                  }}
                  onContextMenu={firstAlloc ? (e) => { e.preventDefault(); onContextMenu(e, firstAlloc); } : undefined}
                  data-testid={`capacity-cell-${project.id}-${weekStr}`}
                />
                {/* Wochen-Allocations als draggable Block */}
                {weekOnlyAllocs.length > 0 && (
                  <DraggableAllocBlock allocId={weekOnlyAllocs[0].id}>
                    <div
                      className={`absolute inset-0.5 rounded-md flex items-center justify-center font-medium text-white transition-all hover:scale-[1.02] ${cellWidth < 40 ? 'text-[8px]' : cellWidth < 60 ? 'text-[9px]' : 'text-xs'}`}
                      style={{
                        backgroundColor: project.status === 'vorläufig' ? `${project.color}80` : project.color,
                        border: project.status === 'vorläufig' ? `2px dashed ${project.color}` : 'none',
                      }}
                      title={minutesToDisplay(weekOnlyAllocs.reduce((s, a) => s + a.minutes, 0))}
                    >
                      {cellWidth >= 40 ? (cellWidth >= 60 ? minutesToDisplay(weekOnlyAllocs.reduce((s, a) => s + a.minutes, 0)) : `${Math.round(weekOnlyAllocs.reduce((s, a) => s + a.minutes, 0) / 60)}h`) : ''}
                    </div>
                  </DraggableAllocBlock>
                )}

                {/* Tages-Allocations als schmale positionierte Blöcke */}
                {dayAllocs.length > 0 && showDaySlots && dayAllocs.map(da => {
                  const slotStyle = getDaySlotStyle(da.week_start);
                  return (
                    <DraggableAllocBlock key={da.id} allocId={da.id}>
                      <div
                        className="absolute top-0.5 bottom-0.5 rounded-sm flex items-center justify-center font-medium text-white text-[8px]"
                        style={{
                          left: slotStyle.left,
                          width: slotStyle.width,
                          backgroundColor: project.status === 'vorläufig' ? `${project.color}80` : project.color,
                          border: `1px solid ${project.color}`,
                        }}
                        title={`${new Date(da.week_start + 'T00:00:00').toLocaleDateString('de-CH', { weekday: 'short' })}: ${minutesToDisplay(da.minutes)}`}
                      >
                        {cellWidth >= 60 ? `${Math.round(da.minutes / 60)}` : ''}
                      </div>
                    </DraggableAllocBlock>
                  );
                })}

                {/* Tages-Allocations aggregiert (wenn Zelle zu klein) */}
                {dayAllocs.length > 0 && !showDaySlots && weekOnlyAllocs.length === 0 && (
                  <div
                    className="absolute inset-0.5 rounded-md flex items-center justify-center font-medium text-white text-[8px]"
                    style={{ backgroundColor: project.color }}
                    title={minutesToDisplay(totalMin)}
                  />
                )}

                {/* Inline Ist-Anzeige für vergangene Wochen */}
                {isPast && totalMin > 0 && projectActualMin > 0 && (
                  <div
                    className={`absolute bottom-0 left-0.5 right-0.5 h-[3px] rounded-b-sm ${
                      projectActualMin > totalMin * 1.05 ? 'bg-red-500' :
                      projectActualMin < totalMin * 0.8 ? 'bg-amber-400' :
                      'bg-emerald-500'
                    }`}
                    title={`Effektiv: ${minutesToDisplay(projectActualMin)} / Geplant: ${minutesToDisplay(totalMin)}`}
                  />
                )}

                {todayOffset !== null && (
                  <div className="absolute top-0 bottom-0 w-[2px] bg-red-500 dark:bg-red-400 z-10 pointer-events-none" style={{ left: `${todayOffset}%` }} />
                )}
              </DroppableWeekCell>
            );
          })}
        </div>
      </DndContext>
    </div>
  );
}

// ── Allocation Dialog ────────────────────────────────────────────────────────

function getDaySlotStyle(dateStr: string): { left: string; width: string } {
  const d = new Date(dateStr + 'T00:00:00');
  const dayIndex = (d.getDay() + 6) % 7; // Mo=0, Di=1, ..., Sa=5
  return { left: `${(dayIndex / 7) * 100}%`, width: '14.28%' };
}

function MiniCalendar({ month, year, selectedDays, onToggleDay }: {
  month: number; year: number;
  selectedDays: Set<string>;
  onToggleDay: (iso: string) => void;
}) {
  if (!Number.isFinite(year) || !Number.isFinite(month)) return null;
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startWeekday = (firstDay.getDay() + 6) % 7; // Mo=0
  const cells: (number | null)[] = Array(startWeekday).fill(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const monthLabel = firstDay.toLocaleDateString('de-CH', { month: 'long', year: 'numeric' });

  return (
    <div className="select-none">
      <div className="mb-1 text-center text-xs font-semibold text-gray-700 dark:text-gray-300">{monthLabel}</div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-[10px] font-medium text-gray-400 dark:text-gray-500 mb-0.5">
        {['Mo','Di','Mi','Do','Fr','Sa','So'].map(d => <div key={d}>{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day, i) => {
          if (day === null) return <div key={`e-${i}`} />;
          const d = new Date(year, month, day);
          const iso = toIso(d);
          const isSunday = d.getDay() === 0;
          const isSelected = selectedDays.has(iso);
          return (
            <button
              key={iso}
              type="button"
              disabled={isSunday}
              onClick={() => onToggleDay(iso)}
              className={`h-6 w-6 rounded text-[11px] font-medium transition
                ${isSunday ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed' : 'cursor-pointer hover:bg-indigo-100 dark:hover:bg-indigo-900/30'}
                ${isSelected ? 'bg-indigo-600 text-white hover:bg-indigo-700' : ''}`}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AllocationDialog({
  open, onClose, onSave, projects, initialProjectId, initialWeek,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (data: {
    capacity_project_id: string;
    week_start: string;
    minutes: number;
    allocation_type: 'week' | 'day';
    repeat: boolean;
    end_date?: string;
    interval_weeks?: number;
  }) => void;
  projects: CapProject[];
  initialProjectId: string;
  initialWeek: string;
}) {
  const [mode, setMode] = useState<'week' | 'calendar'>('week');
  const [projectId, setProjectId] = useState(initialProjectId);
  const [hoursInput, setHoursInput] = useState('8');
  const [minutesInput, setMinutesInput] = useState('0');
  const [repeat, setRepeat] = useState(false);
  const [repeatMode, setRepeatMode] = useState<'count' | 'date'>('count');
  const [repeatCount, setRepeatCount] = useState(4);
  const [endDate, setEndDate] = useState('');
  const [intervalWeeks, setIntervalWeeks] = useState(1);

  // Calendar mode state
  const [selectedDays, setSelectedDays] = useState<Set<string>>(new Set());
  const [calMonth, setCalMonth] = useState(() => {
    const d = new Date(initialWeek + 'T00:00:00');
    return { month: d.getMonth(), year: d.getFullYear() };
  });
  const [dayHours, setDayHours] = useState('8');

  useEffect(() => {
    setProjectId(initialProjectId);
    setMode('week');
    setHoursInput('8');
    setMinutesInput('0');
    setRepeat(false);
    setRepeatMode('count');
    setRepeatCount(4);
    setEndDate('');
    setIntervalWeeks(1);
    setSelectedDays(new Set());
    setDayHours('8');
    const d = new Date(initialWeek + 'T00:00:00');
    setCalMonth({ month: d.getMonth(), year: d.getFullYear() });
  }, [initialProjectId, initialWeek]);

  const totalMinutes = useMemo(() => {
    return (parseInt(hoursInput) || 0) * 60 + (parseInt(minutesInput) || 0);
  }, [hoursInput, minutesInput]);

  const dayTotalMinutes = useMemo(() => {
    return (parseInt(dayHours) || 0) * 60;
  }, [dayHours]);

  const toggleDay = useCallback((iso: string) => {
    setSelectedDays(prev => {
      const next = new Set(prev);
      if (next.has(iso)) next.delete(iso); else next.add(iso);
      return next;
    });
  }, []);

  const nextMonth = useMemo(() => {
    const m = calMonth.month + 1;
    return m > 11 ? { month: 0, year: calMonth.year + 1 } : { month: m, year: calMonth.year };
  }, [calMonth]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" data-testid="capacity-alloc-dialog">
      <div className={`rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-700 dark:bg-gray-900 ${mode === 'calendar' ? 'w-full max-w-lg' : 'w-full max-w-sm'}`}>
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {mode === 'week' ? 'Kapazität planen' : 'Einzeltage planen'}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMode(mode === 'week' ? 'calendar' : 'week')}
              className={`rounded-lg p-1.5 transition ${mode === 'calendar' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`}
              title={mode === 'week' ? 'Einzeltage planen' : 'Wochenplanung'}
              data-testid="capacity-dialog-toggle-mode"
            >
              <Calendar className="h-4 w-4" />
            </button>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" data-testid="capacity-dialog-close">
              <X className="h-5 w-5" />
            </button>
          </div>
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

        {mode === 'week' ? (
          <>
            {/* Wochenmodus: Stunden pro Woche */}
            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Stunden pro Woche</label>
              <div className="flex items-center gap-2">
                <input
                  type="number" min="0" max="80" value={hoursInput}
                  onChange={e => setHoursInput(e.target.value)}
                  className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                  data-testid="capacity-dialog-hours"
                />
                <span className="text-sm text-gray-500">h</span>
                <input
                  type="number" min="0" max="59" value={minutesInput}
                  onChange={e => setMinutesInput(e.target.value)}
                  className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                  data-testid="capacity-dialog-minutes"
                />
                <span className="text-sm text-gray-500">min</span>
              </div>
              {totalMinutes > 0 && (
                <div className="mt-2 rounded-lg bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300">
                  {minutesToDisplay(totalMinutes)}/Woche = {Math.round(totalMinutes / 24)}% Auslastung
                </div>
              )}
            </div>

            {/* Wiederholung */}
            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input type="checkbox" checked={repeat} onChange={e => setRepeat(e.target.checked)} className="rounded border-gray-300" data-testid="capacity-dialog-repeat" />
                Wiederholen
              </label>
              {repeat && (
                <div className="mt-2 space-y-2 pl-6">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">Alle</span>
                    <input type="number" min="1" max="4" value={intervalWeeks} onChange={e => setIntervalWeeks(parseInt(e.target.value) || 1)}
                      className="w-14 rounded-lg border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" data-testid="capacity-dialog-interval" />
                    <span className="text-xs text-gray-500">Woche(n)</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
                      <input type="radio" name="repeatMode" checked={repeatMode === 'count'} onChange={() => setRepeatMode('count')} className="text-indigo-600" />
                      <input type="number" min="2" max="52" value={repeatCount} onChange={e => setRepeatCount(parseInt(e.target.value) || 2)}
                        className="w-12 rounded border border-gray-300 px-1.5 py-0.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" data-testid="capacity-dialog-count" />
                      <span>mal</span>
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
                      <input type="radio" name="repeatMode" checked={repeatMode === 'date'} onChange={() => setRepeatMode('date')} className="text-indigo-600" />
                      <span>bis</span>
                      <input type="date" value={endDate} min={initialWeek}
                        onChange={e => { setEndDate(e.target.value); setRepeatMode('date'); }}
                        className="rounded border border-gray-300 px-1.5 py-0.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" data-testid="capacity-dialog-end-date" />
                    </label>
                  </div>
                </div>
              )}
            </div>

            {/* Aktionen */}
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
                Abbrechen
              </button>
              <button
                onClick={() => {
                  if (totalMinutes <= 0 || !projectId) return;
                  let computedEndDate = endDate || undefined;
                  if (repeat && repeatMode === 'count' && !computedEndDate) {
                    const start = new Date(initialWeek + 'T00:00:00');
                    const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + (repeatCount - 1) * intervalWeeks * 7);
                    computedEndDate = toIso(end);
                  }
                  onSave({
                    capacity_project_id: projectId,
                    week_start: initialWeek,
                    minutes: totalMinutes,
                    allocation_type: 'week',
                    repeat,
                    end_date: computedEndDate,
                    interval_weeks: intervalWeeks,
                  });
                }}
                disabled={totalMinutes <= 0}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                data-testid="capacity-dialog-save"
              >
                Speichern
              </button>
            </div>
          </>
        ) : (
          <>
            {/* Kalendermodus: Tage auswählen */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <button onClick={() => setCalMonth(p => {
                  const m = p.month - 1;
                  return m < 0 ? { month: 11, year: p.year - 1 } : { month: m, year: p.year };
                })} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button onClick={() => setCalMonth(p => {
                  const m = p.month + 1;
                  return m > 11 ? { month: 0, year: p.year + 1 } : { month: m, year: p.year };
                })} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <MiniCalendar month={calMonth.month} year={calMonth.year} selectedDays={selectedDays} onToggleDay={toggleDay} />
                <MiniCalendar month={nextMonth.month} year={nextMonth.year} selectedDays={selectedDays} onToggleDay={toggleDay} />
              </div>
              {selectedDays.size > 0 && (
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  {selectedDays.size} Tag{selectedDays.size > 1 ? 'e' : ''} gewählt
                </div>
              )}
            </div>

            {/* Stunden pro Tag */}
            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Stunden pro Tag</label>
              <div className="flex items-center gap-2">
                <input type="number" min="1" max="12" value={dayHours} onChange={e => setDayHours(e.target.value)}
                  className="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" data-testid="capacity-dialog-day-hours" />
                <span className="text-sm text-gray-500">h</span>
              </div>
              {selectedDays.size > 0 && dayTotalMinutes > 0 && (
                <div className="mt-2 rounded-lg bg-purple-50 px-3 py-1.5 text-xs text-purple-700 dark:bg-purple-900/20 dark:text-purple-300">
                  Total: {minutesToDisplay(selectedDays.size * dayTotalMinutes)} ({selectedDays.size} × {dayHours}h)
                </div>
              )}
            </div>

            {/* Wiederholung im Kalendermodus */}
            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input type="checkbox" checked={repeat} onChange={e => setRepeat(e.target.checked)} className="rounded border-gray-300" />
                Wöchentlich wiederholen
              </label>
              {repeat && (
                <div className="mt-2 flex items-center gap-2 pl-6">
                  <span className="text-xs text-gray-500">Bis</span>
                  <input type="date" value={endDate} min={[...selectedDays].sort()[0] || initialWeek}
                    onChange={e => setEndDate(e.target.value)}
                    className="rounded-lg border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200" />
                </div>
              )}
            </div>

            {/* Aktionen */}
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
                Abbrechen
              </button>
              <button
                onClick={() => {
                  if (selectedDays.size === 0 || dayTotalMinutes <= 0 || !projectId) return;
                  const sortedDays = [...selectedDays].sort();
                  for (const dayIso of sortedDays) {
                    onSave({
                      capacity_project_id: projectId,
                      week_start: dayIso,
                      minutes: dayTotalMinutes,
                      allocation_type: 'day',
                      repeat,
                      end_date: endDate || undefined,
                      interval_weeks: 1,
                    });
                  }
                }}
                disabled={selectedDays.size === 0 || dayTotalMinutes <= 0}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                data-testid="capacity-dialog-save-days"
              >
                {selectedDays.size > 1 ? `${selectedDays.size} Tage speichern` : 'Speichern'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Project Dialog ───────────────────────────────────────────────────────────

interface AvailableProjectOption {
  name: string;
  source: 'both' | 'toggl' | 'taskpilot';
  toggl_project_id: number | null;
  project_id: string | null;
  icon_url: string | null;
  icon_emoji: string | null;
  color: string;
  client_name: string | null;
  billable: boolean;
}

function ProjectDialog({
  open, onClose, onSave, onDelete, initial, appLogoUrl,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (data: Partial<CapProject> & { toggl_project_id?: number }) => void;
  onDelete?: () => void;
  initial?: CapProject | null;
  appLogoUrl?: string | null;
}) {
  const [name, setName] = useState(initial?.name || '');
  const [color, setColor] = useState(initial?.color || '#3B82F6');
  const [clientName, setClientName] = useState(initial?.client_name || '');
  const [hourlyRate, setHourlyRate] = useState(initial?.hourly_rate?.toString() || '');
  const [isBillable, setIsBillable] = useState(initial?.is_billable ?? true);
  const [status, setStatus] = useState<'bestätigt' | 'vorläufig'>(initial?.status || 'bestätigt');
  const [notes, setNotes] = useState(initial?.notes || '');
  const [iconEmoji, setIconEmoji] = useState(initial?.icon_emoji || '');
  const [iconUrl, setIconUrl] = useState(initial?.icon_url || '');
  const [projectId, setProjectId] = useState<string | null>(initial?.project_id || null);
  const [togglProjectId, setTogglProjectId] = useState<number | null>(initial?.toggl_project_id || null);

  const [available, setAvailable] = useState<AvailableProjectOption[]>([]);
  const [loadingAvail, setLoadingAvail] = useState(false);
  const [filter, setFilter] = useState('');
  const [showPicker, setShowPicker] = useState(!initial);
  const [iconPickerOpen, setIconPickerOpen] = useState(false);

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
    setProjectId(initial?.project_id || null);
    setTogglProjectId(initial?.toggl_project_id || null);
    setShowPicker(!initial);
    setFilter('');
  }, [initial]);

  useEffect(() => {
    if (open && !initial && available.length === 0) {
      setLoadingAvail(true);
      api.get<AvailableProjectOption[]>('/api/capacity/available-projects')
        .then(setAvailable)
        .catch(() => {})
        .finally(() => setLoadingAvail(false));
    }
  }, [open, initial]);

  const filtered = useMemo(() => {
    if (!filter) return available;
    const term = filter.toLowerCase();
    return available.filter(p =>
      p.name.toLowerCase().includes(term) || (p.client_name || '').toLowerCase().includes(term)
    );
  }, [available, filter]);

  if (!open) return null;

  const colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#6366F1', '#84CC16', '#F97316'];

  const sourceBadge = (src: string) => {
    if (src === 'both') return <span className="rounded bg-emerald-100 px-1 py-0.5 text-[9px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">Toggl + TaskPilot</span>;
    if (src === 'toggl') return <span className="rounded bg-purple-100 px-1 py-0.5 text-[9px] font-medium text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">Toggl</span>;
    return <span className="rounded bg-blue-100 px-1 py-0.5 text-[9px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">TaskPilot</span>;
  };

  const handleSelectAvailable = (p: AvailableProjectOption) => {
    setName(p.name);
    setColor(p.color);
    setIconUrl(p.icon_url || '');
    setIconEmoji(p.icon_emoji || '');
    setClientName(p.client_name || '');
    setIsBillable(p.billable);
    setProjectId(p.project_id);
    setTogglProjectId(p.toggl_project_id);
    setShowPicker(false);
  };

  const handleIconUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const token = localStorage.getItem('taskpilot_token');
      const res = await fetch('/api/uploads/icons', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) return;
      const { url } = await res.json();
      setIconUrl(url);
      setIconEmoji('');
    } catch { /* ignore */ }
  };

  const handleSave = () => {
    if (!name.trim()) return;
    let finalIconUrl = iconUrl || null;
    if (!finalIconUrl && !iconEmoji && !isBillable && appLogoUrl) {
      finalIconUrl = appLogoUrl;
    }
    onSave({
      name: name.trim(),
      color,
      client_name: clientName || null,
      hourly_rate: hourlyRate ? parseFloat(hourlyRate) : null,
      is_billable: isBillable,
      status,
      notes: notes || null,
      icon_emoji: iconEmoji || null,
      icon_url: finalIconUrl,
      project_id: projectId,
      toggl_project_id: togglProjectId ?? undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" data-testid="capacity-project-dialog">
      <div className="w-full max-w-lg rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-700 dark:bg-gray-900 max-h-[90vh] overflow-y-auto">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {initial ? 'Projekt bearbeiten' : 'Kapazitätsprojekt'}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Projekt-Picker (nur bei Neuanlage) */}
        {!initial && showPicker && (
          <div className="mb-4 space-y-2">
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Bestehendes Projekt übernehmen</label>
            <input
              type="text"
              placeholder="Projekt suchen (Toggl + TaskPilot)..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              data-testid="capacity-project-search"
              autoFocus
            />
            <div className="max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
              {loadingAvail ? (
                <div className="flex items-center justify-center py-6">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                </div>
              ) : filtered.length === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-gray-400">Keine Projekte gefunden</p>
              ) : (
                filtered.map((p, i) => (
                  <button
                    key={`${p.source}-${p.name}-${i}`}
                    onClick={() => handleSelectAvailable(p)}
                    className="flex w-full items-center gap-2 border-b border-gray-100 px-3 py-2 text-left text-sm transition last:border-b-0 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50"
                    data-testid={`capacity-avail-${i}`}
                  >
                    <ProjectIcon iconUrl={p.icon_url} iconEmoji={p.icon_emoji} color={p.color} size={20} />
                    <span className="flex-1 truncate font-medium text-gray-800 dark:text-gray-200">{p.name}</span>
                    {p.client_name && <span className="text-xs text-gray-400 mr-1">{p.client_name}</span>}
                    {sourceBadge(p.source)}
                  </button>
                ))
              )}
            </div>
            <div className="border-t border-gray-100 pt-2 dark:border-gray-800">
              <button
                onClick={() => setShowPicker(false)}
                className="text-xs font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400"
                data-testid="capacity-project-new"
              >
                + Komplett neues Projekt erstellen
              </button>
            </div>
          </div>
        )}

        {/* Rückkehr zum Picker */}
        {!initial && !showPicker && (
          <button
            onClick={() => setShowPicker(true)}
            className="mb-3 text-xs text-gray-500 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-indigo-400"
          >
            ← Bestehendes Projekt auswählen
          </button>
        )}

        {/* Detail-Formular */}
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
            <input
              type="text" value={name} onChange={e => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              data-testid="capacity-project-name"
              autoFocus={!showPicker || !!initial}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Icon / Farbe</label>
            <div className="flex items-center gap-3">
              <ProjectIcon iconUrl={iconUrl || null} iconEmoji={iconEmoji || null} color={color} size={28} />
              <div className="flex flex-wrap gap-1.5">
                {colors.map(c => (
                  <button
                    key={c}
                    onClick={() => { setColor(c); setIconEmoji(''); setIconUrl(''); }}
                    className={`h-5 w-5 rounded-full border-2 transition ${color === c && !iconEmoji && !iconUrl ? 'border-gray-800 dark:border-white scale-110' : 'border-transparent'}`}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
              <button
                onClick={() => setIconPickerOpen(true)}
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                data-testid="capacity-project-icon-picker-btn"
              >
                Icon wählen
              </button>
              <label className="cursor-pointer rounded-lg border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
                Bild
                <input type="file" accept="image/*" className="hidden" onChange={handleIconUpload} data-testid="capacity-project-icon-upload" />
              </label>
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

        <div className="mt-5 flex items-center justify-between">
          {initial && onDelete ? (
            <button
              onClick={onDelete}
              className="rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
              data-testid="capacity-project-delete"
            >
              Projekt löschen
            </button>
          ) : <div />}
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
              Abbrechen
            </button>
            <button
              onClick={handleSave}
              disabled={!name.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              data-testid="capacity-project-save"
            >
              Speichern
            </button>
          </div>
        </div>

        {/* LucideIconPicker Popover */}
        {iconPickerOpen && (
          <div className="absolute inset-0 z-60">
            <LucideIconPicker
              currentIcon={iconEmoji || null}
              onSelect={(iconName) => {
                if (iconName) {
                  setIconEmoji(iconName);
                  setIconUrl('');
                } else {
                  setIconEmoji('');
                }
                setIconPickerOpen(false);
              }}
              onClose={() => setIconPickerOpen(false)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Context Menu ─────────────────────────────────────────────────────────────

function ContextMenu({
  x, y, alloc, onClose, onDelete, onDeleteSeries, onDeleteFrom, onShift, onShiftSingle,
}: {
  x: number; y: number;
  alloc: Allocation;
  onClose: () => void;
  onDelete: () => void;
  onDeleteSeries: () => void;
  onDeleteFrom: () => void;
  onShift: (weeks: number) => void;
  onShiftSingle: (allocId: string, weeks: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const hasSeries = !!alloc.series_id;

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
      {hasSeries && (
        <>
          <button onClick={onDeleteSeries} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20">
            <Trash2 className="h-4 w-4" /> Ganze Serie löschen
          </button>
          <button onClick={onDeleteFrom} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <Trash2 className="h-4 w-4" /> Serie ab hier löschen
          </button>
        </>
      )}
      <hr className="my-1 border-gray-200 dark:border-gray-700" />
      {hasSeries ? (
        <>
          <button onClick={() => onShift(1)} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <ArrowRightLeft className="h-4 w-4" /> Serie +1 Woche verschieben
          </button>
          <button onClick={() => onShift(-1)} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <ArrowRightLeft className="h-4 w-4" /> Serie −1 Woche verschieben
          </button>
        </>
      ) : (
        <>
          <button onClick={() => onShiftSingle(alloc.id, 1)} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <ArrowRightLeft className="h-4 w-4" /> +1 Woche verschieben
          </button>
          <button onClick={() => onShiftSingle(alloc.id, -1)} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
            <ArrowRightLeft className="h-4 w-4" /> −1 Woche verschieben
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
  const [appLogoUrl, setAppLogoUrl] = useState<string | null>(null);

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
    const from = toIso(startDate);
    const to = toIso(endDate);
    const [projRes, allocRes, summaryRes, timeOffRes] = await Promise.allSettled([
      api.get<CapProject[]>('/api/capacity/projects'),
      api.get<Allocation[]>(`/api/capacity/allocations?from=${from}&to=${to}&include_tentative=${showTentative}`),
      api.get<WeeklySummary[]>(`/api/capacity/weekly-summary?from=${from}&to=${to}&include_tentative=${showTentative}`),
      api.get<TimeOffEntry[]>(`/api/capacity/time-off?year=${startDate.getFullYear()}`),
    ]);
    if (projRes.status === 'fulfilled') setProjects(projRes.value);
    if (allocRes.status === 'fulfilled') setAllocations(allocRes.value);
    else console.warn('Allocations laden fehlgeschlagen — evtl. Migration pending:', allocRes.reason);
    if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value);
    if (timeOffRes.status === 'fulfilled') setTimeOff(timeOffRes.value);
    setLoading(false);
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
      .then(s => {
        setBgUrl(s.capacity_background_url ?? null);
        setAppLogoUrl(s.app_logo_url ?? null);
      })
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
    allocation_type: 'week' | 'day';
    repeat: boolean;
    end_date?: string;
    interval_weeks?: number;
  }) => {
    try {
      if (data.repeat && data.end_date) {
        await api.post('/api/capacity/allocations/repeat', {
          capacity_project_id: data.capacity_project_id,
          week_start: data.week_start,
          end_date: data.end_date,
          minutes: data.minutes,
          allocation_type: data.allocation_type,
          interval_weeks: data.interval_weeks || 1,
        });
      } else {
        await api.post('/api/capacity/allocations', {
          capacity_project_id: data.capacity_project_id,
          week_start: data.week_start,
          minutes: data.minutes,
          allocation_type: data.allocation_type,
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

  const handleShiftSingle = async (allocId: string, weeks: number) => {
    const alloc = allocations.find(a => a.id === allocId);
    if (!alloc) return;
    const d = new Date(alloc.week_start + 'T00:00:00');
    const shifted = new Date(d.getFullYear(), d.getMonth(), d.getDate() + weeks * 7);
    await api.patch(`/api/capacity/allocations/${allocId}`, { week_start: toIso(shifted) });
    setContextMenu(null);
    fetchData();
  };

  const handleAllocDrop = async (allocId: string, targetWeekStr: string) => {
    const alloc = allocations.find(a => a.id === allocId);
    if (!alloc || alloc.week_start === targetWeekStr) return;
    await api.patch(`/api/capacity/allocations/${allocId}`, { week_start: targetWeekStr });
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

  // ── Toggl Ist-Daten als Wochen-Map für Inline-Anzeige ──────────────────────

  const togglWeekMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const proj of planVsActual) {
      for (const w of proj.weeks) {
        map[w.week_start] = (map[w.week_start] || 0) + w.actual_minutes;
      }
    }
    return map;
  }, [planVsActual]);

  const planVsActualByProject = useMemo(() => {
    const togglToCapacity: Record<number, string> = {};
    for (const p of projects) {
      if (p.toggl_project_id) togglToCapacity[p.toggl_project_id] = p.id;
    }
    const map: Record<string, Record<string, number>> = {};
    for (const proj of planVsActual) {
      const capId = togglToCapacity[proj.toggl_project_id];
      if (!capId) continue;
      if (!map[capId]) map[capId] = {};
      for (const w of proj.weeks) {
        map[capId][w.week_start] = (map[capId][w.week_start] || 0) + w.actual_minutes;
      }
    }
    return map;
  }, [planVsActual, projects]);

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
      style={bgUrl
        ? bgUrl.startsWith('gradient:')
          ? { background: bgUrl.slice('gradient:'.length) }
          : { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' }
        : undefined
      }
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
      <div className="flex-1 overflow-hidden" data-testid="capacity-timeline">
        <div className="h-full w-full overflow-y-auto">
          {/* Auslastungs-Header (Runn.io-Stil) */}
          <div className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
            {/* Wochenlabels */}
            <div className="flex">
              <div className="flex w-56 min-w-56 shrink-0 items-end border-r border-gray-200 bg-white px-3 pb-1 dark:border-gray-700 dark:bg-gray-900">
                <span className="text-[10px] font-semibold text-gray-500 uppercase dark:text-gray-400">Woche</span>
              </div>
              <div className="flex flex-1">
                {weeks.map((week) => {
                  const weekStr = toIso(week);
                  const isYear = viewRange === '1y';
                  const isHalf = viewRange === '6m';
                  const showMonthLabel = isYear && week.getDate() <= 7;
                  const todayOffset = getTodayOffset(week);
                  return (
                    <div key={weekStr} className={`relative ${getColClass(viewRange)} flex items-end justify-center pb-0.5 border-r border-gray-100 dark:border-gray-800`}>
                      {!isYear && !isHalf && (
                        <span className="text-[10px] text-gray-500 dark:text-gray-400 truncate">{formatWeek(week)}</span>
                      )}
                      {isHalf && (
                        <span className="text-[9px] text-gray-500 dark:text-gray-400 truncate">{week.getDate()}.{week.getMonth() + 1}</span>
                      )}
                      {showMonthLabel && (
                        <span className="text-[9px] font-medium text-gray-600 dark:text-gray-400 truncate">
                          {week.toLocaleDateString('de-CH', { month: 'short' })}
                        </span>
                      )}
                      {todayOffset !== null && (
                        <div className="absolute top-0 bottom-0 w-[2px] bg-red-500 dark:bg-red-400 z-10 pointer-events-none" style={{ left: `${todayOffset}%` }} />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Auslastungs-Blöcke */}
            <div className="flex">
              <div className="flex w-56 min-w-56 shrink-0 items-center border-r border-gray-200 bg-white px-3 py-1.5 dark:border-gray-700 dark:bg-gray-900">
                <span className="text-[10px] font-semibold text-gray-500 uppercase dark:text-gray-400">Auslastung</span>
              </div>
              <div className="flex flex-1">
                {weeks.map((week) => {
                  const weekStr = toIso(week);
                  const s = summary.find(s => s.week_start === weekStr);
                  const util = s?.utilization_pct || 0;
                  const isYear = viewRange === '1y';
                  const isHalf = viewRange === '6m';
                  const isPast = week < new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
                  const actualMin = togglWeekMap[weekStr] || 0;
                  const plannedMin = s?.planned_minutes || 0;

                  let bgColor: string;
                  let textColor: string;
                  if (util === 0) {
                    bgColor = 'bg-gray-100 dark:bg-gray-800';
                    textColor = 'text-gray-400 dark:text-gray-500';
                  } else if (util <= 60) {
                    bgColor = 'bg-emerald-100 dark:bg-emerald-900/40';
                    textColor = 'text-emerald-700 dark:text-emerald-300';
                  } else if (util <= 85) {
                    bgColor = 'bg-emerald-200 dark:bg-emerald-800/50';
                    textColor = 'text-emerald-800 dark:text-emerald-200';
                  } else if (util <= 100) {
                    bgColor = 'bg-amber-200 dark:bg-amber-800/50';
                    textColor = 'text-amber-800 dark:text-amber-200';
                  } else {
                    bgColor = 'bg-red-200 dark:bg-red-900/50';
                    textColor = 'text-red-800 dark:text-red-200';
                  }

                  return (
                    <div
                      key={weekStr}
                      className={`relative ${getColClass(viewRange)} flex flex-col items-center justify-center border-r border-white/50 dark:border-gray-900/50 ${bgColor} py-1`}
                      title={`${formatWeek(week)} — ${Math.round(util)}% (${minutesToDisplay(plannedMin)} geplant${isPast && actualMin > 0 ? `, ${minutesToDisplay(actualMin)} effektiv` : ''} / ${minutesToDisplay(s?.available_minutes || 2400)})`}
                    >
                      {util > 100 && (
                        <div className="absolute inset-x-0 top-0 h-[3px] bg-red-600 dark:bg-red-500" />
                      )}
                      {!isYear && (
                        <span className={`text-[10px] font-bold leading-tight ${textColor} ${isHalf ? 'text-[9px]' : ''}`}>
                          {Math.round(util)}%
                        </span>
                      )}
                      {isYear && util > 0 && (
                        <div
                          className={`h-2 w-2 rounded-full ${util > 100 ? 'bg-red-500' : util > 85 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                        />
                      )}
                      {isPast && actualMin > 0 && !isYear && (
                        <span className={`text-[8px] leading-tight ${
                          actualMin > plannedMin * 1.05 ? 'text-red-600 dark:text-red-400' :
                          actualMin < plannedMin * 0.8 ? 'text-amber-600 dark:text-amber-400' :
                          'text-emerald-600 dark:text-emerald-400'
                        }`}>
                          {Math.round(actualMin / 60)}h
                        </span>
                      )}
                      {(() => {
                        const offset = getTodayOffset(week);
                        if (offset === null) return null;
                        return <div className="absolute top-0 bottom-0 w-[2px] bg-red-500 dark:bg-red-400 z-10 pointer-events-none" style={{ left: `${offset}%` }} />;
                      })()}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Ferien-Zeile */}
          {timeOff.length > 0 && (
            <div className="flex items-stretch border-b border-amber-200 dark:border-amber-800/50 bg-amber-50/50 dark:bg-amber-900/10">
              <div className="flex w-56 min-w-56 shrink-0 items-center gap-2 border-r border-gray-200 bg-amber-50 px-3 py-1.5 dark:border-gray-700 dark:bg-amber-900/20">
                <Palmtree className="h-4 w-4 text-amber-500" />
                <span className="text-xs font-medium text-amber-700 dark:text-amber-400">Ferien / Frei</span>
              </div>
              <div className="flex flex-1">
                {weeks.map(week => {
                  const weekStr = toIso(week);
                  const hoursOff = timeOffWeekMap[weekStr] || 0;
                  const todayOffset = getTodayOffset(week);
                  return (
                    <div key={weekStr} className={`relative flex ${getColClass(viewRange)} items-center justify-center border-r border-amber-100 dark:border-amber-900/30`}>
                      {hoursOff > 0 && (
                        <div className={`rounded px-1 py-0.5 text-[9px] font-medium ${hoursOff >= 40 ? 'bg-amber-200 text-amber-800 dark:bg-amber-800/40 dark:text-amber-300' : 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400'}`}>
                          {viewRange === '1y' ? '' : `${hoursOff}h`}
                        </div>
                      )}
                      {todayOffset !== null && (
                        <div className="absolute top-0 bottom-0 w-[2px] bg-red-500 dark:bg-red-400 z-10 pointer-events-none" style={{ left: `${todayOffset}%` }} />
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
                  onEditProject={(p) => setProjectDialog({ open: true, editing: p })}
                  onContextMenu={(e, alloc) => {
                    e.preventDefault();
                    setContextMenu({ x: e.clientX, y: e.clientY, alloc });
                  }}
                  colClass={getColClass(viewRange)}
                  viewRange={viewRange}
                  onAllocDrop={handleAllocDrop}
                  planVsActualByProject={planVsActualByProject}
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
        onDelete={projectDialog.editing ? async () => {
          await api.delete(`/api/capacity/projects/${projectDialog.editing!.id}`);
          setProjectDialog({ open: false, editing: null });
          fetchData();
        } : undefined}
        initial={projectDialog.editing}
        appLogoUrl={appLogoUrl}
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
          onShiftSingle={handleShiftSingle}
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
