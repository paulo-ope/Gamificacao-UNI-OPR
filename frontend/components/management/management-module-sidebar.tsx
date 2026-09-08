"use client";

import { BriefcaseBusiness, ClipboardList, ListChecks, ShieldAlert, Tag } from "lucide-react";

export type ManagementTab = "structure" | "cases" | "diagnostics" | "reasons" | "audit";

// Exportado para a navegação global do ecossistema (ver `lib/module-screens.ts`).
export const MANAGEMENT_NAV_ITEMS: Array<{ value: ManagementTab; label: string; description: string; icon: typeof BriefcaseBusiness }> = [
  { value: "structure", label: "Estrutura operacional", description: "Colaboradores, supervisor e modelo de equipe", icon: BriefcaseBusiness },
  { value: "cases", label: "Casos de gestão", description: "Justificativas e decisão da matriz", icon: ListChecks },
  { value: "diagnostics", label: "Diagnóstico", description: "Ranking por motivo, colaborador e regional", icon: ClipboardList },
  { value: "audit", label: "Auditoria da estrutura", description: "Inconsistências antes da capacidade regional", icon: ShieldAlert },
  { value: "reasons", label: "Motivos de justificativa", description: "Catálogo de motivos pré-cadastrados", icon: Tag },
];

// O menu hambúrguer próprio deste módulo foi retirado em 2026-09-03: as telas de cada módulo
// agora vivem no submenu da barra lateral do ecossistema (`components/workspace/app-shell.tsx`,
// alimentada por `lib/module-screens.ts`). O que sobra aqui é a LISTA de telas, que a barra
// global consome - e o tipo da aba, usado pelo próprio módulo.
