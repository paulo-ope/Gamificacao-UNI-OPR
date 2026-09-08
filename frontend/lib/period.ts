/**
 * Aritmética de janelas de período em datas puras (`YYYY-MM-DD`), sem fuso.
 *
 * Tudo aqui trabalha em UTC de propósito: uma data pura convertida para `Date` local e de volta
 * pode perder ou ganhar um dia dependendo do fuso do navegador - o mesmo cuidado de
 * `formatIsoDate` em `lib/format.ts`.
 */

function parseIso(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

function toIso(utcMs: number) {
  return new Date(utcMs).toISOString().slice(0, 10);
}

const DAY_MS = 86_400_000;

/** Quantidade de dias de uma janela inclusiva (`from` e `to` contam). */
export function windowLengthDays(dateFrom: string, dateTo: string) {
  return Math.round((parseIso(dateTo) - parseIso(dateFrom)) / DAY_MS) + 1;
}

/**
 * A janela imediatamente anterior, do mesmo tamanho (decisão do usuário em 2026-09-03: "últimos
 * 30 dias" compara com os 30 dias antes deles, não com o mês passado).
 *
 * `allowedFrom` é o início do ano operacional que o backend aceita
 * (`validate_operations_period`). Se a janela anterior começa antes dele, ela é cortada; se
 * fica inteira antes dele, não existe comparação possível e a função devolve `null` - melhor
 * "sem comparação" do que um 422 ou uma janela de tamanho diferente disfarçada de igual.
 */
export function previousWindow(
  dateFrom: string,
  dateTo: string,
  allowedFrom?: string | null,
): { date_from: string; date_to: string; truncated: boolean } | null {
  const length = windowLengthDays(dateFrom, dateTo);
  if (length <= 0) return null;
  const prevTo = parseIso(dateFrom) - DAY_MS;
  let prevFrom = prevTo - (length - 1) * DAY_MS;
  let truncated = false;
  if (allowedFrom) {
    const floor = parseIso(allowedFrom);
    if (prevTo < floor) return null;
    if (prevFrom < floor) {
      prevFrom = floor;
      truncated = true;
    }
  }
  return { date_from: toIso(prevFrom), date_to: toIso(prevTo), truncated };
}

/**
 * Variação percentual de `current` sobre `previous`, com uma casa. `null` quando não há base
 * de comparação (anterior nulo ou zero) - "de 0 para 12" não é "+∞%", é "sem base".
 */
export function percentChange(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current === null || current === undefined || previous === null || previous === undefined) return null;
  if (previous === 0) return null;
  return Math.round(((current - previous) / Math.abs(previous)) * 1000) / 10;
}
