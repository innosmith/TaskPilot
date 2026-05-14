import { useRef, useState, useMemo, useCallback, lazy, Suspense } from 'react';
import type { TaskDetail, Tag, TaskUpdatePayload, PipelineColumn, Project, BoardColumn } from '../../types';
import { api } from '../../api/client';

const CalendarSlotPickerLazy = lazy(() => import('./CalendarSlotPicker'));
import {
  AttrRow, ATTR_SELECT, RecurrenceSelector,
  AgendaIcon, CalendarIcon, FolderIcon, ColumnsIcon, UserIcon,
  TagIcon, RepeatIcon, AgentSmallIcon, ShieldIcon, LockIcon,
  CrmLinkIcon, CloseIcon, MailIcon,
} from './shared';
import type { ModelsData } from './shared';
import CustomSelect from './CustomSelect';
import type { SelectOption } from './CustomSelect';

interface TaskDetailSidebarProps {
  task: TaskDetail;
  taskId: string;
  isOwner: boolean;
  authUser: { id: string; email: string; avatar_url?: string | null } | null;
  allProjects: Project[];
  pipelineCols: PipelineColumn[];
  boardColumns: BoardColumn[];
  boardMembers: { user_id: string; display_name: string; avatar_url?: string | null }[];
  allTags: Tag[];
  models: ModelsData | null;
  defaultLocalModel: string;
  updateTask: (payload: TaskUpdatePayload) => Promise<void>;
  handleProjectChange: (newProjectId: string) => Promise<void>;
  toggleTag: (tag: Tag) => Promise<void>;
  onTagsChanged: () => Promise<void>;
}

const DATA_CLASS_OPTIONS = [
  { value: 'internal', label: 'Intern' },
  { value: 'confidential', label: 'Vertraul.' },
  { value: 'strictly_confidential', label: 'Streng v.' },
] as const;

const AUTONOMY_OPTIONS = [
  { value: 'L0', label: 'L0 – Block' },
  { value: 'L1', label: 'L1 – Approve' },
  { value: 'L2', label: 'L2 – Notify' },
  { value: 'L3', label: 'L3 – Auto' },
] as const;

const CALENDAR_PRESETS = [15, 30, 60, 120] as const;


function formatDateDE(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('de-CH', { day: 'numeric', month: 'long', year: 'numeric' });
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ', ' + d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
}

