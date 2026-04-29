import { useState, useEffect } from 'react';
import { api } from '../api/client';

interface PersonLookup {
  id: number;
  name: string;
  email: string | null;
  org_name: string | null;
  org_id: number | null;
  phone: string | null;
  pic_url: string | null;
  open_deals_count: number;
  open_deals: { id: number; title: string; value: number | null; currency: string | null }[];
}

interface CrmBadgeProps {
  emailAddress: string | null | undefined;
  senderName?: string | null;
  compact?: boolean;
  glassBg?: boolean;
  onCreateContact?: (name: string, email: string) => void;
}

export function CrmBadge({ emailAddress, senderName, compact, glassBg, onCreateContact }: CrmBadgeProps) {
  const [person, setPerson] = useState<PersonLookup | null>(null);
  const [loading, setLoading] = useState(false);
  const [lookupDone, setLookupDone] = useState(false);
  const [lookupFailed, setLookupFailed] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!emailAddress || lookupDone) return;
    setLoading(true);
    setLookupDone(true);

    api.get<PersonLookup | null>(`/api/pipedrive/lookup-email?email=${encodeURIComponent(emailAddress)}`)
      .then(data => {
        if (data && data.id) setPerson(data);
        setLookupFailed(false);
      })
      .catch(() => {
        setLookupFailed(true);
      })
      .finally(() => setLoading(false));
  }, [emailAddress, lookupDone]);

  const handleCreateContact = async () => {
    if (!emailAddress) return;
    setCreating(true);
    try {
      const name = senderName || emailAddress.split('@')[0];
      await api.post('/api/pipedrive/quick-contact', { name, email: emailAddress });
      onCreateContact?.(name, emailAddress);
      setLookupDone(false);
      setPerson(null);
    } catch {}
    finally { setCreating(false); setShowCreate(false); }
  };

  if (loading) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 dark:text-gray-500">
        <span className="h-3 w-3 animate-spin rounded-full border border-gray-300 border-t-transparent" />
        CRM…
      </span>
    );
  }

  if (person) {
    const pipedriveUrl = `https://innosmith.pipedrive.com/person/${person.id}`;
    if (compact) {
      return (
        <a
          href={pipedriveUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-full bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700 transition-colors hover:bg-green-100 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50"
        >
          {person.pic_url ? (
            <img src={person.pic_url} alt="" className="h-4 w-4 rounded-full object-cover" />
          ) : (
            <PersonIcon className="h-3.5 w-3.5" />
          )}
          {person.name}
          {person.open_deals_count > 0 && (
            <span className="text-green-500"> · {person.open_deals_count} Deal{person.open_deals_count !== 1 ? 's' : ''}</span>
          )}
        </a>
      );
    }

    return (
      <div className={`rounded-lg border p-2.5 ${
        glassBg
          ? 'border-green-400/30 bg-green-500/10'
          : 'border-green-200 bg-green-50/60 dark:border-green-900 dark:bg-green-950/30'
      }`}>
        <div className="flex items-center gap-2.5">
          {person.pic_url ? (
            <img src={person.pic_url} alt="" className="h-8 w-8 rounded-full object-cover" />
          ) : (
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">
              <PersonIcon className="h-4 w-4" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <a
              href={pipedriveUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-green-700 hover:underline dark:text-green-300"
            >
              {person.name}
            </a>
            <div className="text-[11px] text-gray-500 dark:text-gray-400">
              {person.org_name && <span>{person.org_name}</span>}
              {person.open_deals_count > 0 && (
                <span>{person.org_name ? ' · ' : ''}{person.open_deals_count} offene{person.open_deals_count === 1 ? 'r' : ''} Deal{person.open_deals_count !== 1 ? 's' : ''}</span>
              )}
            </div>
          </div>
          <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-400">
            Pipedrive
          </span>
        </div>
        {person.open_deals.length > 0 && (
          <div className="mt-2 space-y-0.5">
            {person.open_deals.map(deal => (
              <a
                key={deal.id}
                href={`https://innosmith.pipedrive.com/deal/${deal.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] text-gray-600 hover:bg-green-100/50 dark:text-gray-400 dark:hover:bg-green-900/20"
              >
                <span className="h-1 w-1 rounded-full bg-green-400" />
                <span className="truncate">{deal.title}</span>
                {deal.value != null && deal.value > 0 && (
                  <span className="ml-auto shrink-0 font-medium text-green-600 dark:text-green-400">
                    {deal.currency || 'CHF'} {deal.value.toLocaleString('de-CH')}
                  </span>
                )}
              </a>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (!emailAddress || lookupFailed || !onCreateContact) return null;
  if (!lookupDone) return null;

  if (showCreate) {
    return (
      <div className="flex items-center gap-2">
        <button
          onClick={handleCreateContact}
          disabled={creating}
          className="rounded-lg bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          {creating ? 'Wird erstellt…' : `${senderName || emailAddress} in Pipedrive erfassen`}
        </button>
        <button
          onClick={() => setShowCreate(false)}
          className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          Abbrechen
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setShowCreate(true)}
      className="inline-flex items-center gap-1 rounded-full border border-dashed border-gray-300 px-2 py-0.5 text-[11px] text-gray-400 transition-colors hover:border-green-400 hover:text-green-600 dark:border-gray-600 dark:hover:border-green-600 dark:hover:text-green-400"
      title={`${senderName || emailAddress} ist noch nicht in Pipedrive erfasst`}
    >
      <PlusIcon className="h-3 w-3" />
      Kontakt erfassen
    </button>
  );
}

function PersonIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
    </svg>
  );
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}
