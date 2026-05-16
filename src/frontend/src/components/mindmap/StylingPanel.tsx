import { useState } from 'react';
import { X, Paintbrush, Image } from 'lucide-react';
import { THEMES } from './themes';
import { ThemePreview } from './ThemePreview';
import { BackgroundPicker } from '../../components/BackgroundPicker';

const PRESET_COLORS = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
  '#14B8A6', '#E11D48', '#0EA5E9', '#D946EF', '#78716C',
];

interface Props {
  open: boolean;
  onClose: () => void;
  currentThemeId: string;
  onThemeChange: (themeId: string) => void;
  backgroundUrl: string | null;
  onBackgroundChange: (url: string | null, type: string | null) => void;
  selectedNodeColor: string | null;
  onNodeColorChange: (color: string) => void;
}

export function StylingPanel({
  open,
  onClose,
  currentThemeId,
  onThemeChange,
  backgroundUrl,
  onBackgroundChange,
  selectedNodeColor,
  onNodeColorChange,
}: Props) {
  const [bgPickerOpen, setBgPickerOpen] = useState(false);

  if (!open) return null;

  return (
    <>
      <div
        className="w-72 border-l border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 overflow-y-auto"
        data-testid="styling-panel"
      >
        <div className="flex items-center justify-between p-3 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <Paintbrush size={16} className="text-indigo-600" />
            <span className="text-sm font-semibold dark:text-white">Design</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
            data-testid="styling-panel-close"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-3 space-y-5">
          {/* Section 1: Designs */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
              Designs
            </h3>
            <div className="grid grid-cols-2 gap-2" data-testid="theme-grid">
              {THEMES.map(theme => (
                <button
                  key={theme.id}
                  onClick={() => onThemeChange(theme.id)}
                  className="text-left"
                  data-testid={`theme-select-${theme.id}`}
                >
                  <ThemePreview theme={theme} isActive={currentThemeId === theme.id} />
                </button>
              ))}
            </div>
          </div>

          {/* Section 2: Hintergrund */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
              Hintergrund
            </h3>
            <button
              onClick={() => setBgPickerOpen(true)}
              className="flex w-full items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
              data-testid="bg-picker-trigger"
            >
              <Image size={14} className="text-gray-400" />
              Hintergrund ändern
            </button>
          </div>

          {/* Section 3: Knoten-Farbe (nur bei Selektion) */}
          {selectedNodeColor !== null && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                Knoten-Farbe
              </h3>
              <div className="grid grid-cols-5 gap-1.5" data-testid="node-color-grid">
                {PRESET_COLORS.map(c => (
                  <button
                    key={c}
                    onClick={() => onNodeColorChange(c)}
                    className={`w-8 h-8 rounded-lg border-2 transition-transform hover:scale-110 ${
                      selectedNodeColor === c
                        ? 'border-white ring-2 ring-indigo-500 scale-110'
                        : 'border-transparent'
                    }`}
                    style={{ backgroundColor: c }}
                    data-testid={`node-color-${c.replace('#', '')}`}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={backgroundUrl}
        onSelect={(url, type) => {
          onBackgroundChange(url, type);
          setBgPickerOpen(false);
        }}
      />
    </>
  );
}