export default function TaskDetailSidebar({
  task, taskId, isOwner, authUser, allProjects, pipelineCols,
  boardColumns, boardMembers, allTags, models, defaultLocalModel,
  updateTask, handleProjectChange, toggleTag, onTagsChanged,
}: TaskDetailSidebarProps) {
  const [showTagPicker, setShowTagPicker] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#6B7280');
  const [creatingTag, setCreatingTag] = useState(false);
  const [deletingTagId, setDeletingTagId] = useState<string | null>(null);
  const dateInputRef = useRef<HTMLInputElement>(null);
  const [showCalendarPicker, setShowCalendarPicker] = useState(false);
  const recurrenceEndRef = useRef<HTMLInputElement>(null);
  const [removingCalEvent, setRemovingCalEvent] = useState(false);

  const today = new Date().toISOString().split('T')[0];
  const isDueToday = task.due_date === today;
  const isDueOverdue = task.due_date ? task.due_date < today : false;

  const isTemplate = !!task.recurrence_rule && !task.template_id;
  const showCalendarSection = isOwner && isTemplate;
  const showAgentConfig = isOwner && task.assignee === 'agent';
  const showPipedrive = !!(task.pipedrive_deal_id || task.pipedrive_person_id);

  const handleRemoveCalendarEvent = useCallback(async () => {
    if (!task.calendar_event_id) return;
    setRemovingCalEvent(true);
    try {
      await api.delete(`/api/calendar/events/${task.calendar_event_id}`);
    } catch {
      // Fallback: Event existiert evtl. nicht mehr
    }
    await updateTask({ calendar_event_id: null });
    setRemovingCalEvent(false);
  }, [task.calendar_event_id, updateTask]);

  const assigneeOptions = useMemo<SelectOption[]>(() => {
    const avatarEl = (url: string | null | undefined, fallbackLetter: string, colorClass: string) => {
      if (url) {
        return <img src={url} alt="" className="h-5 w-5 rounded-full object-cover" />;
      }
      return (
        <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold ${colorClass}`}>
          {fallbackLetter}
        </span>
      );
    };

    const opts: SelectOption[] = [
      {
        value: 'unassigned',
        label: 'Nicht zugewiesen',
        icon: <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-gray-200 text-[9px] font-bold text-gray-500 dark:bg-gray-700 dark:text-gray-400">?</span>,
      },
    ];
    if (authUser) {
      const ownerMember = boardMembers.find((bm) => bm.user_id === authUser.id);
      const letter = (ownerMember?.display_name?.[0] ?? authUser.email[0] ?? '?').toUpperCase();
      const displayName = ownerMember?.display_name ?? authUser.email;
      opts.push({
        value: authUser.id,
        label: displayName,
        icon: avatarEl(ownerMember?.avatar_url ?? authUser.avatar_url, letter, 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900 dark:text-indigo-300'),
      });
    }
    for (const m of boardMembers.filter((bm) => bm.user_id !== authUser?.id)) {
      const letter = (m.display_name[0] ?? '?').toUpperCase();
      opts.push({
        value: m.user_id,
        label: m.display_name,
        icon: avatarEl(m.avatar_url, letter, 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900 dark:text-emerald-300'),
      });
    }
    if (isOwner) {
      opts.push({
        value: 'agent',
        label: 'AI Agent',
        icon: (
          <svg className="h-5 w-5 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
          </svg>
        ),
      });
    }
    return opts;
  }, [authUser, boardMembers, isOwner]);

  const projectOptions = useMemo<SelectOption[]>(
    () => allProjects.map((p) => ({
      value: p.id,
      label: p.name,
      icon: p.icon_emoji ? <span className="text-sm leading-none">{p.icon_emoji}</span> : undefined,
    })),
    [allProjects],
  );

  const dueDateClasses = isDueOverdue
    ? 'border-amber-200 bg-amber-50/60 text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300'
    : isDueToday
      ? 'border-indigo-200 bg-indigo-50/60 text-indigo-700 dark:border-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-300'
      : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300';

  return (
    <div className="flex flex-col gap-0.5 px-5 py-4 bg-gray-50/40 dark:bg-gray-900/20">
      {/* Origin Badges */}
      {task.email_message_id && (
        <div className="mb-3 flex items-center gap-1.5 rounded-lg bg-sky-50 px-2.5 py-1.5 text-[11px] font-medium text-sky-600 dark:bg-sky-950/40 dark:text-sky-400">
          <MailIcon className="h-3 w-3" /> Aus E-Mail erstellt
        </div>
      )}
      {task.calendar_event_id && !task.email_message_id && (
        <div className="mb-3 flex items-center gap-1.5 rounded-lg bg-violet-50 px-2.5 py-1.5 text-[11px] font-medium text-violet-600 dark:bg-violet-950/40 dark:text-violet-400">
          <CalendarIcon className="h-3 w-3" /> Verknüpft mit Kalender
        </div>
      )}

      {/* ── Kern-Attribute ── */}

      {isOwner && (
        <AttrRow icon={AgendaIcon} label="Agenda">
          <select
            value={task.pipeline_column_id ?? ''}
            onChange={(e) => updateTask({ pipeline_column_id: e.target.value || null })}
            className={ATTR_SELECT}
          >
            <option value="">– Keine –</option>
            {pipelineCols.map((c) => (
              <option key={c.id} value={c.id}>
                {c.icon_emoji ? `${c.icon_emoji} ` : ''}{c.name}
              </option>
            ))}
          </select>
        </AttrRow>
      )}

      <AttrRow icon={CalendarIcon} label="Fällig am">
        <input
          ref={dateInputRef}
          type="date"
          value={task.due_date ?? ''}
          onChange={(e) => updateTask({ due_date: e.target.value || null })}
          className="sr-only"
        />
        <button
          onClick={() => dateInputRef.current?.showPicker()}
          className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${dueDateClasses}`}
        >
          <CalendarIcon className="h-3.5 w-3.5 shrink-0 opacity-50" />
          {task.due_date ? (
            <span>
              {isDueToday && <span className="font-semibold">Heute, </span>}
              {isDueOverdue && <span className="font-semibold">Überfällig · </span>}
              {formatDateDE(task.due_date)}
            </span>
          ) : (
            <span className="text-gray-400 dark:text-gray-500">Kein Datum</span>
          )}
          {task.due_date && (
            <button
              onClick={(e) => { e.stopPropagation(); updateTask({ due_date: null }); }}
              className="ml-auto rounded p-0.5 hover:bg-black/5 dark:hover:bg-white/10"
            >
              <CloseIcon className="h-3 w-3" />
            </button>
          )}
        </button>
      </AttrRow>

      <AttrRow icon={FolderIcon} label="Projekt">
        <CustomSelect
          value={task.project_id}
          options={projectOptions}
          onChange={handleProjectChange}
          searchable={allProjects.length > 6}
        />
      </AttrRow>

      <AttrRow icon={ColumnsIcon} label="Board-Spalte">
        <select
          value={task.board_column_id}
          onChange={(e) => updateTask({ board_column_id: e.target.value })}
          className={ATTR_SELECT}
        >
          {boardColumns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.icon_emoji ? `${c.icon_emoji} ` : ''}{c.name}
            </option>
          ))}
        </select>
      </AttrRow>

      <AttrRow icon={UserIcon} label="Zuständig">
        <CustomSelect
          value={task.assignee}
          options={assigneeOptions}
          onChange={(val) => updateTask({ assignee: val })}
          searchable={boardMembers.length > 6}
        />
      </AttrRow>

      {/* ── Organisation ── */}
      <div className="my-2" />

      <AttrRow icon={TagIcon} label="Tags" align="start">
        <div className="flex flex-wrap items-center gap-1.5">
          {task.tags.map((t) => (
            <span
              key={t.id}
              className="group/tag inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium"
              style={{ backgroundColor: t.color + '22', color: t.color }}
            >
              {t.name}
              <button
                onClick={() => toggleTag(t)}
                className="rounded-full p-0.5 opacity-70 transition-opacity hover:opacity-100"
              >
                <CloseIcon className="h-3 w-3" />
              </button>
            </span>
          ))}
          <button
            onClick={() => setShowTagPicker(!showTagPicker)}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-gray-300 px-2.5 py-1 text-[11px] font-medium text-gray-500 transition-colors hover:border-indigo-400 hover:bg-indigo-50/50 hover:text-indigo-600 dark:border-gray-600 dark:text-gray-400 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/30 dark:hover:text-indigo-400"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Tag
          </button>
        </div>
        {showTagPicker && (
          <div className="mt-2 max-h-[240px] space-y-2 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50/50 p-2.5 dark:border-gray-700 dark:bg-gray-800/50">
            {allTags.filter((t) => !task.tags.some((tt) => tt.id === t.id)).length > 0 && (
              <div className="flex flex-wrap gap-1">
                {allTags
                  .filter((t) => !task.tags.some((tt) => tt.id === t.id))
                  .map((t) => (
                    <button
                      key={t.id}
                      onClick={() => toggleTag(t)}
                      className="rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors hover:opacity-80"
                      style={{ backgroundColor: t.color + '22', color: t.color }}
                    >
                      {t.name}
                    </button>
                  ))}
              </div>
            )}
            {isOwner && (
              <div className="border-t border-gray-200 pt-2 dark:border-gray-700">
                <div className="flex items-center gap-1.5">
                  <input
                    type="color"
                    value={newTagColor}
                    onChange={(e) => setNewTagColor(e.target.value)}
                    className="h-6 w-6 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
                  />
                  <input
                    type="text"
                    value={newTagName}
                    onChange={(e) => setNewTagName(e.target.value)}
                    onKeyDown={async (e) => {
                      if (e.key === 'Enter' && newTagName.trim()) {
                        setCreatingTag(true);
                        try {
                          const created = await api.post<{ id: string; name: string; color: string }>('/api/tags', { name: newTagName.trim(), color: newTagColor });
                          await onTagsChanged();
                          await toggleTag(created as unknown as Tag);
                          setNewTagName('');
                        } catch { /* tag might already exist */ }
                        setCreatingTag(false);
                      }
                    }}
                    placeholder="Neuer Tag…"
                    disabled={creatingTag}
                    className="min-w-0 flex-1 rounded border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-700 outline-none placeholder:text-gray-400 focus:border-indigo-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300"
                  />
                </div>
              </div>
            )}
            {isOwner && allTags.length > 0 && (
              <div className="border-t border-gray-200 pt-2 dark:border-gray-700">
                <p className="mb-1 text-[10px] text-gray-400 dark:text-gray-500">Tags verwalten:</p>
                <div className="flex flex-wrap gap-1">
                  {allTags.map((t) => (
                    <span
                      key={t.id}
                      className="inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium"
                      style={{ backgroundColor: t.color + '22', color: t.color }}
                    >
                      {deletingTagId === t.id ? (
                        <>
                          <span className="mr-0.5">Löschen?</span>
                          <button
                            onClick={async () => {
                              await api.delete(`/api/tags/${t.id}`);
                              setDeletingTagId(null);
                              await onTagsChanged();
                            }}
                            className="rounded px-1 text-[9px] font-bold opacity-80 hover:opacity-100"
                          >
                            Ja
                          </button>
                          <button
                            onClick={() => setDeletingTagId(null)}
                            className="rounded px-1 text-[9px] opacity-60 hover:opacity-100"
                          >
                            Nein
                          </button>
                        </>
                      ) : (
                        <>
                          {t.name}
                          <button
                            onClick={() => setDeletingTagId(t.id)}
                            className="ml-0.5 rounded-full p-0.5 opacity-50 transition-opacity hover:opacity-100"
                            title="Tag löschen"
                          >
                            <CloseIcon className="h-2.5 w-2.5" />
                          </button>
                        </>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </AttrRow>

      <AttrRow icon={RepeatIcon} label="Wiederholung" align="start">
        <RecurrenceSelector
          value={task.recurrence_rule}
          isInstance={!!task.template_id}
          onChange={(rule) => updateTask({ recurrence_rule: rule })}
        />
      </AttrRow>

      {isTemplate && (
        <div className="mt-1 space-y-2 rounded-lg border border-gray-100 bg-white/60 p-3 dark:border-gray-800 dark:bg-gray-900/30">
          <div className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
            Wiederholungs-Begrenzung
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="w-[72px] shrink-0 text-[11px] text-gray-500 dark:text-gray-400">Enddatum</span>
              <input
                ref={recurrenceEndRef}
                type="date"
                value={task.recurrence_end_date ?? ''}
                onChange={(e) => updateTask({ recurrence_end_date: e.target.value || null })}
                className="sr-only"
              />
              <button
                onClick={() => recurrenceEndRef.current?.showPicker()}
                className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors border-gray-200 text-gray-700 hover:border-gray-300 dark:border-gray-700 dark:text-gray-300 dark:hover:border-gray-600`}
              >
                <CalendarIcon className="h-3.5 w-3.5 shrink-0 opacity-50" />
                {task.recurrence_end_date ? (
                  <span>{formatDateDE(task.recurrence_end_date)}</span>
                ) : (
                  <span className="text-gray-400 dark:text-gray-500">Unbegrenzt</span>
                )}
                {task.recurrence_end_date && (
                  <button
                    onClick={(e) => { e.stopPropagation(); updateTask({ recurrence_end_date: null }); }}
                    className="ml-auto rounded p-0.5 hover:bg-black/5 dark:hover:bg-white/10"
                  >
                    <CloseIcon className="h-3 w-3" />
                  </button>
                )}
              </button>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-[72px] shrink-0 text-[11px] text-gray-500 dark:text-gray-400">Max.</span>
              <select
                value={task.recurrence_max_instances?.toString() ?? ''}
                onChange={(e) => updateTask({ recurrence_max_instances: e.target.value ? Number(e.target.value) : null } as TaskUpdatePayload)}
                className={ATTR_SELECT}
              >
                <option value="">Unbegrenzt</option>
                <option value="5">5 Instanzen</option>
                <option value="10">10 Instanzen</option>
                <option value="20">20 Instanzen</option>
                <option value="50">50 Instanzen</option>
                <option value="100">100 Instanzen</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* ── Kalender (Owner-only) ── */}
      {(showCalendarSection || (isOwner && !isTemplate)) && <div className="my-2" />}

      {showCalendarSection && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 dark:border-indigo-900/50 dark:bg-indigo-950/20">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-indigo-700 dark:text-indigo-300">
            <CalendarIcon className="h-3.5 w-3.5" />
            Auto-Kalender
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {[null, ...CALENDAR_PRESETS].map((m) => {
              const active = task.calendar_duration_minutes === m;
              return (
                <button
                  key={m ?? 'off'}
                  onClick={() => updateTask({ calendar_duration_minutes: m })}
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
                    active
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
                  }`}
                >
                  {m == null ? 'Aus' : `${m}`}
                </button>
              );
            })}
            <div className="flex items-center gap-0.5">
              <input
                type="number"
                min={5}
                max={480}
                step={5}
                value={task.calendar_duration_minutes ?? ''}
                onChange={(e) =>
                  updateTask({ calendar_duration_minutes: e.target.value ? Number(e.target.value) : null })
                }
                className="w-12 rounded border border-gray-200 bg-white px-1 py-0.5 text-center text-[11px] dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                placeholder="Min"
              />
              <span className="text-[10px] text-gray-400">Min</span>
            </div>
          </div>
          <p className="mt-1.5 text-[10px] leading-tight text-gray-500 dark:text-gray-400">
            Bucht automatisch ab der eingestellten Uhrzeit. Bei Konflikten wird der nächste freie Slot gewählt.
          </p>
        </div>
      )}

      {isOwner && !isTemplate && (
        <AttrRow icon={CalendarIcon} label="Kalender" align="start">
          {task.calendar_event_id ? (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 rounded-lg bg-violet-50 px-2.5 py-1.5 text-[11px] font-medium text-violet-600 dark:bg-violet-950/30 dark:text-violet-400">
                <CalendarIcon className="h-3 w-3" />
                Termin blockiert
              </div>
              <button
                onClick={handleRemoveCalendarEvent}
                disabled={removingCalEvent}
                className="text-[10px] text-gray-400 transition-colors hover:text-red-500 disabled:opacity-50 dark:text-gray-500 dark:hover:text-red-400"
              >
                {removingCalEvent ? 'Wird entfernt…' : 'Termin entfernen'}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowCalendarPicker(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-2.5 py-2 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
            >
              <CalendarIcon className="h-3.5 w-3.5" />
              Termin blockieren
            </button>
          )}
        </AttrRow>
      )}

      {showCalendarPicker && (
        <Suspense fallback={null}>
          <CalendarSlotPickerLazy
            taskTitle={task.title}
            taskDescription={task.description}
            initialDate={task.due_date}
            onConfirm={(eventId) => {
              updateTask({ calendar_event_id: eventId });
              setShowCalendarPicker(false);
            }}
            onClose={() => setShowCalendarPicker(false)}
          />
        </Suspense>
      )}

      {/* ── Agent-Konfiguration (Owner-only) ── */}
      {showAgentConfig && <div className="my-2" />}

      {showAgentConfig && (
        <>
          <AttrRow icon={AgentSmallIcon} label="LLM-Modell">
            <select
              value={task.llm_override ?? defaultLocalModel}
              onChange={(e) => updateTask({ llm_override: e.target.value })}
              className={ATTR_SELECT}
            >
              {models && (
                <>
                  <optgroup label="Lokal (Ollama)">
                    {models.local.map((m) => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Cloud">
                    {models.cloud.map((m) => (
                      <option key={m.id} value={m.id}>{m.name} ({m.provider})</option>
                    ))}
                  </optgroup>
                </>
              )}
            </select>
          </AttrRow>

          <AttrRow icon={ShieldIcon} label="Autonomie">
            <select
              value={task.autonomy_level}
              onChange={(e) => updateTask({ autonomy_level: e.target.value })}
              className={ATTR_SELECT}
            >
              {AUTONOMY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </AttrRow>

          <AttrRow icon={LockIcon} label="Datenklasse" align="start">
            <div className="flex gap-1">
              {DATA_CLASS_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  onClick={() => updateTask({ data_class: o.value })}
                  className={`flex-1 rounded-lg border px-2 py-1 text-[10px] font-medium transition-colors ${
                    task.data_class === o.value
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300'
                      : 'border-gray-200 bg-white text-gray-500 hover:border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:border-gray-600'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </AttrRow>
        </>
      )}

      {/* ── Pipedrive CRM ── */}
      {showPipedrive && <div className="my-2" />}

      {showPipedrive && (
        <AttrRow icon={CrmLinkIcon} label="Pipedrive" align="start">
          <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
            {task.pipedrive_deal_id && (
              <div className="flex items-center gap-1.5">
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400">
                  Deal
                </span>
                <span className="text-[11px]">#{task.pipedrive_deal_id}</span>
              </div>
            )}
            {task.pipedrive_person_id && (
              <div className="flex items-center gap-1.5">
                <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:bg-blue-950/40 dark:text-blue-400">
                  Person
                </span>
                <span className="text-[11px]">#{task.pipedrive_person_id}</span>
              </div>
            )}
          </div>
        </AttrRow>
      )}

      {/* ── Metadata ── */}
      <div className="mt-4 border-t border-gray-100 pt-3 dark:border-gray-800">
        <div className="space-y-0.5 text-[10px] text-gray-400 dark:text-gray-500">
          <div>Erstellt: {formatTimestamp(task.created_at)}</div>
          <div>Aktualisiert: {formatTimestamp(task.updated_at)}</div>
          <div className="font-mono opacity-50">ID: {taskId}</div>
        </div>
      </div>
    </div>
  );
}
