import { useState, useRef, useEffect } from 'react';

export const PRESET_COLORS = [
  '#3B82F6',
  '#EF4444',
  '#10B981',
  '#F59E0B',
  '#8B5CF6',
  '#EC4899',
  '#6366F1',
  '#14B8A6',
  '#F97316',
  '#06B6D4',
  '#84CC16',
  '#A855F7',
];

interface ColorPickerProps {
  value: string;
  onChange: (color: string) => void;
  presets?: string[];
}

export function ColorPicker({ value, onChange, presets = PRESET_COLORS }: ColorPickerProps) {
  const [showNative, setShowNative] = useState(false);
  const nativeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (showNative && nativeRef.current) {
      nativeRef.current.click();
    }
  }, [showNative]);

  const isCustom = !presets.includes(value);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {presets.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          className={`h-7 w-7 rounded-full transition-transform hover:scale-110 ${
            value === c ? 'ring-2 ring-indigo-500 ring-offset-2 dark:ring-offset-gray-900' : ''
          }`}
          style={{ backgroundColor: c }}
          title={c}
        />
      ))}
      <div className="relative">
        <button
          type="button"
          onClick={() => {
            setShowNative(true);
            setTimeout(() => nativeRef.current?.click(), 50);
          }}
          className={`flex h-7 w-7 items-center justify-center rounded-full border-2 border-dashed transition-transform hover:scale-110 ${
            isCustom
              ? 'ring-2 ring-indigo-500 ring-offset-2 dark:ring-offset-gray-900'
              : 'border-gray-300 dark:border-gray-600'
          }`}
          style={isCustom ? { backgroundColor: value } : undefined}
          title="Eigene Farbe wählen"
        >
          {!isCustom && (
            <PipetteIcon className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
          )}
        </button>
        <input
          ref={nativeRef}
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => setShowNative(false)}
          className="absolute inset-0 h-7 w-7 cursor-pointer opacity-0"
          tabIndex={-1}
        />
      </div>
    </div>
  );
}

function PipetteIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}
