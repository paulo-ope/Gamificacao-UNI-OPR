// Formatação compartilhada das telas de Ocorrências (assunto 211 do IXC).
//
// Os horários do IXC chegam como relógio local do servidor gravado como UTC (convenção do módulo
// Suporte), então são exibidos SEM conversão de fuso (`timeZone: "UTC"`): o que a tela mostra é o
// mesmo horário que o time vê no IXC.

export const NO_REGIONAL = "NAO IDENTIFICADO";

export function number(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function percent(value: number | null | undefined) {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}%`;
}

export function regionalLabel(value: string | null | undefined) {
  if (!value) return "—";
  return value === NO_REGIONAL ? "Não identificada" : value.replace(/^UNI - /, "");
}

export function localIso(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function daysAgoIso(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return localIso(date);
}

export function ixcDateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "UTC" }).format(new Date(value));
}

export function ixcTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).format(new Date(value));
}

export function dayLabel(iso: string) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

/** 95 -> "1h35min"; 2900 -> "2d 0h"; null -> "—". */
export function durationLabel(minutes: number | null | undefined) {
  if (minutes == null) return "—";
  const total = Math.round(minutes);
  if (total < 1) return "< 1min";
  if (total < 60) return `${total}min`;
  const hours = Math.floor(total / 60);
  if (hours < 24) return `${hours}h${String(total % 60).padStart(2, "0")}min`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
