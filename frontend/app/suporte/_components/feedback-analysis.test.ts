import { describe, expect, it } from "vitest";

import type { SupportFeedback, SupportFeedbackDetails, SupportFeedbackIndicator } from "@/lib/types";

import { buildFeedbackAnalysis } from "./feedback-analysis";

const indicator = (over: Partial<SupportFeedbackIndicator>): SupportFeedbackIndicator => ({
  key: "operational", label: "Registros Operacional", unit: "count", value: 98, previous: 60, target: 50, weekly_target: 50,
  direction: "min", status: "ok", source: "ixc", coverage: null, note: null, ...over,
});

const feedback = (indicators: SupportFeedbackIndicator[]): SupportFeedback => ({
  attendant_id: "1", name: "Bruno", date_from: "2026-10-18", date_to: "2026-10-24", previous_date_from: null, previous_date_to: null,
  goal_scale: 1, ixc_linked: true, indicators, summary: { ok: 1, attention: 0, critical: 1, overall: "critical" }, daily: [],
});

const details = (over: Partial<SupportFeedbackDetails> = {}): SupportFeedbackDetails => ({
  attendant_id: "1", name: "Bruno", date_from: "2026-10-18", date_to: "2026-10-24", ixc_linked: true,
  ratings: { rated_count: 27, average: 4.6, good: { count: 25, percent: 92.6 }, neutral: { count: 0, percent: 0 }, bad: { count: 2, percent: 7.4 }, by_day: [], by_channel: [], attendances: [], truncated: false },
  improper_orders: {
    total_orders: 45, improper_count: 7, improper_percent: 15.6, remote_resolvable: { count: 4, by_reason: [{ reason: "Equipamento travado", count: 4 }] },
    to_review: { count: 3, by_reason: [{ reason: "Problema na rede interna do cliente", count: 3 }] }, repeat_customers: [{ customer_name: "Rubens", count: 3 }], no_diagnosis_codes: ["IXC-9"],
    by_reason: [{ reason: "Desistência da solicitação", count: 4 }, { reason: "Assunto errado", count: 3 }, { reason: "Duplicada (mesmo cliente em até 72 h)", count: 1 }],
    orders: [{ order_code: "IXC-1", customer_name: "Maria", opened_at: "2026-10-20T10:00:00Z", status: "Finalizada", diagnosis: null, reasons: ["Duplicada (mesmo cliente em até 72 h)"], report: "Cliente já tinha visita no dia anterior." }], truncated: false,
  },
  ...over,
});

describe("buildFeedbackAnalysis", () => {
  it("resume, destaca o que melhorou e lista o que evoluir", () => {
    const data = feedback([
      indicator({}),
      indicator({ key: "field", label: "O.S. Aberta a Campo", value: 45, previous: 38, target: 25, direction: "max", status: "critical" }),
    ]);

    const sections = buildFeedbackAnalysis(data, null);

    expect(sections.map((section) => section.title)).toEqual(["Resumo", "Destaques", "A evoluir", "Sugestão para a próxima semana"]);
    expect(sections[0].lines[0]).toContain("Status: Evoluir");
    expect(sections[1].lines[0]).toBe("Registros Operacional: 98, +63,3% contra o período anterior (melhorou)");
    expect(sections[2].lines[0]).toBe("O.S. Aberta a Campo: 45 (até 25), 20 acima da meta, +18,4% contra o período anterior (piorou)");
  });

  it("junta notas e O.S. a campo do colaborador", () => {
    const sections = buildFeedbackAnalysis(feedback([indicator({})]), details());

    const satisfaction = sections.find((section) => section.title.startsWith("Pesquisa"));
    expect(satisfaction?.lines[0]).toBe("27 avaliações, nota média 4,6: 25 boas (92,6%), 0 neutras e 2 ruins.");
    const orders = sections.find((section) => section.title.startsWith("O.S."));
    expect(orders?.lines[0]).toBe("Das 45 O.S. abertas, 11 (24%) poderiam ter sido evitadas: 4 desistência da solicitação, 3 assunto errado, 4 equipamento travado.");
    expect(orders?.lines).toContain("Vale revisar 3: 3 problema na rede interna do cliente.");
    expect(orders?.lines).toContain("1 O.S. aberta em duplicidade: o cliente já tinha O.S. recente.");
    const cases = sections.find((section) => section.title === "Casos para conversar");
    expect(cases?.lines[0]).toContain("IXC-1 (Maria), 20/10 - duplicada (mesmo cliente em até 72 h).");
    expect(cases?.lines[0]).toContain('Relato da finalização: "Cliente já tinha visita no dia anterior."');
    expect(cases?.lines.some((line) => line.includes("Rubens (3)"))).toBe(true);
    expect(cases?.lines).toContain("Finalizada sem diagnóstico: IXC-9.");
    const next = sections.at(-1);
    expect(next?.lines).toContain("Escolher o assunto correto na abertura da O.S.");
  });

  it("não inventa seções sem dado", () => {
    const base = details();
    const sections = buildFeedbackAnalysis(feedback([indicator({ previous: null })]), { ...base, improper_orders: null, ratings: { ...base.ratings, rated_count: 0 } });

    expect(sections.map((section) => section.title)).toEqual(["Resumo", "Sugestão para a próxima semana"]);
    expect(sections[1].lines).toEqual(["Manter o desempenho atual."]);
  });
});
