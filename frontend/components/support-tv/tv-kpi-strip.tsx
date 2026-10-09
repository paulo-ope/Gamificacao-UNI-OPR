import { secondsLabel } from "@/lib/format-duration";
import type { SupportTvKpis } from "@/lib/support-tv-api";
import { cn } from "@/lib/utils";
import { AnimatedNumber } from "./tv-animated-number";
import { formatCount, formatPercent, TvCard, TvUnavailable } from "./tv-primitives";
import { TV_CLASSES, type TvStatus, type TvTheme } from "./tv-theme";

const TMR_STATUS: Record<SupportTvKpis["tmr_all_responses"]["status"], TvStatus> = {
  ok: "ok",
  above: "critical",
  no_data: "neutral",
};

// Hierarquia: o TMR é o único número em 7xl; os demais ficam um degrau abaixo (5xl), para o olho
// ir primeiro ao indicador que tem meta.
function Big({ theme, children, status = "neutral", hero = false }: { theme: TvTheme; children: React.ReactNode; status?: TvStatus; hero?: boolean }) {
  return (
    <p className={cn("font-extrabold leading-none tracking-tight tabular-nums", hero ? "text-6xl" : "text-5xl", TV_CLASSES[theme].status[status].text)}>
      {children}
    </p>
  );
}

function Sub({ theme, children, className }: { theme: TvTheme; children: React.ReactNode; className?: string }) {
  return <p className={cn("mt-2.5 text-base leading-snug", TV_CLASSES[theme].muted, className)}>{children}</p>;
}

function ratingLabel(value: number | null) {
  return value === null ? "—" : value.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

// Medidor do TMR: a barra vai de 0 a 2× a meta e o traço fixo no meio é a meta. Quem olha de longe vê
// "passou do traço" sem ler número nenhum.
function TmrMeter({ theme, current, target, status }: { theme: TvTheme; current: number | null; target: number; status: TvStatus }) {
  const t = TV_CLASSES[theme];
  const fill = current === null ? 0 : Math.min(1, Math.max(0, current / (target * 2))) * 100;
  return (
    <div className={cn("relative mt-4 h-3 rounded-full", t.barTrack)} role="img" aria-label={current === null ? "Sem dado de TMR" : `TMR ${secondsLabel(current)} contra meta de ${secondsLabel(target)}`}>
      <div className={cn("h-full rounded-full transition-[width] duration-700 ease-out", t.status[status === "neutral" ? "ok" : status].bar)} style={{ width: `${fill}%` }} />
      <span className={cn("absolute -top-1.5 left-1/2 h-6 w-0.5 -translate-x-1/2 rounded-full", theme === "dark" ? "bg-white" : "bg-slate-900")} aria-hidden="true" />
    </div>
  );
}

// Variação contra o dia anterior em segundos: menor é melhor, então subir é "pior".
function TmrDelta({ theme, current, previous }: { theme: TvTheme; current: number | null; previous: number | null }) {
  const t = TV_CLASSES[theme];
  if (current === null || previous === null) return <span>Ontem: sem dado</span>;
  const delta = Math.round(current - previous);
  if (delta === 0) return <span>Igual a ontem ({secondsLabel(previous)})</span>;
  const worse = delta > 0;
  return (
    <span>
      <span className={cn("font-semibold", worse ? t.status.attention.text : t.status.ok.text)}>
        {worse ? "▲ +" : "▼ −"}
        {secondsLabel(Math.abs(delta))}
      </span>{" "}
      contra ontem ({secondsLabel(previous)})
    </span>
  );
}

export function TvKpiStrip({ kpis, theme }: { kpis: SupportTvKpis | null; theme: TvTheme }) {
  const gridClass = "grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-[2.1fr_1fr_1fr_1fr_1fr]";
  if (!kpis) {
    return (
      <div className={gridClass}>
        {["TMR geral", "Atendimentos hoje", "Em andamento", "Encerramento", "Avaliação média"].map((title, index) => (
          <TvCard key={title} theme={theme} eyebrow={title} revealDelay={index * 60} className={index === 0 ? "col-span-2 md:col-span-4 xl:col-span-1" : undefined}>
            <TvUnavailable theme={theme} />
          </TvCard>
        ))}
      </div>
    );
  }

  const tmr = kpis.tmr_all_responses;
  const tmrStatus = TMR_STATUS[tmr.status];
  const coverage = tmr.coverage;

  return (
    <div className={gridClass}>
      {/* Indicador principal: TMR geral (conta resposta de bot) contra a meta operacional. */}
      <TvCard
        theme={theme}
        eyebrow="TMR geral (com bot)"
        status={tmrStatus}
        className="col-span-2 md:col-span-4 xl:col-span-1"
        aside={coverage.total > 0 ? <span className={cn("text-sm tabular-nums", TV_CLASSES[theme].muted)}>base {formatCount(coverage.count)} de {formatCount(coverage.total)}</span> : null}
      >
        <Big theme={theme} status={tmrStatus} hero>
          {tmr.current_seconds === null ? "—" : secondsLabel(tmr.current_seconds)}
        </Big>
        <TmrMeter theme={theme} current={tmr.current_seconds} target={tmr.target_seconds} status={tmrStatus} />
        <p className={cn("mt-2.5 flex flex-wrap items-baseline justify-between gap-x-4 text-base tabular-nums", TV_CLASSES[theme].muted)}>
          <span>meta {secondsLabel(tmr.target_seconds)}</span>
          <TmrDelta theme={theme} current={tmr.current_seconds} previous={tmr.previous_seconds} />
        </p>
      </TvCard>

      <TvCard theme={theme} eyebrow="Atendimentos hoje" revealDelay={60}>
        <Big theme={theme}>
          <AnimatedNumber value={kpis.total_today} format={(value) => formatCount(Math.round(value))} />
        </Big>
        {/* Ontem é o dia INTEIRO e hoje é parcial: por isso só o número, nunca uma variação em %. */}
        <Sub theme={theme}>Ontem (dia todo): {formatCount(kpis.previous_day_total)}</Sub>
      </TvCard>

      <TvCard theme={theme} eyebrow="Em andamento agora" revealDelay={120}>
        <Big theme={theme}>
          <AnimatedNumber value={kpis.open_now} format={(value) => formatCount(Math.round(value))} />
        </Big>
        <Sub theme={theme}>Abertos nas últimas 24 h</Sub>
      </TvCard>

      <TvCard theme={theme} eyebrow="Encerramento" revealDelay={180}>
        <Big theme={theme}>
          <AnimatedNumber value={kpis.closure_rate} format={(value) => formatPercent(Math.round(value))} />
        </Big>
        <Sub theme={theme}>{formatCount(kpis.closed_today)} encerrados hoje</Sub>
      </TvCard>

      <TvCard theme={theme} eyebrow="Avaliação média" revealDelay={240}>
        <Big theme={theme}>{ratingLabel(kpis.average_rating)}</Big>
        <Sub theme={theme}>Ontem: {kpis.previous_average_rating === null ? "sem dado" : ratingLabel(kpis.previous_average_rating)}</Sub>
      </TvCard>
    </div>
  );
}
