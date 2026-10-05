import { describe, expect, it } from "vitest";

import { aggregateSlaItems, slaTone } from "@/lib/operations-sla";

describe("aggregateSlaItems", () => {
  const urbana = { completed: 597, on_time: 462, average_closing_hours: 22.7 };
  const rural = { completed: 124, on_time: 87, average_closing_hours: 29.9 };
  const radio = { completed: 79, on_time: 50, average_closing_hours: 50 };

  it("sem grupos ou sem finalizadas devolve sem dado", () => {
    expect(aggregateSlaItems([])).toEqual({ completed: 0, sla_rate: null, average_closing_hours: null });
    expect(aggregateSlaItems([{ completed: 0, on_time: 0, average_closing_hours: null }]).sla_rate).toBeNull();
  });

  it("um grupo devolve o próprio SLA", () => {
    expect(aggregateSlaItems([urbana]).sla_rate).toBe(77.4);
  });

  it("pondera pelo volume, não pela média simples dos percentuais", () => {
    const result = aggregateSlaItems([urbana, rural, radio]);
    expect(result.completed).toBe(800);
    expect(result.sla_rate).toBe(74.9);
    expect(result.average_closing_hours).toBe(26.5);
  });

  it("ignora grupo sem tempo médio no cálculo de horas", () => {
    const result = aggregateSlaItems([urbana, { completed: 10, on_time: 10, average_closing_hours: null }]);
    expect(result.average_closing_hours).toBe(22.7);
  });
});

describe("slaTone", () => {
  it("aplica exatamente os limites operacionais configurados", () => {
    expect(slaTone(null)).toBe("neutral");
    expect(slaTone(59.9)).toBe("danger");
    expect(slaTone(60)).toBe("warning");
    expect(slaTone(79.9)).toBe("warning");
    expect(slaTone(80)).toBe("success");
    expect(slaTone(100)).toBe("success");
  });
});
