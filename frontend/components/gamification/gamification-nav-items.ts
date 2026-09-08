import {
  AlertTriangle,
  CalendarDays,
  ClipboardList,
  History,
  Settings2,
  ShieldAlert,
  Trophy,
  Wallet,
} from "lucide-react";

import type { ModuleNavigationItem } from "@/components/workspace/module-navigation-sidebar";

/**
 * Telas internas da Gamificação Operacional.
 *
 * Ficava dentro de `app/gamificacao/page.tsx`. Saiu para cá quando a navegação global do
 * ecossistema passou a listar as telas de cada módulo no menu lateral (`lib/module-screens.ts`) -
 * uma página não é lugar de onde outra parte da aplicação possa importar.
 */
export const GAMIFICATION_NAV_ITEMS: Array<ModuleNavigationItem<string>> = [
  { value: "closure", label: "Fechamento", description: "Resumo financeiro do período", icon: ClipboardList },
  { value: "ranking", label: "Ranking", description: "Comparação de desempenho", icon: Trophy },
  { value: "pending", label: "Pendências", description: "Itens que exigem revisão", icon: AlertTriangle },
  { value: "config", label: "Configuração", description: "Regras e parâmetros", icon: Settings2 },
  { value: "audit", label: "Auditoria", description: "Registros e rastreabilidade", icon: ShieldAlert },
  { value: "balance", label: "Saldo de pontos", description: "Débitos de garantia pendentes", icon: Wallet },
  { value: "history", label: "Histórico", description: "Períodos anteriores", icon: History },
  { value: "import", label: "Período", description: "Mês de referência da análise", icon: CalendarDays },
];
