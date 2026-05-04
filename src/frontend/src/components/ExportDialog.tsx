import { useState, useEffect } from 'react';
import { getToken } from '../api/client';

type ExportFormat = 'markdown' | 'docx' | 'pdf' | 'pptx';

interface ExportDialogProps {
  isOpen: boolean;
  onClose: () => void;
  messageId: string;
  messageContent: string;
}

const FORMAT_OPTIONS: { id: ExportFormat; label: string; ext: string; mime: string }[] = [
  { id: 'markdown', label: 'Markdown (.md)', ext: 'md', mime: 'text/markdown' },
  { id: 'docx', label: 'Word (.docx)', ext: 'docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
  { id: 'pdf', label: 'PDF (.pdf)', ext: 'pdf', mime: 'application/pdf' },
  { id: 'pptx', label: 'PowerPoint (.pptx)', ext: 'pptx', mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' },
];

export function ExportDialog({ isOpen, onClose, messageId, messageContent }: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>('markdown');
  const [titlePage, setTitlePage] = useState(true);
  const [toc, setToc] = useState(true);
  const [template, setTemplate] = useState<string>('');
  const [title, setTitle] = useState('Export');
  const [author, setAuthor] = useState('InnoSmith');
  const [filename, setFilename] = useState('');
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slideCount = format === 'pptx'
    ? (messageContent.split(/\n---\n/).length)
    : null;

  const supportsFilePicker = typeof window !== 'undefined' && 'showSaveFilePicker' in window;

  useEffect(() => {
    if (isOpen) {
      setError(null);
      setExporting(false);
      const dateStr = new Date().toISOString().slice(0, 10);
      setFilename(`export-${dateStr}`);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleExport = async () => {
    setExporting(true);
    setError(null);

    try {
      const token = getToken();
      const resp = await fetch(`/api/chat/messages/${messageId}/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          format,
          title,
          author,
          title_page: titlePage,
          toc,
          template: template || null,
          filename: filename || null,
        }),
      });

      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }

      const blob = await resp.blob();
      const opt = FORMAT_OPTIONS.find(f => f.id === format)!;
      const defaultName = `${filename || 'export'}.${opt.ext}`;

      if (supportsFilePicker) {
        try {
          const handle = await (window as any).showSaveFilePicker({
            suggestedName: defaultName,
            types: [{
              description: opt.label,
              accept: { [opt.mime]: [`.${opt.ext}`] },
            }],
          });
          const writable = await handle.createWritable();
          await writable.write(blob);
          await writable.close();
          onClose();
          return;
        } catch (pickerErr: any) {
          if (pickerErr?.name === 'AbortError') {
            setExporting(false);
            return;
          }
        }
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = defaultName;
      a.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (e) {
      setError((e as Error).message || 'Export fehlgeschlagen');
    } finally {
      setExporting(false);
    }
  };

  const showDocOptions = format === 'docx' || format === 'pdf';
  const showPptxOptions = format === 'pptx';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-xl dark:border-gray-700 dark:bg-gray-800"
        onClick={e => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Herunterladen als...</h3>

        <div className="mb-4 space-y-2">
          {FORMAT_OPTIONS.map(opt => (
            <label
              key={opt.id}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors ${
                format === opt.id
                  ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-900/20'
                  : 'border-gray-200 hover:border-gray-300 dark:border-gray-600 dark:hover:border-gray-500'
              }`}
            >
              <input
                type="radio"
                name="format"
                value={opt.id}
                checked={format === opt.id}
                onChange={() => setFormat(opt.id)}
                className="h-4 w-4 text-indigo-600"
              />
              <FormatIcon format={opt.id} className="h-4 w-4 text-gray-500 dark:text-gray-400" />
              <span className="text-sm text-gray-700 dark:text-gray-300">{opt.label}</span>
            </label>
          ))}
        </div>

        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Dateiname</label>
          <input
            type="text"
            value={filename}
            onChange={e => setFilename(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            placeholder="export"
          />
        </div>

        {showDocOptions && (
          <div className="mb-4 rounded-lg border border-gray-200 p-3 dark:border-gray-600">
            <div className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">Dokument-Optionen</div>
            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={titlePage} onChange={e => setTitlePage(e.target.checked)} className="h-4 w-4 rounded text-indigo-600" />
                <span className="text-sm text-gray-700 dark:text-gray-300">Titelseite</span>
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={toc} onChange={e => setToc(e.target.checked)} className="h-4 w-4 rounded text-indigo-600" />
                <span className="text-sm text-gray-700 dark:text-gray-300">Inhaltsverzeichnis</span>
              </label>
              <div>
                <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Template</label>
                <select
                  value={template}
                  onChange={e => setTemplate(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="">Standard (InnoSmith)</option>
                  <option value="InnoSmith">InnoSmith</option>
                  <option value="Kt. Bern MBA">Kt. Bern MBA</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Titel</label>
                <input type="text" value={title} onChange={e => setTitle(e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Autor</label>
                <input type="text" value={author} onChange={e => setAuthor(e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white" />
              </div>
            </div>
          </div>
        )}

        {showPptxOptions && (
          <div className="mb-4 rounded-lg border border-gray-200 p-3 dark:border-gray-600">
            <div className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">PowerPoint-Optionen</div>
            <div className="space-y-2">
              <div>
                <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Template</label>
                <select value={template} onChange={e => setTemplate(e.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white">
                  <option value="">InnoSmith</option>
                </select>
              </div>
              <div className="flex items-start gap-2 rounded-lg bg-blue-50 px-3 py-2 dark:bg-blue-900/20">
                <InfoIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-500" />
                <span className="text-xs text-blue-700 dark:text-blue-300">
                  Der Inhalt wird als Slide-Script interpretiert (Slides durch --- getrennt).
                  {slideCount !== null && ` ${slideCount} Folie${slideCount !== 1 ? 'n' : ''} erkannt.`}
                </span>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700">
            Abbrechen
          </button>
          <button onClick={handleExport} disabled={exporting} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
            {exporting ? 'Exportiert...' : 'Speichern unter...'}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormatIcon({ format, className }: { format: ExportFormat; className?: string }) {
  switch (format) {
    case 'markdown':
      return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" /></svg>;
    case 'docx':
      return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" /></svg>;
    case 'pdf':
      return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m.75 12 3 3m0 0 3-3m-3 3v-6m-1.5-9H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" /></svg>;
    case 'pptx':
      return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6" /></svg>;
  }
}

function InfoIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
    </svg>
  );
}
