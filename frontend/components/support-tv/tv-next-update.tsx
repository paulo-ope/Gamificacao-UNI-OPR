import { cn } from "@/lib/utils";
import { TV_CLASSES, type TvTheme } from "./tv-theme";

const SUPPORT_TIMEZONE = "America/Porto_Velho";

// "Próxima atualização: 14:18:57" - mesma forma da linha "Atualizado às 14:18:27" logo acima, só com a
// hora em que o próximo ciclo vai buscar os dados (sem contagem regressiva).
export function TvNextUpdate({ at, theme }: { at: Date | null; theme: TvTheme }) {
  if (!at) return null;
  const clock = at.toLocaleTimeString("pt-BR", { timeZone: SUPPORT_TIMEZONE, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <p className={cn("text-sm tabular-nums", TV_CLASSES[theme].muted)} data-testid="tv-next-update">
      Próxima atualização: {clock}
    </p>
  );
}
