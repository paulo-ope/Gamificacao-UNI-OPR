import { secondsLabel } from "@/lib/format-duration";
import type { SupportTvAttendant, SupportTvCount } from "@/lib/support-tv-api";
import { cn } from "@/lib/utils";
import { formatCount, TvCard, TvEmpty, TvUnavailable } from "./tv-primitives";
import { TV_CLASSES, TV_SERIES, type TvTheme } from "./tv-theme";

function ratingLabel(value: number | null) {
  return value === null ? "—" : value.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

export function TvAttendantsPanel({ items, theme }: { items: SupportTvAttendant[] | null; theme: TvTheme }) {
  const t = TV_CLASSES[theme];
  return (
    <TvCard theme={theme} eyebrow="Atendentes — volume do dia">
      {!items ? (
        <TvUnavailable theme={theme} />
      ) : items.length === 0 ? (
        <TvEmpty theme={theme}>Nenhum atendimento humano hoje.</TvEmpty>
      ) : (
        <ol className="flex flex-1 flex-col justify-between gap-1">
          {items.map((item, index) => {
            const tmr = item.average_tmr_seconds === null ? "—" : secondsLabel(item.average_tmr_seconds);
            return (
              <li key={item.attendant_id} className={cn("flex items-center gap-4 border-b py-2 last:border-b-0", t.divider)}>
                <span className={cn("w-6 text-center text-xl font-bold tabular-nums", t.muted)}>{index + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-xl font-semibold leading-tight md:truncate md:text-2xl", t.title)}>{item.name}</span>
                  {/* Em tela estreita o TMR e a nota descem para baixo do nome em vez de sumirem. */}
                  <span className={cn("block text-sm tabular-nums md:hidden", t.muted)}>
                    TMR {tmr} · ★ {ratingLabel(item.average_rating)}
                  </span>
                </span>
                <span className={cn("w-16 text-right text-3xl font-extrabold tabular-nums", t.value)}>{formatCount(item.total)}</span>
                <span className={cn("hidden w-40 text-right text-lg tabular-nums md:block", t.muted)}>TMR {tmr}</span>
                <span className={cn("hidden w-16 text-right text-lg tabular-nums md:block", t.muted)}>★ {ratingLabel(item.average_rating)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </TvCard>
  );
}

function CountList({ theme, items, empty }: { theme: TvTheme; items: SupportTvCount[]; empty: string }) {
  const t = TV_CLASSES[theme];
  if (items.length === 0) return <TvEmpty theme={theme}>{empty}</TvEmpty>;
  const max = Math.max(...items.map((item) => item.total), 1);
  return (
    <ul className="flex flex-1 flex-col justify-between gap-1.5">
      {items.map((item) => (
        <li key={item.label}>
          <div className="flex items-baseline justify-between gap-3">
            <span className={cn("min-w-0 truncate text-lg", t.title)}>{item.label}</span>
            <span className={cn("text-xl font-bold tabular-nums", t.value)}>{formatCount(item.total)}</span>
          </div>
          <div className={cn("mt-1 h-2 overflow-hidden rounded-full", t.barTrack)} role="presentation">
            <div className="h-full rounded-full" style={{ width: `${(item.total / max) * 100}%`, backgroundColor: TV_SERIES.today }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

// Dois canais principais + "outros" somado: a linha nunca quebra e nenhum atendimento some da conta.
function channelSummary(channels: SupportTvCount[]): string {
  const [first, second, ...rest] = channels;
  const parts = [first, second].filter((channel): channel is SupportTvCount => Boolean(channel)).map((channel) => `${channel.label} ${formatCount(channel.total)}`);
  const others = rest.reduce((sum, channel) => sum + channel.total, 0);
  if (others > 0) parts.push(`outros ${formatCount(others)}`);
  return parts.join(" · ");
}

export function TvReasonsPanel({ reasons, channels, theme }: { reasons: SupportTvCount[] | null; channels: SupportTvCount[] | null; theme: TvTheme }) {
  const t = TV_CLASSES[theme];
  return (
    <TvCard theme={theme} eyebrow="Principais motivos">
      {reasons ? <CountList theme={theme} items={reasons} empty="Sem atendimentos hoje." /> : <TvUnavailable theme={theme} />}
      {channels && channels.length > 0 && (
        <p className={cn("mt-3 border-t pt-2 text-base", t.divider, t.muted)}>
          Canais: {channelSummary(channels)}
        </p>
      )}
    </TvCard>
  );
}
