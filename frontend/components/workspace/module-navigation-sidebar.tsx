import type { LucideIcon } from "lucide-react";

export type ModuleNavigationItem<TValue extends string> = {
  value: TValue;
  label: string;
  description: string;
  icon: LucideIcon;
};

// O menu hambúrguer próprio deste módulo foi retirado em 2026-09-03: as telas de cada módulo
// agora vivem no submenu da barra lateral do ecossistema (`components/workspace/app-shell.tsx`,
// alimentada por `lib/module-screens.ts`). O que sobra aqui é a LISTA de telas, que a barra
// global consome - e o tipo da aba, usado pelo próprio módulo.
