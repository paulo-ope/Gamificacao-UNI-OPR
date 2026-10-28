import type { Tone } from "@/lib/tones";
import type { SupportPlanHealth, SupportPlanItem, SupportPlanKind, SupportPlanPriority, SupportPlanStatus } from "@/lib/types";

// Rótulos, tons e formatação da aba Especialista/Analista. Só apresentação: atraso, progresso e
// transições de status vivem no backend (`planning_service.py`).

export const STATUS_LABEL: Record<SupportPlanStatus, string> = {
  planned: "Planejado",
  in_progress: "Em andamento",
  blocked: "Bloqueado",
  done: "Concluído",
  canceled: "Cancelado",
};

export const STATUS_TONE: Record<SupportPlanStatus, Tone> = {
  planned: "slate",
  in_progress: "blue",
  blocked: "red",
  done: "emerald",
  canceled: "slate",
};

export const STATUS_ORDER: SupportPlanStatus[] = ["planned", "in_progress", "blocked", "done", "canceled"];
export const BOARD_COLUMNS: SupportPlanStatus[] = ["planned", "in_progress", "blocked", "done"];

export const KIND_LABEL: Record<SupportPlanKind, string> = { project: "Projeto", task: "Tarefa", key_result: "Resultado-chave", action: "Ação" };

// Situação dada no check-in de uma ação.
export const HEALTH_LABEL: Record<SupportPlanHealth, string> = { on_track: "No prazo", at_risk: "Em risco", off_track: "Atrasada" };
export const HEALTH_TONE: Record<SupportPlanHealth, Tone> = { on_track: "emerald", at_risk: "amber", off_track: "red" };
export const HEALTH_ORDER: SupportPlanHealth[] = ["on_track", "at_risk", "off_track"];

/** O que há dentro de cada tipo, para os títulos e botões do painel do item. */
export const CHILD_LABEL: Partial<Record<SupportPlanKind, { plural: string; new: string; kind: SupportPlanKind }>> = {
  project: { plural: "Resultados-chave", new: "Novo resultado-chave", kind: "key_result" },
  key_result: { plural: "Ações", new: "Nova ação", kind: "action" },
};

/** Avanço do item: o calculado pelo backend (resultado-chave, ação, projeto com resultados-chave) ou, sem ele, tarefas concluídas. */
export function itemProgress(item: Pick<SupportPlanItem, "progress" | "tasks_total" | "tasks_done">): number | null {
  return item.progress ?? progressPercent(item);
}

export const PRIORITY_LABEL: Record<SupportPlanPriority, string> = { low: "Baixa", medium: "Média", high: "Alta" };
export const PRIORITY_TONE: Record<SupportPlanPriority, Tone> = { low: "slate", medium: "amber", high: "red" };

/** Datas do backend chegam como AAAA-MM-DD; formatar sem `new Date` evita deslocar um dia pelo fuso. */
export function dateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : "—";
}

export function dateTimeLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Percentual de tarefas concluídas de um projeto, ou null quando não há tarefa na conta. */
export function progressPercent(item: Pick<SupportPlanItem, "tasks_total" | "tasks_done">): number | null {
  if (!item.tasks_total) return null;
  return Math.round((item.tasks_done / item.tasks_total) * 100);
}

export function assigneesLabel(item: Pick<SupportPlanItem, "assignees">): string {
  return item.assignees.length ? item.assignees.map((person) => person.name).join(" e ") : "Sem responsável";
}

/** Texto do prazo para o cartão: data e, se estourou, a marca de atraso. */
export function dueLabel(item: Pick<SupportPlanItem, "due_date" | "overdue">): string {
  if (!item.due_date) return "Sem prazo";
  return item.overdue ? `${dateLabel(item.due_date)} · atrasado` : dateLabel(item.due_date);
}

export function isClosed(status: SupportPlanStatus): boolean {
  return status === "done" || status === "canceled";
}

// ---------------------------------------------------------------------------
// Apresentação do quadro: barra de prazo, iniciais e cores dos responsáveis
// ---------------------------------------------------------------------------

export type DeadlineTone = "ok" | "warn" | "late" | "done" | "none";
export type Deadline = { tone: DeadlineTone; percent: number; detail: string; badge: string };

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

function plural(value: number, one: string, many: string) {
  return `${value} ${value === 1 ? one : many}`;
}

/** "3 dias 4 horas" ou, abaixo de um dia, "5 horas 20 min". */
export function durationText(ms: number): string {
  const safe = Math.max(0, ms);
  const days = Math.floor(safe / DAY_MS);
  const hours = Math.floor((safe % DAY_MS) / HOUR_MS);
  if (days > 0) return hours ? `${plural(days, "dia", "dias")} ${plural(hours, "hora", "horas")}` : plural(days, "dia", "dias");
  const minutes = Math.floor((safe % HOUR_MS) / MINUTE_MS);
  return hours ? `${plural(hours, "hora", "horas")} ${minutes} min` : `${minutes} min`;
}

/**
 * Situação do prazo para a barra do cartão. O atraso vem do backend (`overdue`); aqui só se calcula
 * quanto do tempo entre o lançamento e o prazo já passou e o texto de "restante" ou "atraso".
 * O prazo vale até o fim do dia informado.
 */
export function deadlineInfo(
  item: Pick<SupportPlanItem, "status" | "due_date" | "overdue" | "created_at" | "completed_at">,
  now: Date = new Date(),
): Deadline {
  if (item.status === "done") {
    return { tone: "done", percent: 100, detail: item.completed_at ? `Concluído em ${dateLabel(item.completed_at)}` : "Concluído", badge: "Concluído" };
  }
  if (item.status === "canceled") return { tone: "none", percent: 0, detail: "Cancelado", badge: "" };
  if (!item.due_date) return { tone: "none", percent: 0, detail: "Sem prazo", badge: "" };
  const due = new Date(`${item.due_date.slice(0, 10)}T23:59:59`);
  if (Number.isNaN(due.getTime())) return { tone: "none", percent: 0, detail: "Sem prazo", badge: "" };
  if (item.overdue) return { tone: "late", percent: 100, detail: `Atraso: ${durationText(now.getTime() - due.getTime())}`, badge: "Atrasado" };
  const created = new Date(item.created_at).getTime();
  const start = Number.isNaN(created) ? now.getTime() : created;
  const total = Math.max(due.getTime() - start, HOUR_MS);
  const percent = Math.min(100, Math.max(0, Math.round(((now.getTime() - start) / total) * 100)));
  const tone: DeadlineTone = percent >= 80 ? "warn" : "ok";
  return { tone, percent, detail: `Restante: ${durationText(due.getTime() - now.getTime())}`, badge: tone === "warn" ? "Atenção" : "Em dia" };
}

/** Duas iniciais do nome (primeiro e último nome). */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? "") : "";
  return `${first}${last}`.toUpperCase();
}

// Cores da marca UNI, já com a cor do texto (o turquesa pede texto escuro para ter contraste).
const AVATAR_COLORS = [
  "bg-uni-royal text-white",
  "bg-uni-midnight text-white",
  "bg-uni-turquoise text-uni-ink",
  "bg-uni-impact text-white",
  "bg-uni-ink text-white",
  "bg-uni-electric text-white",
];

/** Cor fixa por pessoa (pelo id), para a mesma pessoa ter sempre a mesma cor da marca. */
export function avatarColor(id: number): string {
  return AVATAR_COLORS[Math.abs(id) % AVATAR_COLORS.length];
}
