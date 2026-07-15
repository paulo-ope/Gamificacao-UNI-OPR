"use client";

import type { LucideIcon } from "lucide-react";
import { AlertTriangle, CalendarDays, ClipboardList, History, LogOut, RefreshCw, Settings2, ShieldAlert, Trophy, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AuthUser } from "@/lib/types";

type NavItem = {
  value: string;
  label: string;
  icon: LucideIcon;
};

const NAV_ITEMS: NavItem[] = [
  { value: "closure", label: "Fechamento", icon: ClipboardList },
  { value: "ranking", label: "Ranking", icon: Trophy },
  { value: "pending", label: "Pendências", icon: AlertTriangle },
  { value: "config", label: "Configuração", icon: Settings2 },
  { value: "audit", label: "Auditoria", icon: ShieldAlert },
  { value: "balance", label: "Saldo de pontos", icon: Wallet },
  { value: "history", label: "Histórico", icon: History },
  { value: "import", label: "Período", icon: CalendarDays }
];

type Props = {
  activeTab: string;
  onTabChange: (value: string) => void;
  visibleTabs: Set<string>;
  user: AuthUser | null;
  onLogout: () => void;
  canRecalculate: boolean;
  onRecalculate: () => void;
  recalculating: boolean;
  isPaidPeriod: boolean;
};

export function ModuleSidebar({
  activeTab,
  onTabChange,
  visibleTabs,
  user,
  onLogout,
  canRecalculate,
  onRecalculate,
  recalculating,
  isPaidPeriod
}: Props) {
  return (
    <aside className="flex h-dvh w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
          <img src="/brand/uni-logo.png" alt="UNI Internet" className="max-h-7 w-auto object-contain" />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">UNI Workspace</div>
          <div className="truncate text-sm font-semibold text-slate-950">Gamificação Operacional</div>
        </div>
      </div>

      {canRecalculate ? (
        <div className="border-b border-slate-200 px-3 py-3">
          <Button type="button" onClick={onRecalculate} disabled={recalculating} className="h-10 w-full justify-center rounded-xl">
            <RefreshCw className={recalculating ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            {isPaidPeriod ? "Criar revisão" : "Recalcular pontuação"}
          </Button>
        </div>
      ) : null}

      <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Navegação do módulo">
        <div className="grid gap-1">
          {NAV_ITEMS.filter((item) => visibleTabs.has(item.value)).map((item) => {
            const Icon = item.icon;
            const active = activeTab === item.value;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => onTabChange(item.value)}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "flex items-center gap-3 rounded-xl bg-primary/10 px-3 py-2.5 text-sm font-semibold text-primary"
                    : "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {user ? (
        <div className="border-t border-slate-200 px-3 py-3">
          <div className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2.5">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-950">{user.name}</div>
              <div className="truncate text-[11px] uppercase tracking-wide text-slate-500">{user.role}</div>
            </div>
            <button
              type="button"
              onClick={onLogout}
              title="Sair"
              aria-label="Sair"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white hover:text-red-600"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
