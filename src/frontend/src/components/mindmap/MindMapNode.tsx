import { memo, useState, useCallback, useRef, useEffect } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { ChevronRight, ChevronDown, StickyNote, ExternalLink } from 'lucide-react';
import type { MindMapNodeData } from '../../stores/mindmapStore';
import { useMindmapStore } from '../../stores/mindmapStore';
import { getThemeById } from './themes';

function getNodeDepthFromEdges(nodeId: string, edges: { source: string; target: string }[]): number {
  const parentEdge = edges.find(e => e.target === nodeId);
  if (!parentEdge) return 0;
  return 1 + getNodeDepthFromEdges(parentEdge.source, edges);
}

function MindMapNodeComponent({ id, data, selected }: NodeProps) {
  const nodeData = data as MindMapNodeData;
  const [editing, setEditing] = useState(!nodeData.label);
  const [editValue, setEditValue] = useState(nodeData.label || '');
  const inputRef = useRef<HTMLInputElement>(null);
  const updateNodeData = useMindmapStore(s => s.updateNodeData);
  const toggleCollapse = useMindmapStore(s => s.toggleCollapse);
  const edges = useMindmapStore(s => s.edges);
  const themeId = useMindmapStore(s => s.currentThemeId);
  const theme = getThemeById(themeId);

  const hasChildren = edges.some(e => e.source === id);
  const isRoot = id === 'root';
  const depth = getNodeDepthFromEdges(id, edges);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const confirmEdit = useCallback(() => {
    updateNodeData(id, { label: editValue.trim() || 'Neuer Knoten' });
    setEditing(false);
  }, [id, editValue, updateNodeData]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      confirmEdit();
    } else if (e.key === 'Escape') {
      setEditValue(nodeData.label || '');
      setEditing(false);
    }
    e.stopPropagation();
  }, [confirmEdit, nodeData.label]);

  const themeColorIdx = depth % theme.nodeColors.length;
  const bgColor = nodeData.color || theme.nodeColors[themeColorIdx];
  const textColor = nodeData.textColor || theme.textColors[themeColorIdx] || '#FFFFFF';
  const fontSize = nodeData.fontSize || (isRoot ? theme.fontSize.root : depth === 1 ? theme.fontSize.child : theme.fontSize.leaf);
  const fontWeight = nodeData.fontWeight || (isRoot ? '700' : '500');
  const fontFamily = nodeData.fontFamily || theme.fontFamily;
  const borderRadius = theme.borderRadius;

  return (
    <div
      data-testid={`mindmap-node-${id}`}
      className={`group relative shadow-md transition-all duration-200 ${
        selected ? 'ring-2 ring-indigo-400 ring-offset-2 dark:ring-offset-gray-900' : ''
      } ${isRoot ? 'min-w-[180px]' : 'min-w-[120px]'}`}
      style={{ backgroundColor: bgColor, fontFamily, borderRadius }}
    >
      {!isRoot && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-2 !h-2 !bg-gray-400 !border-0"
        />
      )}

      <div className="px-4 py-2.5">
        {editing ? (
          <input
            ref={inputRef}
            value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onBlur={confirmEdit}
            onKeyDown={handleKeyDown}
            className="w-full bg-transparent outline-none text-center"
            style={{ color: textColor, fontSize, fontWeight: fontWeight as any }}
            data-testid="mindmap-node-input"
          />
        ) : (
          <div
            onDoubleClick={() => { setEditValue(nodeData.label || ''); setEditing(true); }}
            className="cursor-text text-center select-none"
            style={{ color: textColor, fontSize, fontWeight: fontWeight as any }}
          >
            {nodeData.label || 'Neuer Knoten'}
          </div>
        )}

        {nodeData.url && (
          <a
            href={nodeData.url.startsWith('http') ? nodeData.url : `https://${nodeData.url}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 flex items-center justify-center gap-1 text-xs opacity-80 hover:opacity-100 transition-opacity"
            style={{ color: textColor }}
            onClick={e => e.stopPropagation()}
          >
            <ExternalLink size={10} />
            <span className="truncate max-w-[150px]">
              {(() => { try { return new URL(nodeData.url.startsWith('http') ? nodeData.url : `https://${nodeData.url}`).hostname; } catch { return nodeData.url; } })()}
            </span>
          </a>
        )}

        <div className="flex items-center justify-center gap-1 mt-1">
          {nodeData.notes && (
            <span title={nodeData.notes} className="opacity-60 hover:opacity-100">
              <StickyNote size={12} style={{ color: textColor }} />
            </span>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-gray-400 !border-0"
      />

      {hasChildren && (
        <button
          onClick={(e) => { e.stopPropagation(); toggleCollapse(id); }}
          className="absolute -right-3 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-white dark:bg-gray-800 shadow border border-gray-200 dark:border-gray-700 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
          data-testid={`mindmap-node-collapse-${id}`}
        >
          {nodeData.isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </button>
      )}
    </div>
  );
}

export const MindMapNode = memo(MindMapNodeComponent);
