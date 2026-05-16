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
  const edgeColor = theme.edgeColors[0] || '#999';

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
        {/* Edge: root -> child1 */}
        <line x1="42" y1="40" x2="72" y2="18" stroke={edgeColor} strokeWidth="1.5" strokeOpacity="0.6" />
        {/* Edge: root -> child2 */}
        <line x1="42" y1="40" x2="72" y2="40" stroke={edgeColor} strokeWidth="1.5" strokeOpacity="0.6" />
        {/* Edge: root -> child3 */}
        <line x1="42" y1="40" x2="72" y2="62" stroke={edgeColor} strokeWidth="1.5" strokeOpacity="0.6" />

        {/* Root node */}
        <rect x="14" y="30" width="28" height="20" rx={rx} fill={rootColor} />
        {/* Child 1 */}
        <rect x="72" y="10" width="34" height="16" rx={rx} fill={child1} />
        {/* Child 2 */}
        <rect x="72" y="32" width="34" height="16" rx={rx} fill={child2} />
        {/* Child 3 */}
        <rect x="72" y="54" width="34" height="16" rx={rx} fill={child3} />
      </svg>

      <div className="absolute inset-x-0 bottom-0 rounded-b-md bg-gradient-to-t from-black/50 to-transparent px-2 py-1">
        <span className="text-[10px] font-medium text-white">{theme.name}</span>
      </div>
    </div>
  );
}
