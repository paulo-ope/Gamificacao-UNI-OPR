"use client";

import { BarChart3, CalendarDays, Clock3, Settings2 } from "lucide-react";

// 4 itens, não 7 (pedido do usuário 2026-08-31: "várias aba, não sei se faz sentido") - Equipe,
// Configurações e Sincronização eram tarefas de setup de baixa frequência, cada uma com item
// próprio no menu; agora são sub-seções dentro de uma única aba "Administração".
export type SchedulingTab = "painel" | "rankings" | "desempenho" | "administracao";

// Exportado para a navegação global do ecossistema (ver `lib/module-screens.ts`).
export const SCHEDULING_NAV_ITEMS: Array<{ value: SchedulingTab; label: string; description: string; icon: typeof CalendarDays }> = [
  { value: "painel", label: "Painel", description: "Resumo do dia e calendário mensal", icon: CalendarDays },
  { value: "rankings", label: "Rankings e fila", description: "Produtividade, reagendamentos e O.S. sem agendamento", icon: BarChart3 },
  { value: "desempenho", label: "Desempenho", description: "SLA e tempo de resposta", icon: Clock3 },
  { value: "administracao", label: "Administração", description: "Equipe, configurações e sincronização", icon: Settings2 },
];

// O menu hambúrguer próprio deste módulo foi retirado em 2026-09-03: as telas de cada módulo
// agora vivem no submenu da barra lateral do ecossistema (`components/workspace/app-shell.tsx`,
// alimentada por `lib/module-screens.ts`). O que sobra aqui é a LISTA de telas, que a barra
// global consome - e o tipo da aba, usado pelo próprio módulo.
