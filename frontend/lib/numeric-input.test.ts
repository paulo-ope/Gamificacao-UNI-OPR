import { describe, expect, it } from "vitest";

import { numericInputValue, parseNumericInput } from "./numeric-input";

describe("numericInputValue", () => {
  it("mantém números finitos como estão", () => {
    expect(numericInputValue(0)).toBe(0);
    expect(numericInputValue(5)).toBe(5);
    expect(numericInputValue(500)).toBe(500);
    expect(numericInputValue(0.5)).toBe(0.5);
    expect(numericInputValue(-3)).toBe(-3);
  });

  it("mostra vazio quando o número não é finito", () => {
    expect(numericInputValue(Number.NaN)).toBe("");
    expect(numericInputValue(Number.POSITIVE_INFINITY)).toBe("");
  });
});

describe("parseNumericInput", () => {
  it("converte string numérica pra number", () => {
    expect(parseNumericInput("5")).toBe(5);
    expect(parseNumericInput("500")).toBe(500);
    expect(parseNumericInput("0.5")).toBe(0.5);
    expect(parseNumericInput("-3")).toBe(-3);
  });

  it("string vazia vira NaN, não 0 - pra não repor zero indevido durante a digitação", () => {
    expect(Number.isNaN(parseNumericInput(""))).toBe(true);
  });

  it("nunca concatena: '0' seguido de digitar '500' produz 500, não '0500'", () => {
    // Simula o fluxo real: estado começa em 0, exibido como "0" (via numericInputValue),
    // o usuário digita e o DOM entrega a string bruta "0500" (comportamento nativo do
    // input type=number enquanto o cursor está no fim) - o parse deve extrair o valor certo.
    const displayed = numericInputValue(0);
    expect(displayed).toBe(0);
    expect(parseNumericInput("0500")).toBe(500);
  });
});
