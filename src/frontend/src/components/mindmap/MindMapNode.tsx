import { memo, useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { ChevronRight, ChevronDown, StickyNote, ExternalLink } from 'lucide-react';
import type { MindMapNodeData } from '../../stores/mindmapStore';
import { useMindmapStore } from '../../stores/mindmapStore';
import { getThemeById } from './themes';

const URL_REGEX = /(https?:\/\/[^\s]+|www\.[^\s]+)/gi;

function renderLabelWithLinks(text: string, textColor: string): ReactNode {
  const parts = text.split(URL_REGEX);
  if (parts.length === 1) return text;

  return parts.map((part, i) => {
    if (URL_REGEX.test(part)) {
      URL_REGEX.lastIndex = 0;
      const href = part.startsWith('http') ? part : `https://${part}`;
      let hostname: string;
      try { hostname = new URL(href).hostname; } catch { hostname = part; }
      return (
        <a
          key={i}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-0.5 underline decoration-1 underline-offset-2 opacity-85 hover:opacity-100"
          style={{ color: textColor }}
          onClick={e => e.stopPropagation()}
        >
          <ExternalLink size={10} className="inline shrink-0" />
          {hostname}
        </a>
      );
    }
    URL_REGEX.lastIndex = 0;
    return part || null;
  });
}

function getNodeDepthFromEdges(nodeId: string, edges: { source: string; target: string }[]): number {
  const parentEdge = edges.find(e => e.target === nodeId);
  if (!parentEdge) return 0;
  return 1 + getNodeDepthFromEdges(parentEdge.source, edges);
}

function MindMapNodeComponent({ id, data }: NodeProps) {
  const nodeData = data as MindMapNodeData;
  const [editing, setEditing] = useState(!nodeData.label);
  const [editValue, setEditValue] = useState(nodeData.label || '');
  const inputRef = useRef<HTMLInputElement>(null);
  const updateNodeData = useMindmapStore(s => s.updateNodeData);
  const toggleCollapse = useMindmapStore(s => s.toggleCollapse);
  const edges = useMindmapStore(s => s.edges);
  const selectedNodeIds = useMindmapStore(s => s.selectedNodeIds);
  const themeId = useMindmapStore(s => s.currentThemeId);
  const theme = getThemeById(themeId);
  const isSelected = selectedNodeIds.includes(id);

  const hasChildren = edges.some(e => e.source === id);
  const isRoot = id === 'root';
  const depth = getNodeDepthFromEdges(id, edges);
  const side = (nodeData.side === 'left') ? 'left' : 'right';

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
  const nodeColor = (nodeData.color && typeof nodeData.color === 'string' && nodeData.color.startsWith('#'))
    ? nodeData.color
    : theme.nodeColors[themeColorIdx];
  const textColor = (nodeData.textColor && typeof nodeData.textColor === 'string' && nodeData.textColor.startsWith('#'))
    ? nodeData.textColor
    : (theme.textColors[themeColorIdx] || '#FFFFFF');
  const fontSize = nodeData.fontSize || (isRoot ? theme.fontSize.root : depth === 1 ? theme.fontSize.child : theme.fontSize.leaf);
  const fontWeight = nodeData.fontWeight || (isRoot ? '700' : '500');
  const fontFamily = nodeData.fontFamily || theme.fontFamily;
  const borderRadius = theme.borderRadius;

  const isDashed = theme.borderStyle.includes('dashed');

  const containerStyle: React.CSSProperties = {
    fontFamily,
    borderRadius,
    boxShadow: theme.shadowStyle !== 'none' ? theme.shadowStyle : undefined,
    backgroundColor: isDashed ? 'transparent' : nodeColor,
    border: isDashed ? theme.borderStyle : (theme.borderStyle !== 'none' ? theme.borderStyle : undefined),
    borderColor: isDashed ? nodeColor : undefined,
    outline: isSelected ? '3px solid #818CF8' : undefined,
    outlineOffset: isSelected ? '2px' : undefined,
  };

  return (
    <div
      data-testid={`mindmap-node-${id}`}
      className={`group relative transition-all duration-200 ${isRoot ? 'min-w-[180px]' : 'min-w-[120px]'}`}
      style={containerStyle}
    >
      {!isRoot && (
        <Handle
          type="target"
          position={side === 'left' ? Position.Right : Position.Left}
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
            {renderLabelWithLinks(nodeData.label || 'Neuer Knoten', textColor)}
          </div>
        )}

        <div className="flex items-center justify-center gap-1 mt-1">
          {nodeData.notes && (
            <span title={nodeData.notes} className="opacity-60 hover:opacity-100">
              <StickyNote size={12} style={{ color: textColor }} />
            </span>
          )}
        </div>
      </div>

      {isRoot ? (
        <>
          <Handle type="source" position={Position.Right} id="right" className="!w-2 !h-2 !bg-gray-400 !border-0" />
          <Handle type="source" position={Position.Left} id="left" className="!w-2 !h-2 !bg-gray-400 !border-0" />
        </>
      ) : (
        <Handle
          type="source"
          position={side === 'left' ? Position.Left : Position.Right}
          className="!w-2 !h-2 !bg-gray-400 !border-0"
        />
      )}

      {hasChildren && (
        <button
          onClick={(e) => { e.stopPropagation(); toggleCollapse(id); }}
          className={`absolute ${side === 'left' && !isRoot ? '-left-3' : '-right-3'} top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-white dark:bg-gray-800 shadow border border-gray-200 dark:border-gray-700 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity`}
          data-testid={`mindmap-node-collapse-${id}`}
        >
          {nodeData.isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </button>
      )}
    </div>
  );
}

export const MindMapNode = memo(MindMapNodeComponent);
