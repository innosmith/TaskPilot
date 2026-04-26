import { LucideIconByName } from './LucideIconPicker';

interface ProjectIconProps {
  iconUrl?: string | null;
  iconEmoji?: string | null;
  color: string;
  size?: number;
  className?: string;
}

function isLucideIconName(value: string): boolean {
  return /^[A-Za-z][A-Za-z0-9]*$/.test(value);
}

export function ProjectIcon({
  iconUrl,
  iconEmoji,
  color,
  size = 20,
  className = '',
}: ProjectIconProps) {
  if (iconUrl) {
    return (
      <img
        src={iconUrl}
        alt=""
        className={`shrink-0 rounded-md object-cover ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  if (iconEmoji) {
    if (isLucideIconName(iconEmoji)) {
      return (
        <span
          className={`flex shrink-0 items-center justify-center ${className}`}
          style={{ width: size, height: size }}
        >
          <LucideIconByName
            name={iconEmoji}
            className="text-gray-600 dark:text-gray-400"
            strokeWidth={1.5}
          />
        </span>
      );
    }
    return (
      <span
        className={`flex shrink-0 items-center justify-center ${className}`}
        style={{ width: size, height: size, fontSize: size * 0.7 }}
      >
        {iconEmoji}
      </span>
    );
  }

  return (
    <span
      className={`shrink-0 rounded-full ${className}`}
      style={{ width: size, height: size, backgroundColor: color }}
    />
  );
}
