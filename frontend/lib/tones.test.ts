import { describe, expect, it } from "vitest";

import { scoringStatusEntry, scoringStatusTone, toneBadgeClass } from "./tones";

describe("toneBadgeClass", () => {
  it("segue a fórmula border/bg/text do sistema", () => {
    expect(toneBadgeClass("emerald")).toBe("border-emerald-200 bg-emerald-50 text-emerald-700");
    expect(toneBadgeClass("red")).toBe("border-red-200 bg-red-50 text-red-700");
  });
});

describe("scoringStatusTone", () => {
  it("mapeia os status canônicos", () => {
    expect(scoringStatusTone("O.S pontuada")).toBe("emerald");
    expect(scoringStatusTone("Anulada por reincidência")).toBe("red");
    expect(scoringStatusTone("Sem regra")).toBe("amber");
    expect(scoringStatusTone("Revisão manual")).toBe("violet");
  });

  it("status desconhecido cai em slate", () => {
    expect(scoringStatusTone("Qualquer coisa nova")).toBe("slate");
  });
});

describe("scoringStatusEntry", () => {
  it("retorna entrada do registry para status conhecidos", () => {
    const entry = scoringStatusEntry("Anulada por SLA");
    expect(entry.tone).toBe("red");
    expect(entry.label).toBe("Anulada por SLA");
  });

  it("status texto-livre desconhecido ganha fallback por substring", () => {
    const entry = scoringStatusEntry("O.S pontuada com ajuste");
    expect(entry.tone).toBe("emerald");
    expect(entry.label).toBe("O.S pontuada com ajuste");
  });
});
