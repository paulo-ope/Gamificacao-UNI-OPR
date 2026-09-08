import { describe, expect, it } from "vitest";

import { isWithinViewport } from "@/lib/viewport";

describe("isWithinViewport", () => {
  const viewport = 900;

  it("revela o que está dentro da viewport", () => {
    expect(isWithinViewport({ top: 100, bottom: 400 }, viewport)).toBe(true);
  });

  it("revela o que está parcialmente visível, em cima ou embaixo", () => {
    expect(isWithinViewport({ top: -200, bottom: 50 }, viewport)).toBe(true);
    expect(isWithinViewport({ top: 850, bottom: 1200 }, viewport)).toBe(true);
  });

  it("não revela o que ainda está abaixo da dobra", () => {
    expect(isWithinViewport({ top: 1522, bottom: 1842 }, viewport)).toBe(false);
  });

  it("a margem antecipa a revelação antes de o bloco aparecer", () => {
    // 1000px de topo numa viewport de 900: fora sem margem, dentro com 240px de antecedência.
    expect(isWithinViewport({ top: 1000, bottom: 1320 }, viewport)).toBe(false);
    expect(isWithinViewport({ top: 1000, bottom: 1320 }, viewport, 240)).toBe(true);
  });

  it("a margem também vale para o que já passou pra cima", () => {
    expect(isWithinViewport({ top: -500, bottom: -100 }, viewport, 240)).toBe(true);
    expect(isWithinViewport({ top: -500, bottom: -300 }, viewport, 240)).toBe(false);
  });

  it("viewport de altura zero (aba oculta) nunca revela, mesmo com o retângulo em cima", () => {
    // Achado real de 2026-09-03: o painel embutido colapsava a viewport para 0px; revelar ali só
    // dispararia o download do gráfico sem ninguém para ver.
    expect(isWithinViewport({ top: 0, bottom: 300 }, 0)).toBe(false);
    expect(isWithinViewport({ top: 0, bottom: 300 }, 0, 240)).toBe(false);
  });
});
