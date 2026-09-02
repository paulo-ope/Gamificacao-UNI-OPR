// Helpers de formatação do módulo de Agendamento - extraídos de app/agendamento/page.tsx na
// reformulação do cockpit diário (calendário mensal), para os componentes de
// components/scheduling/* não duplicarem a mesma lógica.

export function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

export function minutesLabel(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (value < 60) return `${Math.round(value)} min`;
  if (value < 60 * 24) return `${(value / 60).toFixed(1).replace(".", ",")} h`;
  return `${(value / (60 * 24)).toFixed(1).replace(".", ",")} dias`;
}

export function hoursLabel(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (value < 48) return `${value.toFixed(1).replace(".", ",")} h`;
  return `${(value / 24).toFixed(1).replace(".", ",")} dias`;
}

export function rescheduleOriginLabel(origins: ("backoffice" | "campo")[] | undefined) {
  if (!origins || !origins.length) return "—";
  const hasBackoffice = origins.includes("backoffice");
  const hasCampo = origins.includes("campo");
  if (hasBackoffice && hasCampo) return "Backoffice e campo";
  if (hasBackoffice) return "Backoffice";
  if (hasCampo) return "Campo";
  return "—";
}

// A operação inteira acontece em Rondônia - fixar o fuso na formatação garante que todo mundo vê o
// mesmo horário, não importa onde o navegador de quem está olhando a tela está fisicamente. Sem
// isso, `toLocaleString` usa o fuso do DISPOSITIVO de quem acessa, não o da operação (achado real,
// 2026-07-29: "Aberta em" mostrava 4h a menos do horário certo de Rondônia).
export function formatPortoVelho(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "America/Porto_Velho",
  }).format(new Date(iso));
}

// Só o horário (sem a data) em Porto Velho - usado na fila do dia (a data já está no título do
// drawer, repeti-la em toda linha só teria peso visual sem informação nova).
export function formatTimePortoVelho(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeStyle: "short",
    timeZone: "America/Porto_Velho",
  }).format(new Date(iso));
}

export function number(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

const MONTH_LABELS = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export type MonthKey = { year: number; month: number }; // month: 1-12

export function monthLabel({ year, month }: MonthKey) {
  return `${MONTH_LABELS[month - 1]} de ${year}`;
}

export function monthBounds({ year, month }: MonthKey): { date_from: string; date_to: string } {
  const lastDay = new Date(year, month, 0).getDate();
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    date_from: `${year}-${pad(month)}-01`,
    date_to: `${year}-${pad(month)}-${pad(lastDay)}`,
  };
}

export function shiftMonth({ year, month }: MonthKey, delta: number): MonthKey {
  const total = year * 12 + (month - 1) + delta;
  return { year: Math.floor(total / 12), month: (total % 12) + 1 };
}

export function currentMonthKey(): MonthKey {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export function isSameMonth(a: MonthKey, b: MonthKey) {
  return a.year === b.year && a.month === b.month;
}

export const DRILL_PAGE_SIZE = 50;

// Período independente do calendário mensal do Painel (pedido do usuário 2026-08-31: "só consigo
// ver o de hoje, quero ver um período maior") - usado pelas abas Rankings e Desempenho, que
// precisam de uma janela mais ampla que o mês em navegação. Últimos 30 dias por padrão.
export function defaultPeriod(): { date_from: string; date_to: string } {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - 29);
  return { date_from: isoDate(from), date_to: isoDate(today) };
}
