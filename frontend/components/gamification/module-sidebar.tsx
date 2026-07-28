"use client";

import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  History,
  LogOut,
  Menu,
  RefreshCw,
  Settings2,
  ShieldAlert,
  Trophy,
  Wallet,
  X
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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

const COLLAPSE_STORAGE_KEY = "uni-gamificacao-sidebar-collapsed";

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
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(COLLAPSE_STORAGE_KEY);
    if (stored === "1") setCollapsed(true);
  }, []);

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

  function selectTab(value: string) {
    onTabChange(value);
    setMobileOpen(false);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir navegação do módulo"
        className="fixed left-3 top-3 z-40 flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {mobileOpen ? (
        <div
          className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-dvh shrink-0 flex-col border-r border-slate-200 bg-white transition-[width,transform] duration-200 ease-out lg:static lg:z-auto lg:translate-x-0",
          mobileOpen ? "translate-x-0 w-72" : "-translate-x-full",
          collapsed ? "lg:w-[76px]" : "lg:w-64"
        )}
      >
        <div className={cn("flex items-center gap-3 border-b border-slate-200 px-5 py-5", collapsed && "lg:justify-center lg:px-3")}>
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
            <img src="/brand/uni-logo.png" alt="UNI Internet" className="max-h-7 w-auto object-contain" />
          </div>
          <div className={cn("min-w-0", collapsed && "lg:hidden")}>
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-uni-royal">UNI Workspace</div>
            <div className="truncate text-sm font-semibold text-slate-950">Gamificação Operacional</div>
          </div>
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="Fechar navegação"
            className="ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-50 lg:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Volta ao hub de módulos (Gamificação/Operação/Admin) - antes não existia nenhum jeito
            de sair do módulo sem apagar a URL manualmente. */}
        <Link
          href="/"
          title={collapsed ? "Voltar ao ecossistema" : undefined}
          className={cn(
            "flex items-center gap-2 border-b border-slate-200 px-5 py-3 text-xs font-medium text-slate-500 transition hover:bg-slate-50 hover:text-uni-royal",
            collapsed && "lg:justify-center lg:px-0"
          )}
        >
          <ArrowLeft className="h-3.5 w-3.5 shrink-0" />
          <span className={cn(collapsed && "lg:hidden")}>Voltar ao ecossistema</span>
        </Link>

        {canRecalculate ? (
          <div className={cn("border-b border-slate-200 px-3 py-3", collapsed && "lg:px-2")}>
            <Button
              type="button"
              onClick={onRecalculate}
              disabled={recalculating}
              title={isPaidPeriod ? "Criar revisão" : "Recalcular pontuação"}
              className={cn("h-10 w-full justify-center rounded-xl", collapsed && "lg:w-10 lg:px-0")}
            >
              <RefreshCw className={recalculating ? "h-4 w-4 shrink-0 animate-spin" : "h-4 w-4 shrink-0"} />
              <span className={cn(collapsed && "lg:hidden")}>{isPaidPeriod ? "Criar revisão" : "Recalcular pontuação"}</span>
            </Button>
          </div>
        ) : null}

        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-3" aria-label="Navegação do módulo">
          <div className="grid gap-1">
            {NAV_ITEMS.filter((item) => visibleTabs.has(item.value)).map((item) => {
              const Icon = item.icon;
              const active = activeTab === item.value;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => selectTab(item.value)}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                    collapsed && "lg:justify-center lg:px-0",
                    active
                      ? "bg-[color:rgba(45,95,255,0.1)] font-semibold text-[var(--uni-electric)]"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className={cn("truncate", collapsed && "lg:hidden")}>{item.label}</span>
                </button>
              );
            })}
          </div>
        </nav>

        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
          className={cn(
            "hidden items-center gap-2 border-t border-slate-200 px-5 py-3 text-xs font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-800 lg:flex",
            collapsed && "justify-center px-0"
          )}
        >
          {collapsed ? <ChevronsRight className="h-4 w-4 shrink-0" /> : <ChevronsLeft className="h-4 w-4 shrink-0" />}
          <span className={cn(collapsed && "hidden")}>Recolher menu</span>
        </button>

        {user ? (
          <div className={cn("border-t border-slate-200 px-3 py-3", collapsed && "lg:px-2")}>
            <div className={cn("flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2.5", collapsed && "lg:justify-center lg:px-0")}>
              <div className={cn("min-w-0", collapsed && "lg:hidden")}>
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
    </>
  );
}
