// Helpers puros de formatação/rótulo compartilhados entre os componentes de casos de gestão -
// extraído de management-cases-panel.tsx em 2026-08-21 (reorganização do módulo, ver
// generic-riding-petal.md) para reduzir o tamanho do arquivo principal.

export const CASE_STATUS_LABELS: Record<string, string> = {
  pending: "Aguardando justificativa",
  justified: "Justificado",
  in_progress: "Em andamento",
  resolved: "Resolvido",
  rejected: "Rejeitado",
  overdue: "Em atraso",
};

export const SEVERITY_LABELS: Record<string, string> = { high: "Alta", medium: "Média", low: "Baixa" };

export const CASE_TYPE_LABELS: Record<string, string> = {
  productivity_below_target: "Produtividade abaixo da meta",
  daily_performance_below_target: "Dia abaixo da meta",
};

export function severityTone(severity: string) {
  if (severity === "high") return "border-red-200 bg-red-50 text-red-700";
  if (severity === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-100 text-slate-600";
}

export function statusTone(status: string) {
  if (status === "resolved") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "rejected") return "border-slate-200 bg-slate-100 text-slate-600";
  if (status === "justified") return "border-blue-200 bg-blue-50 text-blue-700";
  if (status === "in_progress") return "border-violet-200 bg-violet-50 text-violet-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

export function formatDate(value: string | null) {
  if (!value) return "—";
  // `reference_date`/`due_date`/`last_run_date` são datas puras (YYYY-MM-DD, sem hora nem fuso) -
  // achado real de 2026-08-22: `new Date("2026-08-06")` vira meia-noite UTC, e reformatar esse
  // instante com `timeZone: "America/Porto_Velho"` (UTC-4) empurrava a data um dia pra trás
  // (mostrava 05/08 pra um caso de 06/08). Formata os componentes Y-M-D direto, sem passar por
  // `Date`/fuso nenhum - diferente de `formatDateTime`, que lida com timestamps de verdade.
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return "—";
  return `${day}/${month}/${year}`;
}

export function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Porto_Velho" });
}

export function decimal(value: number | null) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value);
}

export function previousMonth() {
  // A competência padrão é o mês anterior: cobrar produtividade do mês corrente, ainda em curso,
  // geraria caso em cima de dado incompleto.
  const now = new Date();
  const reference = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return { year: reference.getFullYear(), month: reference.getMonth() + 1 };
}
