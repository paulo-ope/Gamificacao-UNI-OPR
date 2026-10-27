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
  it("aponta o dia de maior aumento e os motivos que puxaram", () => {
    const [peak] = buildDashboardAnalysis(dashboard());

    expect(peak.title).toBe("Dia de maior aumento");
    expect(peak.lines[0]).toBe("Dia 20/10 teve 210 atendimentos no OPA, 40% acima da média dos outros dias do período (150 por dia).");
    expect(peak.lines[1]).toContain("Sem conexão (45, habitual 20 por dia)");
    expect(peak.lines[2]).toBe("Puxaram o aumento: Sem conexão.");
  });

  it("diz quanto falta para a meta, ou que já está dentro", () => {
    const meta = buildDashboardAnalysis(dashboard()).find((section) => section.title.startsWith("Para bater"));

    expect(meta?.lines).toEqual([
      "TMR: 00:02:35 contra a meta de 00:02:00. Na próxima semana precisa cair 35 segundos para bater a meta.",
      "TMA: 00:30:00, dentro da meta de 01:00:00. Manter o ritmo na próxima semana.",
      "Avaliação (CSAT): 4,42 contra a meta de 4,50. Na próxima semana precisa subir 0,08 pontos para bater a meta.",
    ]);
  });

  it("avisa quando não houve aumento relevante e não avalia dado parcial", () => {
    const sections = buildDashboardAnalysis(dashboard({ peak_day: null, cards: [card({ status: "partial" })] }));

    expect(sections[0].lines).toEqual(["Nenhum dia com aumento relevante de atendimentos no período."]);
    expect(sections[1].lines[0]).toContain("dados ainda incompletos");
  });
});
