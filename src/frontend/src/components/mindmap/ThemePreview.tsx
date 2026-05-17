import type { MindMapTheme } from './themes';

interface ThemePreviewProps {
  theme: MindMapTheme;
  isActive: boolean;
}

function getNodeRx(shape: MindMapTheme['nodeShape']): number {
  switch (shape) {
    case 'pill': return 8;
    case 'rectangle': return 2;
    default: return 5;
  }
}

export function ThemePreview({ theme, isActive }: ThemePreviewProps) {
  const rx = getNodeRx(theme.nodeShape);
  const rootColor = theme.nodeColors[0];
  const child1 = theme.nodeColors[1];
  const child2 = theme.nodeColors[2];
  const child3 = theme.nodeColors[3] || theme.nodeColors[1];
  const edge1 = theme.edgeColors[1] || theme.edgeColors[0];
  const edge2 = theme.edgeColors[2] || theme.edgeColors[0];
  const edge3 = theme.edgeColors[3] || theme.edgeColors[0];
  const isDashed = theme.borderStyle.includes('dashed');
  const dashArray = theme.edgeDashArray || undefined;

  return (
    <div
      className={`relative cursor-pointer rounded-lg border-2 transition-all hover:scale-[1.03] ${
        isActive
          ? 'border-indigo-500 ring-2 ring-indigo-500/30'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
      }`}
      data-testid={`theme-preview-${theme.id}`}
    >
      <svg
        viewBox="0 0 120 80"
        className="w-full rounded-md"
        style={{ backgroundColor: theme.background }}
      >
        <line x1="42" y1="40" x2="72" y2="18" stroke={edge1} strokeWidth={theme.edgeWidth} strokeOpacity={theme.edgeOpacity} strokeDasharray={dashArray} />
        <line x1="42" y1="40" x2="72" y2="40" stroke={edge2} strokeWidth={theme.edgeWidth} strokeOpacity={theme.edgeOpacity} strokeDasharray={dashArray} />
        <line x1="42" y1="40" x2="72" y2="62" stroke={edge3} strokeWidth={theme.edgeWidth} strokeOpacity={theme.edgeOpacity} strokeDasharray={dashArray} />

        {isDashed ? (
          <>
            <rect x="14" y="30" width="28" height="20" rx={rx} fill="none" stroke={rootColor} strokeWidth="1.5" strokeDasharray="4 2" />
            <rect x="72" y="10" width="34" height="16" rx={rx} fill="none" stroke={child1} strokeWidth="1.5" strokeDasharray="4 2" />
            <rect x="72" y="32" width="34" height="16" rx={rx} fill="none" stroke={child2} strokeWidth="1.5" strokeDasharray="4 2" />
            <rect x="72" y="54" width="34" height="16" rx={rx} fill="none" stroke={child3} strokeWidth="1.5" strokeDasharray="4 2" />
          </>
        ) : (
          <>
            <rect x="14" y="30" width="28" height="20" rx={rx} fill={rootColor} />
            <rect x="72" y="10" width="34" height="16" rx={rx} fill={child1} />
            <rect x="72" y="32" width="34" height="16" rx={rx} fill={child2} />
            <rect x="72" y="54" width="34" height="16" rx={rx} fill={child3} />
          </>
        )}
      </svg>

      <div className="absolute inset-x-0 bottom-0 rounded-b-md bg-gradient-to-t from-black/50 to-transparent px-2 py-1">
        <span className="text-[10px] font-medium text-white">{theme.name}</span>
      </div>
    </div>
  );
}
