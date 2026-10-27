import { describe, expect, it } from "vitest";

import type { SupportMacroCard, SupportMacroDashboard, SupportMacroProjectionItem } from "@/lib/types";

import { buildDashboardAnalysis } from "./dashboard-analysis";

const card = (over: Partial<SupportMacroCard>): SupportMacroCard => ({
  key: "tmr", label: "TMR", unit: "seconds", value: 157, previous: 150, change: 7, target: 120, direction: "max", status: "critical",
  coverage: null, source: "opa", note: null, ...over,
});

const item = (over: Partial<SupportMacroProjectionItem>): SupportMacroProjectionItem => ({
  key: "tmr", kind: "mean", month_value: 130, pace_value: 134, target: 120, direction: "max", count: 400, required_value: 94,
  pace_meets_target: false, status: "reachable", ...over,
});

const dashboard = (over: Partial<SupportMacroDashboard> = {}): SupportMacroDashboard =>
  ({
    date_from: "2026-10-18", date_to: "2026-10-24", previous_date_from: null, previous_date_to: null,
    cards: [card({}), card({ key: "tma", value: 1800, target: 3600 }), card({ key: "csat", unit: "score", value: 4.34, target: 4.5, direction: "min" }), card({ key: "resolutivity", unit: "percent", value: 74, target: 80, direction: "min" })],
    n2: {}, previous_n2: null, n2_collaborators: { rows: [] }, daily: [], previous_daily: [], weekly: { month: "2026-10", resolutivity_target: 80, buckets: [] },
    peak_day: {
      day: "2026-10-20", total: 210, average: 150, percent_above: 40,
      reasons: [{ reason: "Sem conexão", count: 45, usual_per_day: 20 }, { reason: "Lentidão", count: 30, usual_per_day: 28 }],
    },
    month_projection: {
      month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 24, remaining_days: 7, remaining_from: "2026-10-25",
      items: [
        item({}),
        item({ key: "tma", month_value: 1800, pace_value: 1800, target: 3600, required_value: 5400, pace_meets_target: true }),
        item({ key: "csat", month_value: 4.2, pace_value: 4.25, target: 4.5, direction: "min", required_value: null, status: "unreachable" }),
        item({ key: "opa_total", kind: "sum", month_value: 2400, pace_value: 3100, target: null, direction: null, required_value: null, pace_meets_target: null, status: "no_target" }),
      ],
    },
    ...over,
  }) as unknown as SupportMacroDashboard;

describe("buildDashboardAnalysis", () => {
  it("aponta o dia de maior aumento e os motivos que puxaram", () => {
    const [peak] = buildDashboardAnalysis(dashboard());

    expect(peak.title).toBe("Dia de maior aumento");
    expect(peak.lines[0]).toBe("Dia 20/10 teve 210 atendimentos no OPA, 40% acima da média dos outros dias do período (150 por dia).");
    expect(peak.lines[1]).toContain("Sem conexão (45, habitual 20 por dia)");
    expect(peak.lines[2]).toBe("Puxaram o aumento: Sem conexão.");
  });

  it("diz quanto a próxima semana precisa fechar para o mês terminar na meta", () => {
    const month = buildDashboardAnalysis(dashboard())[1];

    expect(month.title).toBe("Para fechar o mês na meta");
    expect(month.lines).toEqual([
      "TMR: 00:02:37 na semana e 00:02:10 no mês (meta 00:02:00). Para fechar o mês na meta, a próxima semana (25/10 a 31/10) precisa fechar em 00:01:34. No ritmo atual o mês fecharia em 00:02:14.",
      "TMA: 00:30:00 na semana e 00:30:00 no mês (meta 01:00:00). Para fechar o mês na meta, a próxima semana (25/10 a 31/10) precisa fechar em 01:30:00. No ritmo atual já bate a meta.",
      "Avaliação (CSAT): 4,34 na semana e 4,20 no mês (meta 4,50). Não dá mais para fechar o mês na meta só com a próxima semana (25/10 a 31/10). No ritmo atual o mês fecharia em 4,25.",
    ]);
  });

  it("fala em resto do mês quando falta mais de uma semana", () => {
    const projection = { ...dashboard().month_projection!, remaining_days: 15, remaining_from: "2026-10-17" };

    const month = buildDashboardAnalysis(dashboard({ month_projection: projection }))[1];

    expect(month.lines[0]).toContain("o resto do mês (17/10 a 31/10) precisa fechar em 00:01:34");
  });

  it("mostra o resultado quando o mês já fechou e some sem projeção", () => {
    const closed = buildDashboardAnalysis(
      dashboard({
        month_projection: {
          month_from: "2026-10-01", month_to: "2026-10-31", elapsed_days: 31, remaining_days: 0, remaining_from: null,
          items: [item({ month_value: 110, pace_value: 110, required_value: null, pace_meets_target: true, status: "closed" })],
        },
      }),
    )[1];
    expect(closed.title).toBe("Fechamento do mês");
    expect(closed.lines).toEqual(["TMR: o mês fechou em 00:01:50 (meta 00:02:00), dentro da meta."]);

    const none = buildDashboardAnalysis(dashboard({ peak_day: null, month_projection: null }));
    expect(none).toHaveLength(1);
    expect(none[0].lines).toEqual(["Nenhum dia com aumento relevante de atendimentos no período."]);
  });
});
