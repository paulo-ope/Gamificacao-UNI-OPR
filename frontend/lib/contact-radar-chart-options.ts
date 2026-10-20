import type { SupportContactRadarPoint } from "@/lib/types";

// Rótulos de tempo do Radar de Contatos (mini-gráficos dos cartões), sempre no horário de Porto Velho.

const TIMEZONE = "America/Porto_Velho";

function parts(iso: string) {
  const formatter = new Intl.DateTimeFormat("pt-BR", { timeZone: TIMEZONE, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const found = Object.fromEntries(formatter.formatToParts(new Date(iso)).map((part) => [part.type, part.value]));
  return { day: found.day, month: found.month, hour: found.hour, minute: found.minute };
}

/** Rótulo de um intervalo da série, no horário de Porto Velho: "14:35" (curto), "20/10 14h" ou "20/10". */
export function bucketLabel(iso: string, bucketMinutes: number, multiDay: boolean) {
  const { day, month, hour, minute } = parts(iso);
  if (bucketMinutes >= 1440) return `${day}/${month}`;
  if (bucketMinutes >= 60) return multiDay ? `${day}/${month} ${hour}h` : `${hour}h`;
  return multiDay ? `${day}/${month} ${hour}:${minute}` : `${hour}:${minute}`;
}

/** "20/10 14:35", no horário de Porto Velho. */
export function momentLabel(iso: string) {
  const { day, month, hour, minute } = parts(iso);
  return `${day}/${month} ${hour}:${minute}`;
}

export function seriesLabels(points: SupportContactRadarPoint[], bucketMinutes: number) {
  const first = points[0] ? parts(points[0].start) : null;
  const last = points.length ? parts(points[points.length - 1].start) : null;
  const multiDay = Boolean(first && last && (first.day !== last.day || first.month !== last.month));
  return points.map((point) => bucketLabel(point.start, bucketMinutes, multiDay));
}
