import type { SupportTvN1, SupportTvRadar } from "@/lib/support-tv-api";
import { cn } from "@/lib/utils";
import { formatCount, TvCard } from "./tv-primitives";
import { TV_CLASSES, type TvStatus, type TvTheme } from "./tv-theme";

type RadarLine = { key: string; status: TvStatus; text: string };

// Abaixo disto o dia está claramente mais fraco que o normal para o mesmo horário.
const PACE_BELOW_RATIO = 0.75;

function decimal(value: number) {
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

function protocols(count: number) {
  return `${formatCount(count)} protocolo${count === 1 ? "" : "s"} operaciona${count === 1 ? "l" : "is"}`;
}

// Cada linha vira uma frase curta, SEMPRE com o número absoluto ao lado do esperado ("22 hoje, esperado
// 6") - percentual sozinho engana quando a base é pequena. Fonte que não respondeu (`null`) é dita como
// indisponível, nunca como "sem problema" (um radar mudo não pode parecer um radar tranquilo).
function radarLines(radar: SupportTvRadar): RadarLine[] {
  const lines: RadarLine[] = [];
  const noHistory = radar.baseline_weeks_used === 0;

  // 1) ritmo do dia
  if (radar.pace === null) {
    lines.push({ key: "pace", status: "neutral", text: "Ritmo de hoje: indisponível" });
  } else if (radar.pace.status === "no_baseline" || radar.pace.expected_so_far === null) {
    lines.push({ key: "pace", status: "neutral", text: `Hoje: ${protocols(radar.pace.observed_today)} (sem histórico para comparar)` });
  } else {
    const expected = `esperado até agora: ${decimal(radar.pace.expected_so_far)}`;
    // Abaixo do esperado não é alarme (pode ser só um dia fraco), mas também não pode ser dito "dentro".
    const below = radar.pace.status === "normal" && radar.pace.ratio !== null && radar.pace.ratio < PACE_BELOW_RATIO;
    const status: TvStatus = radar.pace.status === "critical" ? "critical" : radar.pace.status === "attention" ? "attention" : below ? "neutral" : "ok";
    const verdict = radar.pace.status !== "normal" ? "acima do esperado" : below ? "abaixo do esperado" : "dentro do esperado";
    lines.push({ key: "pace", status, text: `Hoje: ${protocols(radar.pace.observed_today)}, ${verdict} (${expected})` });
  }

  // 2) rajada: mostra só a janela mais forte, para não repetir a mesma rajada em 1 h, 2 h e 6 h
  if (radar.bursts === null) {
    lines.push({ key: "burst", status: "neutral", text: "Rajada de protocolos: indisponível" });
  } else if (noHistory || radar.bursts.every((window) => window.basis === "none")) {
    lines.push({ key: "burst", status: "neutral", text: "Rajada de protocolos: ainda sem histórico para comparar" });
  } else {
    const active = radar.bursts.filter((window) => window.active).sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0));
    if (active.length === 0) {
      lines.push({ key: "burst", status: "ok", text: "Sem rajada de protocolos operacionais hoje" });
    } else {
      const strongest = active[0];
      const expected = strongest.expected === null ? "" : ` (esperado ${decimal(strongest.expected)})`;
      lines.push({ key: "burst", status: "critical", text: `Rajada na última ${strongest.window}: ${protocols(strongest.observed)}${expected}` });
    }
  }

  // 3) cidades
  if (radar.cities_at_risk === null) {
    lines.push({ key: "cities", status: "neutral", text: "Cidades fora do esperado: indisponível" });
  } else if (noHistory) {
    lines.push({ key: "cities", status: "neutral", text: "Cidades: ainda sem histórico para comparar" });
  } else if (radar.cities_at_risk.length === 0) {
    lines.push({ key: "cities", status: "ok", text: "Nenhuma cidade fora do esperado hoje" });
  } else {
    for (const city of radar.cities_at_risk) {
      lines.push({ key: `city-${city.city}`, status: "critical", text: `${city.city}: ${formatCount(city.today_count)} hoje (esperado ${decimal(city.expected)})` });
    }
  }
  return lines;
}

function overallStatus(lines: RadarLine[]): TvStatus {
  if (lines.some((line) => line.status === "critical")) return "critical";
  if (lines.some((line) => line.status === "attention")) return "attention";
  return "neutral";
}

export function TvRadarPanel({ radar, theme }: { radar: SupportTvRadar; theme: TvTheme }) {
  const t = TV_CLASSES[theme];
  const lines = radarLines(radar);
  return (
    <TvCard theme={theme} eyebrow="Radar de incidente — operacional" status={overallStatus(lines)}>
      <ul className="flex flex-1 flex-col justify-between gap-2">
        {lines.map((line) => (
          <li key={line.key} className="flex items-start gap-3">
            <span className={cn("mt-2 h-3 w-3 shrink-0 rounded-full", t.status[line.status].dot, line.status === "critical" && "tv-live")} aria-hidden="true" />
            <span className={cn("text-lg leading-snug", line.status === "critical" ? "font-semibold" : "font-normal", t.title)}>{line.text}</span>
          </li>
        ))}
      </ul>
    </TvCard>
  );
}

// Suporte interno N1 hoje, em uma linha no cabeçalho (o espaço do cartão foi para a presença).
export function TvN1Chip({ data, theme }: { data: SupportTvN1 | null; theme: TvTheme }) {
  const t = TV_CLASSES[theme];
  return (
    <span className={cn("inline-flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-1.5 text-base font-medium", t.chip)} title="Protocolos do Suporte interno N1 abertos hoje (IXC)">
      N1 hoje:
      {data ? (
        <>
          <span className={cn("font-bold tabular-nums", t.value)}>{formatCount(data.total)}</span>
          <span className={cn("hidden md:inline", t.muted)}>
            ({formatCount(data.operational)} operacional · {formatCount(data.financial)} financeiro)
          </span>
        </>
      ) : (
        <span className={t.muted}>indisponível</span>
      )}
    </span>
  );
}
