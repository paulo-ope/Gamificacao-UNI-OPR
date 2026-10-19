import { secondsLabel } from "@/lib/format-duration";
import type { SupportTvQueue } from "@/lib/support-tv-api";
import { cn } from "@/lib/utils";
import { formatCount, TvCard, TvEmpty, TvUnavailable } from "./tv-primitives";
import { TV_CLASSES, type TvStatus, type TvTheme } from "./tv-theme";

// Faixas de espera da TV (só sinalização visual, não é meta do negócio): a partir daqui o cliente
// passa a pedir atenção / está esperando demais.
const WAIT_ATTENTION_SECONDS = 5 * 60;
const WAIT_CRITICAL_SECONDS = 15 * 60;

function waitStatus(seconds: number): TvStatus {
  return seconds >= WAIT_CRITICAL_SECONDS ? "critical" : seconds >= WAIT_ATTENTION_SECONDS ? "attention" : "ok";
}

export function TvQueuePanel({ queue, theme }: { queue: SupportTvQueue | null; theme: TvTheme }) {
  const t = TV_CLASSES[theme];
  const status: TvStatus = queue?.longest_wait_seconds ? waitStatus(queue.longest_wait_seconds) : "neutral";
  const hidden = queue ? queue.total - queue.items.length : 0;
  return (
    <TvCard
      theme={theme}
      eyebrow="Fila de espera"
      status={status === "ok" ? "neutral" : status}
      aside={queue && <span className={cn("text-3xl font-extrabold tabular-nums", t.value)}>{formatCount(queue.total)}</span>}
    >
      {!queue ? (
        <TvUnavailable theme={theme} />
      ) : queue.items.length === 0 ? (
        <TvEmpty theme={theme}>Ninguém aguardando na fila.</TvEmpty>
      ) : (
        <>
          <ul className="flex flex-1 flex-col justify-between gap-1">
            {queue.items.map((item, index) => (
              <li key={`${item.label}-${index}`} className={cn("flex items-center gap-3 border-b py-1.5 last:border-b-0", t.divider)}>
                <span className={cn("h-2.5 w-2.5 flex-shrink-0 rounded-full", t.status[waitStatus(item.wait_seconds)].dot)} aria-hidden="true" />
                <span className={cn("min-w-0 flex-1 truncate text-lg font-semibold", t.title)}>{item.label}</span>
                <span className={cn("text-lg font-bold tabular-nums", t.value)}>{secondsLabel(item.wait_seconds)}</span>
              </li>
            ))}
          </ul>
          {hidden > 0 && <p className={cn("mt-2 text-base", t.muted)}>+ {formatCount(hidden)} aguardando</p>}
        </>
      )}
    </TvCard>
  );
}
