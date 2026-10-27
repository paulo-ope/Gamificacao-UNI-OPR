import { describe, expect, it } from "vitest";

import type { SupportMacroCard, SupportMacroDashboard } from "@/lib/types";

import { buildDashboardAnalysis, durationWords } from "./dashboard-analysis";

const card = (over: Partial<SupportMacroCard>): SupportMacroCard => ({
  key: "tmr", label: "TMR", unit: "seconds", value: 155, previous: 150, change: 5, target: 120, direction: "max", status: "critical",
  coverage: null, source: "opa", note: null, ...over,
});

const dashboard = (over: Partial<SupportMacroDashboard> = {}): SupportMacroDashboard =>
  ({
    date_from: "2026-10-18", date_to: "2026-10-24", previous_date_from: null, previous_date_to: null,
    cards: [card({}), card({ key: "tma", unit: "seconds", value: 1800, target: 3600, status: "ok" }), card({ key: "csat", unit: "score", value: 4.42, target: 4.5, direction: "min", status: "attention" })],
    n2: {}, previous_n2: null, n2_collaborators: { rows: [] }, daily: [], previous_daily: [], weekly: { month: "2026-10", resolutivity_target: 80, buckets: [] },
    peak_day: {
      day: "2026-10-20", total: 210, average: 150, percent_above: 40,
      reasons: [{ reason: "Sem conexão", count: 45, usual_per_day: 20 }, { reason: "Lentidão", count: 30, usual_per_day: 28 }],
    },
    month_projection: {
      month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 24, remaining_days: 7, remaining_from: "2026-10-25",
      items: [
        { key: "tmr", month_value: 130, target: 120, count: 400, required_value: 94, status: "reachable" },
        { key: "tma", month_value: 1800, target: 3600, count: 400, required_value: null, status: "no_data" },
      ],
    },
    ...over,
  }) as unknown as SupportMacroDashboard;

describe("durationWords", () => {
  it("escreve segundos e minutos", () => {
    expect(durationWords(35)).toBe("35 segundos");
    expect(durationWords(1)).toBe("1 segundo");
    expect(durationWords(80)).toBe("1 min 20 s");
    expect(durationWords(1500)).toBe("25 min");
  });
});

describe("buildDashboardAnalysis", () => {
  it("aponta o dia de maior aumento e marca os motivos que puxaram", () => {
    const { peak } = buildDashboardAnalysis(dashboard());

    expect(peak.headline).toBe("Dia 20/10: 210 atendimentos no OPA, 40% acima da média dos outros dias (150 por dia).");
    expect(peak.reasons).toEqual([
      { reason: "Sem conexão", count: 45, usual: 20, heavy: true },
      { reason: "Lentidão", count: 30, usual: 28, heavy: false },
    ]);
    expect(peak.note).toBeNull();
  });

  it("diz quanto falta para a meta da semana, ou que já está dentro", () => {
    const { goals } = buildDashboardAnalysis(dashboard());

    expect(goals).toEqual([
      { name: "TMR", current: "00:02:35", target: "≤ 00:02:00", action: "Cair 35 segundos", tone: "bad" },
      { name: "TMA", current: "00:30:00", target: "≤ 01:00:00", action: "Dentro da meta: manter", tone: "ok" },
      { name: "Avaliação (CSAT)", current: "4,42", target: "≥ 4,50", action: "Subir 0,08 pontos", tone: "warn" },
    ]);
  });

  it("projeta quanto o resto do mês precisa fechar para a média do mês bater a meta", () => {
    const { month } = buildDashboardAnalysis(dashboard());

    expect(month?.range).toBe("Resto do mês: 25/10 a 31/10 (7 dias)");
    expect(month?.rows[0]).toEqual({ name: "TMR", monthValue: "00:02:10", target: "≤ 00:02:00", verdict: "Precisa fechar o resto do mês em 00:01:34", tone: "warn" });
    expect(month?.rows[1].verdict).toBe("Sem dado suficiente no mês");
  });

  it("trata mês inalcançável e mês já encerrado", () => {
    const unreachable = buildDashboardAnalysis(
      dashboard({ month_projection: { month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 24, remaining_days: 7, remaining_from: "2026-10-25", items: [{ key: "tmr", month_value: 180, target: 120, count: 400, required_value: null, status: "unreachable" }] } }),
    );
    expect(unreachable.month?.rows[0]).toMatchObject({ verdict: "Não dá mais para fechar o mês na meta", tone: "bad" });

    const closed = buildDashboardAnalysis(
      dashboard({ month_projection: { month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 31, remaining_days: 0, remaining_from: null, items: [{ key: "tmr", month_value: 110, target: 120, count: 500, required_value: null, status: "closed" }] } }),
    );
    expect(closed.month?.range).toBe("Mês de 01/10 a 31/10, já encerrado");
    expect(closed.month?.rows[0]).toMatchObject({ verdict: "Mês fechou dentro da meta", tone: "ok" });
  });

  it("avisa quando não houve aumento relevante e não avalia dado parcial", () => {
    const result = buildDashboardAnalysis(dashboard({ peak_day: null, month_projection: null, cards: [card({ status: "partial" })] }));

    expect(result.peak).toEqual({ headline: "Nenhum dia com aumento relevante de atendimentos no período.", reasons: [], note: null });
    expect(result.goals[0].action).toBe("Dados incompletos");
    expect(result.month).toBeNull();
  });
});
