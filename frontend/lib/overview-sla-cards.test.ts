import { describe, expect, it } from "vitest";

import type { OperationSlaItem } from "@/lib/operations-api";
import { buildSlaGaugeCards } from "@/lib/overview-sla-cards";

function item(label: string, completed: number, onTime: number): OperationSlaItem {
  return {
    label,
    completed,
    on_time: onTime,
    out_of_time: completed - onTime,
    sla_rate: completed ? Math.round((onTime / completed) * 1000) / 10 : null,
    up_to_12h: 0,
    from_12h_to_24h: 0,
    from_24h_to_48h: 0,
    from_48h_to_72h: 0,
    after_72h: 0,
    average_closing_hours: null,
  };
}

const GROUPS = ["Fibra Urbana", "Rádio"] as const;

describe("buildSlaGaugeCards", () => {
  it("põe o Geral primeiro, ponderado pelo volume e não pela média dos percentuais", () => {
    const cards = buildSlaGaugeCards({
      groups: GROUPS,
      current: [item("Fibra Urbana", 900, 810), item("Rádio", 100, 50)],
      previous: null,
      year: null,
    });
    expect(cards.map((card) => card.label)).toEqual(["Geral", "Fibra Urbana", "Rádio"]);
    // (810 + 50) / 1000 = 86%; a média simples de 90% e 50% daria 70%.
    expect(cards[0].rate).toBe(86);
  });

  it("calcula variação contra o período anterior, SLA do ano e distância da meta de 80%", () => {
    const cards = buildSlaGaugeCards({
      groups: GROUPS,
      current: [item("Fibra Urbana", 100, 90), item("Rádio", 100, 70)],
      previous: [item("Fibra Urbana", 100, 80), item("Rádio", 100, 75)],
      year: [item("Fibra Urbana", 1000, 880), item("Rádio", 1000, 760)],
    });
    const urbana = cards.find((card) => card.key === "Fibra Urbana");
    const radio = cards.find((card) => card.key === "Rádio");
    expect(urbana).toMatchObject({ rate: 90, deltaPp: 10, yearRate: 88, gapPp: 10 });
    expect(radio).toMatchObject({ rate: 70, deltaPp: -5, yearRate: 76, gapPp: -10 });
  });

  it("devolve nulos, e não zeros, quando não há dado ou base de comparação", () => {
    const cards = buildSlaGaugeCards({ groups: GROUPS, current: [], previous: null, year: null });
    for (const card of cards) {
      expect(card).toMatchObject({ rate: null, deltaPp: null, yearRate: null, gapPp: null, completed: 0 });
    }
  });

  it("o Geral soma só os grupos selecionados, com variação e ano na mesma seleção", () => {
    const cards = buildSlaGaugeCards({
      groups: GROUPS,
      current: [item("Fibra Urbana", 900, 810), item("Rádio", 100, 50)],
      previous: [item("Fibra Urbana", 100, 80), item("Rádio", 100, 40)],
      year: [item("Fibra Urbana", 1000, 880), item("Rádio", 1000, 600)],
      selected: ["Rádio"],
    });
    expect(cards[0]).toMatchObject({ rate: 50, deltaPp: 10, yearRate: 60, scopeLabel: "1 de 2 selecionados" });
    expect(cards.find((card) => card.key === "Rádio")?.selected).toBe(true);
    expect(cards.find((card) => card.key === "Fibra Urbana")?.selected).toBe(false);
  });

  it("sem seleção o Geral soma todos os grupos", () => {
    const cards = buildSlaGaugeCards({
      groups: GROUPS,
      current: [item("Fibra Urbana", 900, 810), item("Rádio", 100, 50)],
      previous: null,
      year: null,
      selected: [],
    });
    expect(cards[0]).toMatchObject({ rate: 86, scopeLabel: "todos os grupos" });
  });

  it("ignora seleção de grupo que não existe mais no cartão", () => {
    const cards = buildSlaGaugeCards({
      groups: GROUPS,
      current: [item("Fibra Urbana", 100, 90), item("Rádio", 100, 50)],
      previous: null,
      year: null,
      selected: ["Grupo removido"],
    });
    expect(cards[0].scopeLabel).toBe("todos os grupos");
  });
});
