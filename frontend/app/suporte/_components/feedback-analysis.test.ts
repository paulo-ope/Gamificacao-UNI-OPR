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

    expect(sections.map((section) => section.title)).toEqual(["Resumo", "Destaques", "A evoluir", "Próxima semana"]);
    expect(sections[0].lines).toEqual(["Evoluir: 1 na meta, 0 em atenção, 1 a evoluir."]);
    expect(sections[1].lines).toEqual(["Registros Operacional (+63,3%)"]);
    expect(sections[2].lines).toEqual(["O.S. Aberta a Campo: 45 (meta até 25, 20 acima) · piorou 18,4%"]);
  });

  it("junta notas e O.S. a campo do colaborador", () => {
    const sections = buildFeedbackAnalysis(feedback([indicator({})]), details());

    const satisfaction = sections.find((section) => section.title.startsWith("Pesquisa"));
    expect(satisfaction?.lines[0]).toBe("27 avaliações, média 4,6: 25 boas, 0 neutras, 2 ruins.");
    const orders = sections.find((section) => section.title.startsWith("O.S."));
    expect(orders?.lines[0]).toBe("45 O.S. abertas, 11 evitáveis (24%). Motivos: 4 desistência da solicitação, 3 assunto errado, 1 duplicada, 4 equipamento travado.");
    expect(orders?.lines).toContain("Revisar 3: 3 problema na rede interna do cliente.");
    const cases = sections.find((section) => section.title === "Casos para conversar");
    expect(cases?.lines[0]).toBe('IXC-1 · 20/10 · duplicada: "Cliente já tinha visita no dia anterior."');
    expect(cases?.lines).toContain("Clientes com mais de uma O.S.: Rubens (3).");
    expect(cases?.lines).toContain("Sem diagnóstico: IXC-9.");
    const next = sections.at(-1);
    expect(next?.lines).toContain("Escolher o assunto correto ao abrir a O.S.");
  });

  it("lista só as primeiras notas ruins e os primeiros casos, com relato cortado", () => {
    const base = details();
    const rated = (protocol: string, rating: number) => ({ protocol, opened_at: "2026-10-20T10:00:00Z", channel: "whatsapp", rating, band: "bad" as const, reason: null, tma_seconds: null, tmr_seconds: null });
    const order = (code: string) => ({ order_code: code, customer_name: null, opened_at: "2026-10-20T10:00:00Z", status: "Finalizada", diagnosis: null, reasons: ["Desistência da solicitação"], report: "x".repeat(150) });
    const sections = buildFeedbackAnalysis(feedback([indicator({})]), {
      ...base,
      ratings: { ...base.ratings, attendances: [rated("P1", 1), rated("P2", 2), rated("P3", 1), rated("P4", 2), rated("P5", 1)] },
      improper_orders: { ...base.improper_orders!, orders: ["A", "B", "C", "D", "E", "F", "G"].map(order) },
    });

    const satisfaction = sections.find((section) => section.title.startsWith("Pesquisa"));
    expect(satisfaction?.lines[1]).toBe("Ruins: P1 (1), P2 (2), P3 (1) e mais 2.");
    const cases = sections.find((section) => section.title === "Casos para conversar");
    expect(cases?.lines[0]).toBe(`A · 20/10 · desistência da solicitação: "${"x".repeat(100)}…"`);
    expect(cases?.lines.filter((line) => line.startsWith("A ·") || line.startsWith("B ·") || line.startsWith("E ·"))).toHaveLength(3);
    expect(cases?.lines).toContain("Mais 2 O.S. indevidas.");
    expect(cases?.lines.some((line) => line.startsWith("F ·"))).toBe(false);
  });

  it("não inventa seções sem dado", () => {
    const base = details();
    const sections = buildFeedbackAnalysis(feedback([indicator({ previous: null })]), { ...base, improper_orders: null, ratings: { ...base.ratings, rated_count: 0 } });

    expect(sections.map((section) => section.title)).toEqual(["Resumo", "Próxima semana"]);
    expect(sections[1].lines).toEqual(["Manter o desempenho atual."]);
  });
});
