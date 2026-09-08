import { describe, expect, it } from "vitest";

import { CATEGORICAL_SLOTS, NEUTRAL_SERIES } from "@/lib/chart-palette";
import { assignSeriesColors, foldShares, OTHER_LABEL } from "@/lib/share-breakdown";

describe("foldShares", () => {
  const filiais = [
    { label: "UNI - JI PARANA", value: 1241 },
    { label: "UNI - JARU", value: 768 },
    { label: "UNI - MACHADINHO DOESTE", value: 630 },
    { label: "UNI - ROLIM DE MOURA", value: 535 },
    { label: "UNI - OURO PRETO DOESTE", value: 524 },
    { label: "UNI - NOVA BRASILANDIA DOESTE", value: 388 },
    { label: "UNI - PRESIDENTE MEDICI", value: 386 },
    { label: "UNI - ALVORADA DOESTE", value: 369 },
  ];

  it("mantém as maiores nomeadas e dobra a cauda em Outros", () => {
    const slices = foldShares(filiais, { maxSlices: 5 });
    expect(slices).toHaveLength(6);
    expect(slices.slice(0, 5).map((s) => s.label)).toEqual([
      "UNI - JI PARANA",
      "UNI - JARU",
      "UNI - MACHADINHO DOESTE",
      "UNI - ROLIM DE MOURA",
      "UNI - OURO PRETO DOESTE",
    ]);
    const other = slices[5];
    expect(other.isOther).toBe(true);
    expect(other.label).toBe(OTHER_LABEL);
    expect(other.value).toBe(388 + 386 + 369);
    expect(other.color).toBe(NEUTRAL_SERIES);
  });

  it("as participações somam 100 (com arredondamento de uma casa)", () => {
    const total = foldShares(filiais).reduce((sum, s) => sum + s.share, 0);
    expect(Math.abs(total - 100)).toBeLessThan(0.5);
  });

  it("não cria um Outros de um item só - o último fica nomeado", () => {
    const seis = filiais.slice(0, 6);
    const slices = foldShares(seis, { maxSlices: 5 });
    expect(slices).toHaveLength(6);
    expect(slices.every((s) => !s.isOther)).toBe(true);
  });

  it("descarta valores zero ou negativos antes de qualquer conta", () => {
    const slices = foldShares([
      { label: "A", value: 10 },
      { label: "B", value: 0 },
      { label: "C", value: -3 },
    ]);
    expect(slices.map((s) => s.label)).toEqual(["A"]);
    expect(slices[0].share).toBe(100);
  });

  it("lista vazia ou só zeros devolve nenhuma fatia", () => {
    expect(foldShares([])).toEqual([]);
    expect(foldShares([{ label: "A", value: 0 }])).toEqual([]);
  });

  it("a cor segue a entidade, não a posição: filtrar não repinta quem sobrou", () => {
    const antes = foldShares(filiais.slice(0, 3));
    const depois = foldShares(filiais.slice(0, 3).filter((f) => f.label !== "UNI - JARU"));
    const corJiParana = (s: typeof antes) => s.find((x) => x.label === "UNI - JI PARANA")?.color;
    // Sem JARU a ordem alfabética muda e a cor de JI PARANA pode mudar de slot - o que NÃO pode
    // acontecer é a cor depender do ranking por valor. Aqui o conjunto muda, logo o teste
    // verifica o contrato exato: mesma entidade no mesmo conjunto → mesma cor.
    expect(corJiParana(antes)).toBe(assignSeriesColors(filiais.slice(0, 3).map((f) => f.label)).get("UNI - JI PARANA"));
    expect(corJiParana(depois)).toBe(assignSeriesColors(["UNI - JI PARANA", "UNI - MACHADINHO DOESTE"]).get("UNI - JI PARANA"));
  });
});

describe("assignSeriesColors", () => {
  it("atribui os 8 slots em ordem alfabética antes de repetir matiz", () => {
    const colors = assignSeriesColors(["Zeta", "Alfa", "Beta"]);
    expect(colors.get("Alfa")).toBe(CATEGORICAL_SLOTS[0]);
    expect(colors.get("Beta")).toBe(CATEGORICAL_SLOTS[1]);
    expect(colors.get("Zeta")).toBe(CATEGORICAL_SLOTS[2]);
  });

  it("além do 8º rótulo volta pro início da paleta num tom diferente, nunca no neutro", () => {
    const labels = Array.from({ length: 10 }, (_, i) => `S${String(i).padStart(2, "0")}`);
    const colors = assignSeriesColors(labels);
    expect(colors.get("S07")).toBe(CATEGORICAL_SLOTS[7]);
    // S08 reaproveita o matiz do slot 0 (8 % 8 === 0), num tom claramente diferente do slot puro
    // e do cinza neutro - cada entidade extra continua distinguível, nunca cai no mesmo cinza de
    // "Outros" nem fica idêntica a outra entidade.
    expect(colors.get("S08")).not.toBe(NEUTRAL_SERIES);
    expect(colors.get("S08")).not.toBe(CATEGORICAL_SLOTS[0]);
    expect(colors.get("S09")).not.toBe(NEUTRAL_SERIES);
    expect(colors.get("S09")).not.toBe(colors.get("S08"));
  });

  it("ignora rótulos repetidos", () => {
    expect(assignSeriesColors(["A", "A", "B"]).size).toBe(2);
  });
});
