import { useState, useRef, useMemo, useEffect, useCallback } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { MentionsInput, Mention } from 'react-mentions';
import { api } from '../../api/client';
import type { ActivityLogEntry } from './shared';
import {
  SectionLabel,
  ActivityIcon,
  CommentDotIcon,
  HistoryIcon,
  formatActivityEvent,
} from './shared';

type ActivityFilter = 'all' | 'comments' | 'changes';

interface MentionableUser {
  id: string;
  display_name: string;
  avatar_url: string | null;
}

interface TaskDetailActivityProps {
  taskId: string;
  projectId?: string;
  activities: ActivityLogEntry[];
  onActivitiesChanged: (activities: ActivityLogEntry[]) => void;
  currentUserEmail?: string;
  isOwner: boolean;
  refreshTask: () => Promise<void>;
}

export default function TaskDetailActivity({
  taskId,
  projectId,
  activities,
  onActivitiesChanged,
  currentUserEmail,
  isOwner,
  refreshTask,
}: TaskDetailActivityProps) {
  const [commentText, setCommentText] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>('all');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [mentionableUsers, setMentionableUsers] = useState<MentionableUser[]>([]);
  const editRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!projectId) return;
    api
      .get<MentionableUser[]>(`/api/notifications/mentionable-users?project_id=${projectId}`)
      .then(setMentionableUsers)
      .catch(() => {});
  }, [projectId]);

  const mentionData = useMemo(
    () => mentionableUsers.map((u) => ({ id: u.id, display: u.display_name })),
    [mentionableUsers],
  );

  const commentCount = useMemo(
    () => activities.filter((a) => a.event_type === 'comment').length,
    [activities],
  );
  const changeCount = useMemo(
    () => activities.filter((a) => a.event_type !== 'comment').length,
    [activities],
  );

  const filteredActivities = useMemo(() => {
    if (activityFilter === 'comments') return activities.filter((a) => a.event_type === 'comment');
    if (activityFilter === 'changes') return activities.filter((a) => a.event_type !== 'comment');
    return activities;
  }, [activities, activityFilter]);

  const handleSubmitComment = async () => {
    const text = commentText.trim();
    if (!text || submittingComment) return;
    setSubmittingComment(true);
    try {
      await api.post<ActivityLogEntry>(`/api/tasks/${taskId}/activity`, {
        event_type: 'comment',
        details: { text },
      });
      setCommentText('');
      await refreshTask();
    } finally {
      setSubmittingComment(false);
    }
  };

  const canModify = (entry: ActivityLogEntry) =>
    entry.event_type === 'comment' && (isOwner || entry.actor === currentUserEmail);

  const startEditing = (entry: ActivityLogEntry) => {
    setEditingId(entry.id);
    setEditText((entry.details?.text as string) || '');
    setDeletingId(null);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditText('');
  };

  const saveEdit = async (entryId: string) => {
    const text = editText.trim();
    if (!text) return;
    try {
      const updated = await api.patch<ActivityLogEntry>(
        `/api/tasks/${taskId}/activity/${entryId}`,
        { text },
      );
      onActivitiesChanged(activities.map((a) => (a.id === entryId ? updated : a)));
    } finally {
      setEditingId(null);
      setEditText('');
    }
  };

  const confirmDelete = async (entryId: string) => {
    try {
      await api.delete(`/api/tasks/${taskId}/activity/${entryId}`);
      onActivitiesChanged(activities.filter((a) => a.id !== entryId));
    } finally {
      setDeletingId(null);
    }
  };

  const formatTimestamp = (iso: string) =>
    new Date(iso).toLocaleString('de-CH', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });

  const renderMentionText = useCallback((text: string) => {
    const parts = text.split(/(@\[[^\]]+\]\([^)]+\))/g);
    return parts.map((part, i) => {
      const match = part.match(/^@\[([^\]]+)\]\(([^)]+)\)$/);
      if (match) {
        return (
          <span key={i} className="inline-block rounded bg-indigo-100 px-1 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
            @{match[1]}
          </span>
        );
      }
      return <span key={i}>{part}</span>;
    });
  }, []);

  const filterTabs: { key: ActivityFilter; label: string; count?: number }[] = [
    { key: 'all', label: 'Alle' },
    { key: 'comments', label: 'Kommentare', count: commentCount },
    { key: 'changes', label: 'Änderungen', count: changeCount },
  ];

  return (
    <div>
      <SectionLabel icon={ActivityIcon} text="Aktivität" />

      {/* Comment input with @-mention autocomplete */}
      <div className="mb-3">
        <MentionsInput
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmitComment();
            }
          }}
          placeholder="Kommentar hinzufügen… (@Name für Erwähnung)"
          className="mentions-input"
          forceSuggestionsAboveCursor
        >
          <Mention
            trigger="@"
            data={mentionData}
            markup="@[__display__](__id__)"
            displayTransform={(_id: string, display: string) => `@${display}`}
            appendSpaceOnAdd
            className="mention-highlight"
          />
        </MentionsInput>
      </div>

      {/* Filter tabs */}
      <div className="mb-3 flex gap-1 rounded-lg bg-gray-100 p-0.5 dark:bg-gray-800">
        {filterTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActivityFilter(tab.key)}
            className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
              activityFilter === tab.key
                ? 'bg-indigo-600 text-white'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && ` (${tab.count})`}
          </button>
        ))}
      </div>

      {/* Activity feed */}
      <div className="space-y-2">
        {filteredActivities.length === 0 && (
          <p className="py-4 text-center text-xs text-gray-400 dark:text-gray-500">
            Keine Einträge
          </p>
        )}
        {filteredActivities.map((entry) => {
          const isComment = entry.event_type === 'comment';
          const Icon = isComment ? CommentDotIcon : HistoryIcon;
          const rawContent = isComment
            ? (entry.details?.text as string) || ''
            : formatActivityEvent(entry.event_type, entry.details);
          const content = rawContent;
          const modifiable = canModify(entry);
          const isEditing = editingId === entry.id;
          const isDeleting = deletingId === entry.id;

          return (
            <div
              key={entry.id}
              className="group relative flex items-start gap-2.5 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-700/50 dark:bg-gray-800/50"
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500" />
              <div className="min-w-0 flex-1">
                {isEditing ? (
                  <div>
                    <textarea
                      ref={editRef}
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          saveEdit(entry.id);
                        }
                        if (e.key === 'Escape') cancelEditing();
                      }}
                      autoFocus
                      rows={2}
                      className="w-full resize-none rounded border border-indigo-300 bg-white px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-indigo-300 dark:border-indigo-600 dark:bg-gray-800 dark:text-gray-200"
                    />
                    <div className="mt-1 flex gap-1.5">
                      <button
                        onClick={() => saveEdit(entry.id)}
                        disabled={!editText.trim()}
                        className="rounded bg-indigo-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        Speichern
                      </button>
                      <button
                        onClick={cancelEditing}
                        className="rounded px-2 py-0.5 text-[11px] font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                      >
                        Abbrechen
                      </button>
                    </div>
                  </div>
                ) : isDeleting ? (
                  <div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      {isComment ? renderMentionText(content) : content}
                    </p>
                    <div className="mt-1 flex items-center gap-1.5">
                      <span className="text-[11px] text-red-600 dark:text-red-400">Löschen?</span>
                      <button
                        onClick={() => confirmDelete(entry.id)}
                        className="rounded bg-red-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-red-700"
                      >
                        Ja
                      </button>
                      <button
                        onClick={() => setDeletingId(null)}
                        className="rounded px-2 py-0.5 text-[11px] font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                      >
                        Nein
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {isComment ? renderMentionText(content) : content}
                  </p>
                )}
                <p className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500">
                  {entry.actor} · {formatTimestamp(entry.created_at)}
                </p>
              </div>

              {modifiable && !isEditing && !isDeleting && (
                <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    onClick={() => startEditing(entry)}
                    className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
                    title="Bearbeiten"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => { setDeletingId(entry.id); setEditingId(null); }}
                    className="rounded p-1 text-gray-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                    title="Löschen"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
