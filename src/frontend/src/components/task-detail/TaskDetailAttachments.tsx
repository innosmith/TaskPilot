import { useRef, useState } from 'react';
import { api } from '../../api/client';
import type { AttachmentEntry } from './shared';
import { SectionLabel, PaperclipIcon, TrashIcon, formatFileSize } from './shared';

interface TaskDetailAttachmentsProps {
  taskId: string;
  attachments: AttachmentEntry[];
  onAttachmentsChanged: (attachments: AttachmentEntry[]) => void;
}

export default function TaskDetailAttachments({ taskId, attachments, onAttachmentsChanged }: TaskDetailAttachmentsProps) {
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleDownload(att: AttachmentEntry) {
    const token = localStorage.getItem('taskpilot_token');
    const res = await fetch(`/api${att.filepath}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function uploadFiles(files: FileList | File[]) {
    if (!files.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        await api.upload(`/api/tasks/${taskId}/attachments`, form);
      }
      const updated = await api.get<AttachmentEntry[]>(`/api/tasks/${taskId}/attachments`);
      onAttachmentsChanged(updated);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(attId: string) {
    await api.delete(`/api/tasks/${taskId}/attachments/${attId}`);
    onAttachmentsChanged(attachments.filter((a) => a.id !== attId));
  }

  return (
    <div>
      <SectionLabel
        icon={PaperclipIcon}
        text="Anhänge"
        action={
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          >
            {uploading ? 'Hochladen…' : '+ Datei'}
          </button>
        }
      />

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); uploadFiles(e.dataTransfer.files); }}
        className={`rounded-lg border border-dashed px-3 py-2.5 text-center transition-colors ${
          dragOver
            ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/40'
            : 'border-gray-200 dark:border-gray-700'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => { if (e.target.files) uploadFiles(e.target.files); e.target.value = ''; }}
        />
        <p className="text-[11px] text-gray-400 dark:text-gray-500">
          {dragOver ? 'Loslassen zum Hochladen' : 'Datei hierher ziehen'}
        </p>
      </div>

      {attachments.length > 0 && (
        <ul className="mt-2.5 space-y-1">
          {attachments.map((att) => (
            <li key={att.id} className="group flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800">
              <PaperclipIcon className="h-3.5 w-3.5 shrink-0 text-gray-400 dark:text-gray-500" />
              <button
                onClick={() => handleDownload(att)}
                className="min-w-0 flex-1 truncate text-left text-xs text-indigo-600 hover:underline dark:text-indigo-400"
              >
                {att.filename}
              </button>
              <span className="shrink-0 text-[10px] text-gray-400 dark:text-gray-500">{formatFileSize(att.size)}</span>
              <button
                onClick={() => handleDelete(att.id)}
                className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                title="Löschen"
              >
                <TrashIcon className="h-3.5 w-3.5 text-red-400 hover:text-red-500" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
