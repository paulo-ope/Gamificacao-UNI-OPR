import { describe, expect, it } from "vitest";

import { percentChange, previousWindow, windowLengthDays } from "@/lib/period";

describe("windowLengthDays", () => {
  it("conta as duas pontas", () => {
    expect(windowLengthDays("2026-08-05", "2026-09-03")).toBe(30);
    expect(windowLengthDays("2026-09-03", "2026-09-03")).toBe(1);
  });
});

describe("previousWindow", () => {
  it("devolve a janela imediatamente anterior, do mesmo tamanho", () => {
    expect(previousWindow("2026-08-05", "2026-09-03")).toEqual({
      date_from: "2026-07-06",
      date_to: "2026-08-04",
      truncated: false,
    });
  });

  it("atravessa a virada de mês e de ano sem perder dia", () => {
    expect(previousWindow("2026-01-01", "2026-01-10")).toEqual({
      date_from: "2025-12-22",
      date_to: "2025-12-31",
      truncated: false,
    });
  });

  it("corta no início do ano operacional e avisa que cortou", () => {
    expect(previousWindow("2026-01-15", "2026-02-13", "2026-01-01")).toEqual({
      date_from: "2026-01-01",
      date_to: "2026-01-14",
      truncated: true,
    });
  });

  it("sem nenhum dia permitido na janela anterior, não há comparação", () => {
    // Janela começa no primeiro dia permitido: o "anterior" cairia inteiro no ano passado.
    expect(previousWindow("2026-01-01", "2026-01-30", "2026-01-01")).toBeNull();
  });

  it("janela invertida não produz comparação", () => {
    expect(previousWindow("2026-09-03", "2026-08-05")).toBeNull();
  });
});

describe("percentChange", () => {
  it("calcula com uma casa e sinal", () => {
    expect(percentChange(120, 100)).toBe(20);
    expect(percentChange(90, 100)).toBe(-10);
    expect(percentChange(101, 300)).toBe(-66.3);
  });

  it("sem base de comparação devolve null em vez de infinito", () => {
    expect(percentChange(12, 0)).toBeNull();
    expect(percentChange(12, null)).toBeNull();
    expect(percentChange(null, 12)).toBeNull();
  });
});
