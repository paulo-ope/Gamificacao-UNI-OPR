import { describe, expect, it } from "vitest";

import { formatPreviousLine } from "./dashboard-format";

const csat = (value: number | null, previous: number | null, change: number | null) => ({ unit: "score" as const, value, previous, change });

describe("linha do que era antes (CSAT e demais cartões)", () => {
  it("mostra o valor anterior, a diferença e o percentual, como no cartão", () => {
    // 4,26 contra 4,37: queda de 0,11 (-2,5%), a mesma conta do percentual exibido no cartão.
    expect(formatPreviousLine(csat(4.26, 4.37, -0.11))).toBe("Antes: 4,37 · -0,11 (-2,5%)");
  });

  it("a diferença bate com os números exibidos, não com as casas escondidas", () => {
    // Exibe 4,34 e 4,40: a diferença mostrada tem de ser -0,06, mesmo que o backend tenha -0,0542.
    expect(formatPreviousLine(csat(4.3449, 4.3991, -0.0542))).toBe("Antes: 4,40 · -0,06 (-1,2%)");
  });

  it("sinal positivo quando subiu", () => {
    expect(formatPreviousLine(csat(4.5, 4.4, 0.1))).toBe("Antes: 4,40 · +0,10 (+2,3%)");
  });

  it("formata tempo em hh:mm:ss e diferença em tempo", () => {
    expect(formatPreviousLine({ unit: "seconds", value: 192, previous: 148, change: 44 })).toBe("Antes: 00:02:28 · +00:00:44 (+29,7%)");
  });

  it("indicador percentual mostra só o valor de antes: o p.p. já está no cartão", () => {
    expect(formatPreviousLine({ unit: "percent", value: 74.19, previous: 94.04, change: -19.84 })).toBe("Antes: 94,04%");
  });

  it("contagem mostra o anterior, a diferença e o percentual", () => {
    expect(formatPreviousLine({ unit: "count", value: 3379, previous: 3633, change: -254 })).toBe("Antes: 3.633 · -254 (-7%)");
  });

  it("sem valor anterior não mostra nada", () => {
    expect(formatPreviousLine(csat(4.26, null, null))).toBeNull();
  });

  it("anterior zero não gera percentual infinito, só a diferença", () => {
    expect(formatPreviousLine({ unit: "count", value: 5, previous: 0, change: 5 })).toBe("Antes: 0 · +5");
  });
});
