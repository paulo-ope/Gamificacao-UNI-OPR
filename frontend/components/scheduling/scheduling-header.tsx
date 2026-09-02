"use client";

import Link from "next/link";
import { CalendarClock, Home, LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";

import { SchedulingModuleSidebar, type SchedulingTab } from "./scheduling-module-sidebar";

// Mesmo padrão de header dos outros módulos (`OperationsModuleSidebar` em /operacao,
// `ModuleNavigationSidebar` em /suporte): menu lateral deslizante + identidade à esquerda, ações
// globais à direita. Sem badge de sync nem botões de admin aqui - essas visões agora são itens do
// próprio menu (ver `scheduling-module-sidebar.tsx`).
export function SchedulingHeader({
  activeTab,
  onChangeTab,
  onLogout,
}: {
  activeTab: SchedulingTab;
  onChangeTab: (tab: SchedulingTab) => void;
  onLogout: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 lg:px-7">
        <div className="flex items-center gap-3">
          <SchedulingModuleSidebar activeTab={activeTab} onChange={onChangeTab} />
          <Link
            href="/"
            aria-label="Voltar ao ecossistema"
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700"
          >
            <Home className="h-5 w-5" />
          </Link>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-600">UNI Workspace</p>
            <h1 className="flex items-center gap-1.5 text-base font-semibold text-slate-950">
              <CalendarClock className="h-4 w-4 text-blue-600" /> Agendamento
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onLogout}>
            <LogOut className="h-4 w-4" /> Sair
          </Button>
        </div>
      </div>
    </header>
  );
}
