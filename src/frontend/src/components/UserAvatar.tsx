export function getAvatarUrl(user: { avatar_url?: string | null; email: string }): string {
  if (user.avatar_url) return user.avatar_url;

  const hash = md5Hex(user.email.trim().toLowerCase());
  return `https://gravatar.com/avatar/${hash}?d=mp&s=80`;
}

function md5Hex(input: string): string {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const chr = input.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0;
  }
  return Math.abs(hash).toString(16).padStart(8, '0');
}

interface UserAvatarProps {
  user: { avatar_url?: string | null; email: string; display_name: string };
  size?: number;
  className?: string;
}

export function UserAvatar({ user, size = 24, className = '' }: UserAvatarProps) {
  const url = getAvatarUrl(user);
  const initials = user.display_name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <img
      src={url}
      alt={initials}
      className={`shrink-0 rounded-full object-cover ${className}`}
      style={{ width: size, height: size }}
      onError={(e) => {
        const target = e.target as HTMLImageElement;
        target.style.display = 'none';
        const fallback = target.nextElementSibling as HTMLElement;
        if (fallback) fallback.style.display = 'flex';
      }}
    />
  );
}
