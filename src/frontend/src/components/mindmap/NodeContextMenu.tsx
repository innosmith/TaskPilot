import { useEffect, useRef } from 'react';
import { Plus, Trash2, Palette, StickyNote, Link, ChevronRight } from 'lucide-react';
import { useMindmapStore } from '../../stores/mindmapStore';

interface Props {
  nodeId: string;
  x: number;
  y: number;
  onClose: () => void;
  onColorChange: (nodeId: string) => void;
  onAddNote: (nodeId: string) => void;
  onAddUrl: (nodeId: string) => void;
}

export function NodeContextMenu({ nodeId, x, y, onClose, onColorChange, onAddNote, onAddUrl }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { addChildNode, addSiblingNode, deleteNode } = useMindmapStore();

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const items: (null | { icon: typeof Plus; label: string; action: () => void; danger?: boolean; shortcut?: string })[] = [
    { icon: Plus, label: 'Kind hinzufügen', action: () => { addChildNode(nodeId); onClose(); }, shortcut: 'Tab' },
    { icon: ChevronRight, label: 'Geschwister hinzufügen', action: () => { addSiblingNode(nodeId); onClose(); }, shortcut: 'Enter' },
    null,
    { icon: Palette, label: 'Farbe ändern', action: () => { onColorChange(nodeId); onClose(); } },
    { icon: StickyNote, label: 'Notiz hinzufügen', action: () => { onAddNote(nodeId); onClose(); } },
    { icon: Link, label: 'URL hinzufügen', action: () => { onAddUrl(nodeId); onClose(); } },
    null,
    { icon: Trash2, label: 'Löschen', action: () => { deleteNode(nodeId); onClose(); }, danger: true, shortcut: 'Del' },
  ];

  return (
    <div
      ref={ref}
      className="fixed z-50 w-52 bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 py-1"
      style={{ left: x, top: y }}
      data-testid="node-context-menu"
    >
      {items.map((item, i) =>
        item === null ? (
          <div key={i} className="my-1 border-t border-gray-100 dark:border-gray-800" />
        ) : (
          <button
            key={i}
            onClick={item.action}
            className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm transition-colors ${
              item.danger
                ? 'text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20'
                : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
            }`}
          >
            <item.icon size={14} />
            <span className="flex-1 text-left">{item.label}</span>
            {item.shortcut && (
              <span className="text-xs text-gray-400">{item.shortcut}</span>
            )}
          </button>
        )
      )}
    </div>
  );
}
