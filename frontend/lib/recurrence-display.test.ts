import { describe, expect, it } from "vitest";

import { cleanOperationalText, resolveRecurrenceDisplay } from "./recurrence-display";

const base = {
  recurrence_classification: null as string | null,
  recurrence_rule_name: null as string | null,
  is_warranty: false,
  is_recurrence: false
};

describe("resolveRecurrenceDisplay", () => {
  it("usa o nome da regra configurada pelo usuário quando existe", () => {
    const display = resolveRecurrenceDisplay({
      ...base,
      recurrence_classification: "garantia",
      recurrence_rule_name: "Garantia"
    });
    expect(display?.label).toBe("Garantia");
  });

  it("respeita nomes de regra personalizados sem reescrever", () => {
    const display = resolveRecurrenceDisplay({
      ...base,
      recurrence_classification: "reincidencia_tecnica",
      recurrence_rule_name: "Reincidência após suporte"
    });
    expect(display?.label).toBe("Reincidência após suporte");
  });

  it("cai no rótulo genérico da classificação quando não há regra nomeada", () => {
    const display = resolveRecurrenceDisplay({ ...base, recurrence_classification: "garantia" });
    expect(display?.label).toBe("Garantia");
  });

  it("não etiqueta classificações que não são retorno", () => {
    expect(resolveRecurrenceDisplay({ ...base, recurrence_classification: "os_nao_reincidente" })).toBeNull();
    expect(resolveRecurrenceDisplay({ ...base, recurrence_classification: "demandas_diferentes" })).toBeNull();
  });

  it("planilha legada com as duas flags marcadas gera UMA etiqueta (garantia vence)", () => {
    const display = resolveRecurrenceDisplay({ ...base, is_warranty: true, is_recurrence: true });
    expect(display?.label).toBe("Garantia (importada)");
  });

  it("flag legada de reincidência sozinha", () => {
    const display = resolveRecurrenceDisplay({ ...base, is_recurrence: true });
    expect(display?.label).toBe("Reincidência (importada)");
  });

  it("sem classificação nem flags: sem etiqueta", () => {
    expect(resolveRecurrenceDisplay(base)).toBeNull();
  });
});

describe("cleanOperationalText", () => {
  it("corrige acentos sem renomear Garantia", () => {
    expect(cleanOperationalText("Garantia com reincidencia e pontuacao em revisao")).toBe(
      "Garantia com reincidência e pontuação em revisão"
    );
  });

  it("trata vazio como Não informado", () => {
    expect(cleanOperationalText(null)).toBe("Não informado");
  });
});
