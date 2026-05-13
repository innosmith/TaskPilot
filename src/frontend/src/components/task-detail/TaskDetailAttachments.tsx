import { useRef, useState } from 'react';
import { api } from '../../api/client';
import type { AttachmentEntry } from './shared';
import { SectionLabel, PaperclipIcon, TrashIcon, formatFileSize } from './shared';
import { OneDrivePicker, type ContextSource } from '../OneDrivePicker';

interface TaskDetailAttachmentsProps {
  taskId: string;
  attachments: AttachmentEntry[];
  onAttachmentsChanged: (attachments: AttachmentEntry[]) => void;
  isOwner: boolean;
}

function CloudIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z" />
    </svg>
  );
}

function UploadIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
    </svg>
  );
}

function isOneDriveRef(filepath: string): boolean {
  return filepath.startsWith('onedrive://');
}

export default function TaskDetailAttachments({ taskId, attachments, onAttachmentsChanged, isOwner }: TaskDetailAttachmentsProps) {
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [showOneDrivePicker, setShowOneDrivePicker] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleDownload(att: AttachmentEntry) {
    if (isOneDriveRef(att.filepath)) {
      const itemId = att.filepath.replace('onedrive://', '');
      try {
        const meta = await api.get<{ web_url: string }>(`/api/onedrive/metadata?item_id=${encodeURIComponent(itemId)}`);
        window.open(meta.web_url, '_blank');
      } catch {
        window.open('https://onedrive.live.com', '_blank');
      }
      return;
    }
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

  async function handleOneDriveSelect(sources: ContextSource[]) {
    setUploading(true);
    try {
      for (const src of sources) {
        if (src.type === 'onedrive_file' && src.item_id) {
          await api.post(`/api/tasks/${taskId}/attachments/onedrive`, {
            item_id: src.item_id,
            name: src.name,
          });
        }
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
      <SectionLabel icon={PaperclipIcon} text="Anhänge" />

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); uploadFiles(e.dataTransfer.files); }}
        className={`rounded-lg border border-dashed px-3 py-3 text-center transition-colors ${
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
        {uploading ? (
          <div className="flex items-center justify-center gap-2 py-1">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
            <span className="text-[11px] text-gray-400">Hochladen…</span>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex flex-col items-center gap-1 rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-indigo-600 dark:hover:bg-gray-800 dark:hover:text-indigo-400"
                title="Lokale Datei hochladen"
              >
                <UploadIcon className="h-5 w-5" />
                <span className="text-[9px] font-medium">Datei</span>
              </button>
              {isOwner && (
                <button
                  type="button"
                  onClick={() => setShowOneDrivePicker(true)}
                  className="flex flex-col items-center gap-1 rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-blue-600 dark:hover:bg-gray-800 dark:hover:text-blue-400"
                  title="OneDrive-Datei verknüpfen"
                >
                  <CloudIcon className="h-5 w-5" />
                  <span className="text-[9px] font-medium">OneDrive</span>
                </button>
              )}
            </div>
            <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">
              {dragOver ? 'Loslassen zum Hochladen' : 'oder Datei hierher ziehen'}
            </p>
          </>
        )}
      </div>

      {attachments.length > 0 && (
        <ul className="mt-2.5 space-y-1">
          {attachments.map((att) => {
            const isCloud = isOneDriveRef(att.filepath);
            return (
              <li key={att.id} className="group flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800">
                {isCloud
                  ? <CloudIcon className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                  : <PaperclipIcon className="h-3.5 w-3.5 shrink-0 text-gray-400 dark:text-gray-500" />
                }
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
            );
          })}
        </ul>
      )}

      {showOneDrivePicker && (
        <OneDrivePicker
          isOpen={showOneDrivePicker}
          onClose={() => setShowOneDrivePicker(false)}
          onSelect={handleOneDriveSelect}
        />
      )}
    </div>
  );
}
