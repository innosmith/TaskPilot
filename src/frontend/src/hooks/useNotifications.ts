import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useSSE } from './useSSE';

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  source_type: string | null;
  source_id: string | null;
  is_read: boolean;
  created_at: string;
}

export function useNotifications() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchUnreadCount = useCallback(() => {
    api
      .get<{ count: number }>('/api/notifications/unread-count')
      .then((r) => {
        setUnreadCount(r.count);
        if ('setAppBadge' in navigator) {
          (navigator as any).setAppBadge(r.count || 0).catch(() => {});
        }
      })
      .catch(() => {});
  }, []);

  const fetchItems = useCallback(() => {
    setLoading(true);
    api
      .get<NotificationItem[]>('/api/notifications?limit=30')
      .then((data) => {
        setItems(data);
        const unread = data.filter((n) => !n.is_read).length;
        setUnreadCount(unread);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchUnreadCount();
  }, [fetchUnreadCount]);

  useSSE((event) => {
    if (event === 'notifications_changed') {
      fetchUnreadCount();
      if (items.length > 0) {
        fetchItems();
      }
    }
  });

  const markAsRead = useCallback(
    async (id: string) => {
      await api.patch(`/api/notifications/${id}/read`);
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      setUnreadCount((c) => Math.max(0, c - 1));
    },
    [],
  );

  const markAllAsRead = useCallback(async () => {
    await api.post('/api/notifications/read-all');
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    if ('setAppBadge' in navigator) {
      (navigator as any).clearAppBadge().catch(() => {});
    }
  }, []);

  const dismiss = useCallback(
    async (id: string) => {
      const item = items.find((n) => n.id === id);
      await api.delete(`/api/notifications/${id}`);
      setItems((prev) => prev.filter((n) => n.id !== id));
      if (item && !item.is_read) {
        setUnreadCount((c) => Math.max(0, c - 1));
      }
    },
    [items],
  );

  return {
    items,
    unreadCount,
    loading,
    fetchItems,
    markAsRead,
    markAllAsRead,
    dismiss,
  };
}
