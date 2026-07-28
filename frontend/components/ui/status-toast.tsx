"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useEffect } from "react";

type StatusToastProps = {
  error?: string | null;
  message?: string | null;
  busy?: boolean;
  busyLabel?: string;
  onDismissError?: () => void;
  onDismissMessage?: () => void;
  errorDurationMs?: number;
  messageDurationMs?: number;
};

/** Floating notification stack for async action feedback (success/error/in-flight). */
export function StatusToast({
  error,
  message,
  busy,
  busyLabel = "Processando...",
  onDismissError,
  onDismissMessage,
  errorDurationMs = 6000,
  messageDurationMs = 4000
}: StatusToastProps) {
  useEffect(() => {
    if (!error || !onDismissError) return undefined;
    const timer = setTimeout(onDismissError, errorDurationMs);
    return () => clearTimeout(timer);
  }, [error, onDismissError, errorDurationMs]);

  useEffect(() => {
    if (!message || !onDismissMessage) return undefined;
    const timer = setTimeout(onDismissMessage, messageDurationMs);
    return () => clearTimeout(timer);
  }, [message, onDismissMessage, messageDurationMs]);

  const showBusy = Boolean(busy);
  const showMessage = Boolean(message) && !showBusy;
  const showError = Boolean(error);

  if (!showBusy && !showMessage && !showError) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2 sm:right-6 sm:top-6">
      {showBusy ? (
        <div className="pointer-events-auto flex items-center gap-3 rounded-2xl border border-blue-200 bg-white/95 px-4 py-3 text-sm shadow-lg shadow-blue-900/10 backdrop-blur animate-in fade-in slide-in-from-top-2 duration-300">
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-600" />
          </span>
          <span className="font-medium text-slate-600">{busyLabel}</span>
        </div>
      ) : null}

      {showError ? (
        <div className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-red-200 bg-white/95 px-4 py-3 shadow-lg shadow-red-900/10 backdrop-blur animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
            <AlertTriangle className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-red-500">Atenção</div>
            <div className="mt-0.5 text-sm font-medium text-red-700">{error}</div>
          </div>
        </div>
      ) : null}

      {showMessage ? (
        <div className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-emerald-200 bg-white/95 px-4 py-3 shadow-lg shadow-emerald-900/10 backdrop-blur animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-600">Atualização concluída</div>
            <div className="mt-0.5 text-sm font-medium text-emerald-700">{message}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
