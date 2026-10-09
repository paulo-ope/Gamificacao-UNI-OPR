import type { CockpitMonitorHealth } from "@/lib/intelligence-cockpit-api";

export type MonitorTone = "ok" | "failing" | "disabled" | "never";

const SUCCESS_STATUSES = new Set(["completed", "success", "succeeded", "ok"]);

/**
 * Cor do monitor: desligado (cinza), nunca rodou (cinza), com falhas seguidas ou última execução
 * que não foi sucesso (vermelho) ou saudável (verde). Sem limiar de "atrasado" inventado aqui - o
 * intervalo de cada monitor é do backend, e chutar um corte faria a tela divergir do cockpit.
 */
export function monitorTone(monitor: CockpitMonitorHealth): MonitorTone {
  if (!monitor.enabled) return "disabled";
  if (!monitor.last_run_at) return "never";
  if (monitor.consecutive_failures > 0) return "failing";
  // A última execução foi a última com sucesso: não depende do nome do status (o backend usa
  // "COMPLETED"), e é o que o próprio payload do cockpit expõe como `last_success_at`.
  if (monitor.last_success_at && monitor.last_success_at === monitor.last_run_at) return "ok";
  const status = (monitor.last_run_status ?? "").toLowerCase();
  return SUCCESS_STATUSES.has(status) ? "ok" : "failing";
}

/** "há 2 min", "há 3 h", "há 4 d" - arredonda para baixo e nunca mostra tempo negativo (relógios desalinhados). */
export function formatAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "nunca";
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "—";
  const minutes = Math.max(0, Math.floor((now.getTime() - time) / 60_000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  return `há ${Math.floor(hours / 24)} d`;
}
