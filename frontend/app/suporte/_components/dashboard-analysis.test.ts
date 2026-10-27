import { describe, expect, it } from "vitest";

import type { SupportMacroCard, SupportMacroDashboard } from "@/lib/types";

import { buildDashboardAnalysis } from "./dashboard-analysis";

const card = (over: Partial<SupportMacroCard>): SupportMacroCard => ({
  key: "tmr", label: "TMR", unit: "seconds", value: 155, previous: 150, change: 5, target: 120, direction: "max", status: "critical",
  coverage: null, source: "opa", note: null, ...over,
});

const dashboard = (over: Partial<SupportMacroDashboard> = {}): SupportMacroDashboard =>
  ({
    date_from: "2026-10-18", date_to: "2026-10-24", previous_date_from: null, previous_date_to: null,
    cards: [
      card({}),
      card({ key: "tma", value: 1800, target: 3600 }),
      card({ key: "csat", unit: "score", value: 4.42, target: 4.5, direction: "min" }),
      card({ key: "resolutivity", unit: "percent", value: 74, target: 80, direction: "min" }),
    ],
    n2: {}, previous_n2: null, n2_collaborators: { rows: [] }, previous_daily: [],
    daily: [
      { day: "2026-10-19", opa_total: 210, performed: 90, solved: 60, field: 30, rating: 4.7, tmr_seconds: 100, tma_seconds: 1800 },
      { day: "2026-10-20", opa_total: 150, performed: 80, solved: 55, field: 25, rating: 4.3, tmr_seconds: 150, tma_seconds: 3800 },
    ],
    weekly: {
      month: "2026-10", resolutivity_target: 80,
      buckets: [{ key: "week_1", label: "1ª semana", date_from: "2026-10-01", date_to: "2026-10-03", performed: 200, field: 50, solved: 150, resolutivity: 75 }],
    },
    weeks_opa: [
      { key: "week_1", label: "1ª semana", date_from: "2026-10-01", date_to: "2026-10-03", future: false, partial: false, total: 500, tmr_seconds: 110, tma_seconds: 3000, rating: 4.6 },
      { key: "week_5", label: "5ª semana", date_from: "2026-10-25", date_to: "2026-10-31", future: true, partial: false, total: null, tmr_seconds: null, tma_seconds: null, rating: null },
    ],
    peak_day: {
      day: "2026-10-19", total: 210, average: 150, percent_above: 40,
      reasons: [{ reason: "Sem conexão", count: 45, usual_per_day: 20 }, { reason: "Lentidão", count: 30, usual_per_day: 28 }],
    },
    month_projection: {
      month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 24, remaining_days: 7, remaining_from: "2026-10-25",
      items: [
        { key: "tmr", kind: "mean", month_value: 130, pace_value: 134, target: 120, direction: "max", count: 400, required_value: 94, pace_meets_target: false, status: "reachable" },
        { key: "opa_total", kind: "sum", month_value: 2400, pace_value: 3100, target: null, direction: null, count: 2400, required_value: null, pace_meets_target: null, status: "no_target" },
        { key: "csat", kind: "mean", month_value: 4, pace_value: 4.05, target: 4.5, direction: "min", count: 1000, required_value: null, pace_meets_target: false, status: "unreachable" },
      ],
    },
    ...over,
  }) as unknown as SupportMacroDashboard;

describe("buildDashboardAnalysis", () => {
  it("monta o dia a dia com cor pela meta e marca o dia de pico", () => {
    const { days } = buildDashboardAnalysis(dashboard());

    expect(days).toHaveLength(2);
    expect(days[0].label).toMatch(/^19\/10 /);
    expect(days[0].peak).toBe(true);
    expect(days[0].cells.map((cell) => cell.text)).toEqual(["210", "90", "30", "00:01:40", "00:30:00", "4,70"]);
    expect(days[0].cells.map((cell) => cell.tone)).toEqual(["none", "none", "none", "ok", "ok", "ok"]);
    // TMR 150 s contra meta 120 s (25% acima) é vermelho; TMA 3.800 s contra 3.600 s (5,6% acima) é amarelo; nota 4,3 contra 4,5 é amarela.
    expect(days[1].peak).toBe(false);
    expect(days[1].cells.map((cell) => cell.tone)).toEqual(["none", "none", "none", "bad", "warn", "warn"]);
  });

  it("aponta o dia de maior aumento e marca os motivos que puxaram", () => {
    const { peak } = buildDashboardAnalysis(dashboard());

    expect(peak.headline).toMatch(/^Dia 19\/10 \(.+\): 210 atendimentos no OPA, 40% acima da média dos outros dias \(150 por dia\)\.$/);
    expect(peak.reasons).toEqual([
      { reason: "Sem conexão", count: 45, usual: 20, heavy: true },
      { reason: "Lentidão", count: 30, usual: 28, heavy: false },
    ]);
    expect(peak.note).toBeNull();
  });

  it("junta OPA e IXC por semana e deixa a semana futura vazia", () => {
    const { weeks } = buildDashboardAnalysis(dashboard());

    expect(weeks[0].range).toBe("01/10 a 03/10");
    expect(weeks[0].cells.map((cell) => cell.text)).toEqual(["500", "00:01:50", "00:50:00", "4,60", "200", "50", "75,00%"]);
    expect(weeks[0].cells.map((cell) => cell.tone)).toEqual(["none", "ok", "ok", "ok", "none", "none", "warn"]);
    expect(weeks[1]).toMatchObject({ muted: true, note: "ainda não começou" });
    expect(weeks[1].cells.every((cell) => cell.text === "-")).toBe(true);
  });

  it("projeta o fechamento do mês e diz quanto o resto do mês precisa fechar", () => {
    const { projection } = buildDashboardAnalysis(dashboard());

    expect(projection?.range).toBe("Resto do mês: 25/10 a 31/10 (7 dias), no ritmo do período selecionado");
    const byName = Object.fromEntries((projection?.rows ?? []).map((row) => [row.name, row]));
    expect(byName.TMR).toEqual({ name: "TMR", month: "00:02:10", pace: "00:02:14", target: "≤ 00:02:00", required: "00:01:34", verdict: "Precisa melhorar o ritmo", tone: "warn" });
    expect(byName["Atendimentos OPA"]).toMatchObject({ month: "2.400", pace: "3.100", required: "-", verdict: "Sem meta definida" });
    expect(byName["Avaliação (CSAT)"]).toMatchObject({ required: "-", verdict: "Não dá mais para fechar o mês na meta", tone: "bad" });
  });

  it("trata mês encerrado e ausência de projeção", () => {
    const closed = buildDashboardAnalysis(
      dashboard({
        month_projection: {
          month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 31, remaining_days: 0, remaining_from: null,
          items: [{ key: "tmr", kind: "mean", month_value: 110, pace_value: 110, target: 120, direction: "max", count: 500, required_value: null, pace_meets_target: true, status: "closed" }],
        },
      }),
    );
    expect(closed.projection?.range).toBe("Mês de 01/10 a 31/10, já encerrado");
    expect(closed.projection?.rows[0]).toMatchObject({ verdict: "Mês fechou na meta", tone: "ok" });

    const none = buildDashboardAnalysis(dashboard({ peak_day: null, month_projection: null, weeks_opa: [] }));
    expect(none.projection).toBeNull();
    expect(none.peak).toEqual({ headline: "Nenhum dia com aumento relevante de atendimentos no período.", reasons: [], note: null });
    expect(none.weeks).toEqual([]);
  });
});
