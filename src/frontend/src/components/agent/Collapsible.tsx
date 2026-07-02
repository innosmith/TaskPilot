import { useState } from 'react';
import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

export function Collapsible({
  title, subtitle, badge, defaultOpen = false, children,
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800/50">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
      >
        <div className="flex min-w-0 items-center gap-2">
          <ChevronRight className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${open ? 'rotate-90' : ''}`} />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-gray-900 dark:text-white">{title}</div>
            {subtitle && <div className="truncate text-xs text-gray-500 dark:text-gray-400">{subtitle}</div>}
          </div>
        </div>
        {badge && <div className="shrink-0">{badge}</div>}
      </button>
      {open && <div className="border-t border-gray-100 px-4 py-3 dark:border-gray-700/60">{children}</div>}
    </div>
  );
}
