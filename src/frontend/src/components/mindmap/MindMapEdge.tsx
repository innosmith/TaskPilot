import { memo } from 'react';
import {
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react';
import { useMindmapStore } from '../../stores/mindmapStore';
import { getThemeById } from './themes';

function MindMapEdgeComponent({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style,
}: EdgeProps) {
  const themeId = useMindmapStore(s => s.currentThemeId);
  const theme = getThemeById(themeId);

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
      strokeWidth={style?.strokeWidth || 2}
      stroke={String(style?.stroke || theme.edgeColors[0] || '#94A3B8')}
      strokeLinecap="round"
      className="react-flow__edge-path"
    />
  );
}

export const MindMapEdge = memo(MindMapEdgeComponent);
