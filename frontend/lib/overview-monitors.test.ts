import { describe, expect, it } from "vitest";

import type { CockpitMonitorHealth } from "@/lib/intelligence-cockpit-api";
import { formatAgo, monitorTone } from "@/lib/overview-monitors";

function monitor(overrides: Partial<CockpitMonitorHealth>): CockpitMonitorHealth {
  return {
    monitor_key: "m",
    name: "Monitor",
    enabled: true,
    last_run_at: "2026-10-09T12:00:00Z",
    last_run_status: "success",
    last_success_at: "2026-10-09T12:00:00Z",
    consecutive_failures: 0,
    ...overrides,
  };
}

describe("monitorTone", () => {
  it("saudável quando roda com sucesso e sem falhas", () => {
    expect(monitorTone(monitor({}))).toBe("ok");
  });
  it("cinza quando desligado ou nunca executou", () => {
    expect(monitorTone(monitor({ enabled: false }))).toBe("disabled");
    expect(monitorTone(monitor({ last_run_at: null }))).toBe("never");
  });
  it("reconhece o status COMPLETED que o backend usa como sucesso", () => {
    expect(monitorTone(monitor({ last_run_status: "COMPLETED" }))).toBe("ok");
    // Mesmo sem conhecer o nome do status: a última execução é a última com sucesso.
    expect(monitorTone(monitor({ last_run_status: "QUALQUER_COISA" }))).toBe("ok");
  });
  it("vermelho com falhas seguidas ou última execução sem sucesso", () => {
    expect(monitorTone(monitor({ consecutive_failures: 2 }))).toBe("failing");
    expect(
      monitorTone(monitor({ last_run_status: "FAILED", last_success_at: "2026-10-09T11:00:00Z" })),
    ).toBe("failing");
  });
});

describe("formatAgo", () => {
  const now = new Date("2026-10-09T12:00:00Z");
  it("formata minutos, horas e dias", () => {
    expect(formatAgo("2026-10-09T11:58:00Z", now)).toBe("há 2 min");
    expect(formatAgo("2026-10-09T09:00:00Z", now)).toBe("há 3 h");
    expect(formatAgo("2026-10-05T12:00:00Z", now)).toBe("há 4 d");
  });
  it("trata agora, futuro, vazio e data inválida", () => {
    expect(formatAgo("2026-10-09T12:00:10Z", now)).toBe("agora");
    expect(formatAgo(null, now)).toBe("nunca");
    expect(formatAgo("lixo", now)).toBe("—");
  });
});
