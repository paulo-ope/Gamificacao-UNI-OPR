"use client";

import { Bell, Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Notification } from "@/lib/types";

const POLL_INTERVAL_MS = 60_000;

function timeAgo(value: string) {
  const diffMs = Date.now() - new Date(value).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes} min atrás`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h atrás`;
  const days = Math.floor(hours / 24);
  return `${days}d atrás`;
}

export function NotificationBell() {
  const pathname = usePathname();
  const router = useRouter();
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const refreshCount = useCallback(() => {
    void api.notificationsUnreadCount().then((result) => setUnreadCount(result.unread_count)).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshCount();
    window.addEventListener("notifications:refresh", refreshCount);
    const interval = setInterval(refreshCount, POLL_INTERVAL_MS);
    return () => {
      window.removeEventListener("notifications:refresh", refreshCount);
      clearInterval(interval);
    };
  }, [refreshCount]);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  async function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      try {
        setItems(await api.notifications(30));
      } catch {
        setItems([]);
      } finally {
        setLoading(false);
      }
    }
  }

  async function handleClickNotification(notification: Notification) {
    if (!notification.is_read) {
      setItems((current) => current.map((item) => (item.id === notification.id ? { ...item, is_read: true } : item)));
      setUnreadCount((count) => Math.max(0, count - 1));
      void api.markNotificationRead(notification.id).catch(() => undefined);
    }
    if (notification.link_url) {
      const targetPath = notification.link_url.split("?")[0];
      if (targetPath !== pathname) {
        router.push(notification.link_url);
      }
      setOpen(false);
    }
  }

  async function handleMarkAllRead() {
    setItems((current) => current.map((item) => ({ ...item, is_read: true })));
    setUnreadCount(0);
    await api.markAllNotificationsRead().catch(() => undefined);
  }

  return (
    <div className="relative" ref={containerRef}>
      <Button type="button" variant="ghost" size="sm" className="relative h-9 w-9 p-0" onClick={() => void toggleOpen()} aria-label="Notificações">
        <Bell className="h-4.5 w-4.5" />
        {unreadCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        ) : null}
      </Button>
      {open ? (
        <div className="absolute right-0 top-11 z-50 w-80 rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <p className="text-sm font-semibold text-slate-900">Notificações</p>
            {unreadCount > 0 ? (
              <button type="button" className="text-xs font-medium text-blue-600 hover:text-blue-800" onClick={() => void handleMarkAllRead()}>
                Marcar todas como lidas
              </button>
            ) : null}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
              </div>
            ) : items.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-400">Nenhuma notificação ainda.</p>
            ) : (
              items.map((notification) => (
                <button
                  key={notification.id}
                  type="button"
                  onClick={() => void handleClickNotification(notification)}
                  className="block w-full border-b border-slate-50 px-4 py-3 text-left last:border-b-0 hover:bg-slate-50"
                >
                  <div className="flex items-start gap-2">
                    {!notification.is_read ? <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-600" /> : <span className="mt-1.5 h-2 w-2 shrink-0" />}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900">{notification.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{notification.message}</p>
                      <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-400">{timeAgo(notification.created_at)}</p>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
