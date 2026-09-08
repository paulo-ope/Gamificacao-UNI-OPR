"use client";

import { BarChart3, CalendarDays, ClipboardList, Gauge, Inbox, ListChecks, Radio, Settings2, ShieldCheck } from "lucide-react";

export type OperationTab = "overview" | "openings" | "sla" | "garantias" | "calendar" | "progress" | "details" | "network" | "teams";

// Exportado para a navegação global do ecossistema (`lib/module-screens.ts`) poder listar as
// telas deste módulo no menu lateral sem manter uma segunda cópia dos rótulos.
export const OPERATION_NAV_ITEMS: Array<{ value: OperationTab; label: string; description: string; icon: typeof Gauge }> = [
  { value: "overview", label: "Visão Geral", description: "Indicadores do período", icon: Gauge },
  { value: "openings", label: "Aberturas", description: "Entrada e desvios", icon: Inbox },
  { value: "progress", label: "Andamento", description: "Todo o backlog aberto", icon: ListChecks },
  { value: "sla", label: "SLA", description: "Prazos e produtividade", icon: BarChart3 },
  { value: "garantias", label: "Garantias", description: "Retornos em garantia de ativação", icon: ShieldCheck },
  { value: "calendar", label: "Calendário", description: "Produção mensal", icon: CalendarDays },
  { value: "details", label: "Detalhamento", description: "Drill-through e busca", icon: ClipboardList },
  { value: "network", label: "Rede", description: "Quedas de conexão por proximidade", icon: Radio },
  { value: "teams", label: "Config", description: "Modelos, jornadas, metas e assuntos", icon: Settings2 }
];

// O menu hambúrguer próprio deste módulo foi retirado em 2026-09-03: as telas de cada módulo
// agora vivem no submenu da barra lateral do ecossistema (`components/workspace/app-shell.tsx`,
// alimentada por `lib/module-screens.ts`). O que sobra aqui é a LISTA de telas, que a barra
// global consome - e o tipo da aba, usado pelo próprio módulo.
