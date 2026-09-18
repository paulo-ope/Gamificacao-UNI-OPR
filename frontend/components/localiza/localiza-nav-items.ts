import { Map, MapPin } from "lucide-react";

/**
 * Telas internas do UNI Localiza.
 *
 * Mesma função das listas equivalentes dos outros módulos (`OPERATION_NAV_ITEMS`,
 * `ADMIN_NAV_ITEMS`...): a página usa esta lista para desenhar as abas e `lib/module-screens.ts`
 * importa a MESMA lista para o menu lateral do ecossistema poder abrir cada tela direto, sem
 * entrar no módulo e caçar a aba. Manter uma segunda cópia dos rótulos garantiria divergência na
 * primeira vez que alguém renomeasse uma aba.
 */
export const LOCALIZA_NAV_ITEMS = [
  {
    value: "solicitacoes",
    label: "Solicitações",
    description: "Links gerados e posições confirmadas",
    icon: MapPin,
  },
  {
    value: "mapa",
    label: "Mapa",
    description: "Clientes já localizados por GPS",
    icon: Map,
  },
] as const;

export type LocalizaTab = (typeof LOCALIZA_NAV_ITEMS)[number]["value"];

export function isLocalizaTab(value: string | null | undefined): value is LocalizaTab {
  return LOCALIZA_NAV_ITEMS.some((item) => item.value === value);
}
