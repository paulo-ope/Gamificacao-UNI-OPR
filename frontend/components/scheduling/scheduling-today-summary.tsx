"use client";

import { CalendarClock, Inbox, RefreshCcw, Users } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

import type { SchedulingDailyPoint } from "@/lib/scheduling-api";

import { number } from "./scheduling-format";

// KPIs do dia, alinhados ao vocabulário do setor de field service (reschedule rate, SLA
// compliance) pesquisado a pedido do usuário 2026-08-31 - taxa em %, não só contagem bruta, e o
// SLA do dia junto do reagendamento (as duas métricas que decidem "o dia foi bom ou não").
function TodayTile({
  title,
  value,
  helper,
  tone,
  icon: Icon,
  onClick,
  children,
}: {
  title: string;
  value: string | number;
  helper: string;
  tone: "amber" | "red" | "slate" | "blue";
  icon: ComponentType<{ className?: string }>;
  onClick?: () => void;
  children?: ReactNode;
}) {
  const { gradient, badge } = {
    amber: { gradient: "from-amber-500 to-orange-500", badge: "bg-amber-50 text-amber-700" },
    red: { gradient: "from-red-600 to-rose-500", badge: "bg-red-50 text-red-700" },
    slate: { gradient: "from-slate-400 to-slate-300", badge: "bg-slate-100 text-slate-600" },
    blue: { gradient: "from-blue-600 to-cyan-500", badge: "bg-blue-50 text-blue-700" },
  }[tone];

  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={`relative overflow-hidden rounded-2xl border border-slate-100 bg-white p-4 text-left shadow-sm ${onClick ? "cursor-pointer transition hover:-translate-y-0.5 hover:shadow-md hover:border-slate-200" : ""}`}
    >
      <span className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${gradient}`} />
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-slate-500">{title}</p>
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${badge}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-2 text-3xl font-bold tabular-nums text-slate-950">{value}</p>
      <p className="mt-1.5 text-xs text-slate-500">{helper}</p>
      {children}
    </div>
  );
}

export function SchedulingTodaySummary({
  todayPoint,
  todaySlaRate,
  todaySlaTarget,
  pendingOrders,
  loading,
  onOpenToday,
  onOpenPending,
}: {
  todayPoint: SchedulingDailyPoint | null;
  todaySlaRate: number | null;
  todaySlaTarget: number | null;
  pendingOrders: number | null;
  loading: boolean;
  onOpenToday: () => void;
  onOpenPending: () => void;
}) {
  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-32 animate-pulse rounded-2xl bg-slate-100" />
        ))}
      </div>
    );
  }

  const reschedules = todayPoint?.reschedule_events ?? 0;
  const firstSchedules = todayPoint?.first_schedule_events ?? 0;
  const totalActions = reschedules + firstSchedules;
  const rescheduleRate = totalActions > 0 ? Math.round((reschedules / totalActions) * 100) : null;
  const team = todayPoint?.team_reschedule_events ?? 0;
  const field = todayPoint?.field_reschedule_events ?? 0;
  const unknown = todayPoint?.unknown_reschedule_events ?? 0;
  const teamPct = reschedules > 0 ? Math.round((team / reschedules) * 100) : null;
  const fieldPct = reschedules > 0 ? Math.round((field / reschedules) * 100) : null;
  const unknownPct = reschedules > 0 && teamPct !== null && fieldPct !== null ? Math.max(0, 100 - teamPct - fieldPct) : null;
  const pendingIsHigh = (pendingOrders ?? 0) > 50;
  const slaMet = todaySlaRate !== null && todaySlaTarget !== null && todaySlaRate >= todaySlaTarget;

  return (
    <div aria-busy={loading} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <TodayTile
        title="Reagendamentos hoje"
        value={rescheduleRate !== null ? `${number(reschedules)} · ${rescheduleRate}%` : number(reschedules)}
        helper="Taxa sobre o total de ações do dia · toque para ver quem reagendou"
        tone={reschedules > 0 ? "amber" : "slate"}
        icon={RefreshCcw}
        onClick={reschedules > 0 ? onOpenToday : undefined}
      />
      <TodayTile
        title="SLA do dia"
        value={number(todaySlaRate, "%")}
        helper={todaySlaTarget !== null ? `Meta: ${number(todaySlaTarget, "%")}` : "% agendado dentro do prazo útil"}
        tone={todaySlaRate === null ? "slate" : slaMet ? "blue" : "red"}
        icon={CalendarClock}
      />
      <TodayTile
        title="Equipe vs campo"
        value={teamPct !== null ? `${teamPct}% / ${fieldPct}% / ${unknownPct}%` : "—"}
        helper={`Equipe ${number(team)} · Campo ${number(field)} · Desconhecido ${number(unknown)}`}
        tone="slate"
        icon={Users}
      >
        {teamPct !== null && fieldPct !== null && unknownPct !== null ? (
          <div className="mt-2 flex h-1.5 overflow-hidden rounded-full">
            <div className="bg-blue-500" style={{ width: `${teamPct}%` }} />
            <div className="bg-orange-400" style={{ width: `${fieldPct}%` }} />
            <div className="bg-slate-300" style={{ width: `${unknownPct}%` }} />
          </div>
        ) : null}
      </TodayTile>
      <TodayTile
        title="Aguardando agendamento"
        value={number(pendingOrders)}
        helper="Fila atual, independente do mês em navegação - toque para ver a lista"
        tone={pendingIsHigh ? "red" : "slate"}
        icon={Inbox}
        onClick={pendingOrders ? onOpenPending : undefined}
      />
    </div>
  );
}
