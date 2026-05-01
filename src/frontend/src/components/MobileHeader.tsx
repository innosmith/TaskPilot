import { useLocation } from 'react-router-dom';

const PAGE_TITLES: Record<string, string> = {
  '/cockpit': 'Cockpit',
  '/pipeline': 'Agenda',
  '/agenten': 'Agenten',
  '/projects': 'Projekte',
  '/inbox': 'Posteingang',
  '/signale': 'Signale',
  '/settings': 'Einstellungen',
};

interface MobileHeaderProps {
  onMenuOpen: () => void;
  onSearchOpen: () => void;
}

export function MobileHeader({ onMenuOpen, onSearchOpen }: MobileHeaderProps) {
  const { pathname } = useLocation();

  const title =
    PAGE_TITLES[pathname] ??
    (pathname.startsWith('/projects/') ? 'Projekt' : 'TaskPilot');

  return (
    <header className="fixed inset-x-0 top-0 z-30 border-b border-white/20 bg-white/70 backdrop-blur-xl dark:border-gray-800/60 dark:bg-gray-950/70 lg:hidden"
      style={{ paddingTop: 'env(safe-area-inset-top)', paddingLeft: 'env(safe-area-inset-left)', paddingRight: 'env(safe-area-inset-right)' }}
    >
      <div className="flex h-12 items-center px-3">
        <button
          onClick={onMenuOpen}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-gray-600 transition-colors active:bg-gray-200/60 dark:text-gray-300 dark:active:bg-gray-800/60"
          aria-label="Menü öffnen"
        >
          <MenuIcon className="h-5 w-5" />
        </button>

        <h1 className="flex-1 text-center text-[15px] font-semibold text-gray-900 dark:text-white">
          {title}
        </h1>

        <button
          onClick={onSearchOpen}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-gray-600 transition-colors active:bg-gray-200/60 dark:text-gray-300 dark:active:bg-gray-800/60"
          aria-label="Suche öffnen"
        >
          <SearchIcon className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
    </svg>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
    </svg>
  );
}
