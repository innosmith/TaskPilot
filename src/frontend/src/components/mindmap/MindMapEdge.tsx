import { memo } from 'react';
import {
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react';
import { useMindmapStore } from '../../stores/mindmapStore';
import { getThemeById } from './themes';

function getTargetDepth(targetId: string, edges: { source: string; target: string }[]): number {
  const parentEdge = edges.find(e => e.target === targetId);
  if (!parentEdge) return 0;
  return 1 + getTargetDepth(parentEdge.source, edges);
}

function MindMapEdgeComponent({
  id, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
}: EdgeProps) {
  const themeId = useMindmapStore(s => s.currentThemeId);
  const theme = getThemeById(themeId);
  const edges = useMindmapStore(s => s.edges);

  const depth = getTargetDepth(target, edges);
  const colorIdx = depth % theme.edgeColors.length;
  const edgeColor = theme.edgeColors[colorIdx] || '#94A3B8';

  let edgePath: string;
  switch (theme.edgeType) {
    case 'step':
      [edgePath] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 8 });
      break;
    case 'straight':
      [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
      break;
    default:
      [edgePath] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  }

  return (
    <path
      id={id}
      d={edgePath}
      fill="none"
      className="react-flow__edge-path"
      style={{
        stroke: edgeColor,
        strokeWidth: theme.edgeWidth,
        opacity: theme.edgeOpacity,
        strokeLinecap: 'round',
        strokeDasharray: theme.edgeDashArray || undefined,
      }}
    />
  );
}

export const MindMapEdge = memo(MindMapEdgeComponent);
