import type { SupportTvPresence } from "@/lib/support-tv-api";
import { cn } from "@/lib/utils";
import { formatCount, TvCard, TvEmpty, TvUnavailable } from "./tv-primitives";
import { presenceColor, TV_CLASSES, type TvTheme } from "./tv-theme";

function availableLabel(percentage: number | null) {
  return percentage === null ? "" : `${percentage.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% disponível`;
}

// "há 30 min" / "há 1 h 05 min" / "agora". Sem data (null) não mostra tempo - nunca inventa.
function sinceLabel(seconds: number | null): string {
  if (seconds === null) return "";
  if (seconds < 60) return "agora";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  return `há ${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export function TvPresencePanel({ presence, theme }: { presence: SupportTvPresence | null; theme: TvTheme }) {
  const t = TV_CLASSES[theme];
  const hidden = presence ? presence.agents_total - presence.agents.length : 0;
  return (
    <TvCard
      theme={theme}
      eyebrow="Status dos atendentes"
      aside={presence ? <span className={cn("shrink-0 whitespace-nowrap text-base font-bold tabular-nums", t.value)}>{availableLabel(presence.available_percentage)}</span> : null}
    >
      {!presence ? (
        <TvUnavailable theme={theme} />
      ) : presence.total === 0 ? (
        <TvEmpty theme={theme}>Nenhum atendente com atendimento nos últimos 30 dias.</TvEmpty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2.5">
          <ul className="grid grid-cols-3 gap-x-4 gap-y-1.5">
            {presence.states.map((state) => (
              <li key={state.code} className="flex items-stretch gap-2.5">
                <span className="w-1 shrink-0 rounded-full" style={{ backgroundColor: presenceColor(state.code, theme) }} aria-hidden="true" />
                <div className="min-w-0">
                  <p className={cn("truncate text-sm leading-tight", t.muted)}>{state.label}</p>
                  <p className={cn("text-2xl font-extrabold leading-tight tabular-nums", t.value)}>{formatCount(state.total)}</p>
                </div>
              </li>
            ))}
          </ul>

          <div className={cn("flex min-h-0 flex-1 flex-col border-t pt-1.5", t.divider)}>
            {presence.agents.length === 0 ? (
              <p className={cn("py-2 text-lg", t.muted)}>Ninguém em ligação, ocupado, em pausa ou ausente agora.</p>
            ) : (
              <ul className="min-h-0 flex-1 overflow-hidden">
                {presence.agents.map((agent) => (
                  <li key={`${agent.state_code}-${agent.name}`} className="flex items-center gap-2.5 py-0.5">
                    <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", agent.state_code === "call" && "tv-live")} style={{ backgroundColor: presenceColor(agent.state_code, theme) }} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className={cn("block truncate text-lg font-semibold leading-tight", t.title)}>{agent.name}</span>
                      {/* Celular: status e tempo descem para baixo do nome (o nome nunca é cortado). */}
                      <span className={cn("block text-sm sm:hidden", t.muted)}>
                        {agent.state_label.toLowerCase()} · <span className={cn("font-medium tabular-nums", t.value)}>{sinceLabel(agent.seconds_in_state)}</span>
                      </span>
                    </span>
                    <span className={cn("hidden shrink-0 whitespace-nowrap text-base sm:inline", t.muted)}>{agent.state_label.toLowerCase()}</span>
                    <span className={cn("hidden shrink-0 whitespace-nowrap text-right text-base font-medium tabular-nums sm:inline", t.value)}>{sinceLabel(agent.seconds_in_state)}</span>
                  </li>
                ))}
              </ul>
            )}
            {hidden > 0 && <p className={cn("text-sm", t.muted)}>+{hidden} {hidden === 1 ? "outro" : "outros"} neste momento</p>}
            {/* Honestidade sobre o que o OPA entrega: o tempo é aproximado e "tocando" não existe na API. */}
            <p className={cn("mt-auto pt-1 text-xs leading-snug", t.muted)}>
              Tempo aproximado{!presence.ringing_available ? " · ligação tocando não vem do OPA" : ""}
            </p>
          </div>
        </div>
      )}
    </TvCard>
  );
}
