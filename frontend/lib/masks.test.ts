import { describe, expect, it } from "vitest";

import { formatCpf, formatPhone, isValidCpf, onlyDigits } from "./masks";

describe("onlyDigits", () => {
  it("remove tudo que não é dígito", () => {
    expect(onlyDigits("529.982.247-25")).toBe("52998224725");
    expect(onlyDigits("(69) 99999-0000")).toBe("69999990000");
  });
});

describe("formatCpf", () => {
  it("formata progressivamente enquanto digita", () => {
    expect(formatCpf("5")).toBe("5");
    expect(formatCpf("529982")).toBe("529.982");
    expect(formatCpf("529982247")).toBe("529.982.247");
    expect(formatCpf("52998224725")).toBe("529.982.247-25");
  });

  it("ignora dígitos além do 11º", () => {
    expect(formatCpf("529982247259999")).toBe("529.982.247-25");
  });
});

describe("formatPhone", () => {
  it("formata fixo (10 dígitos)", () => {
    expect(formatPhone("6932221234")).toBe("(69) 3222-1234");
  });

  it("formata celular (11 dígitos)", () => {
    expect(formatPhone("69999990000")).toBe("(69) 99999-0000");
  });

  it("formata progressivamente enquanto digita", () => {
    expect(formatPhone("6")).toBe("(6");
    expect(formatPhone("69")).toBe("(69) ");
    expect(formatPhone("699999")).toBe("(69) 9999");
  });
});

describe("isValidCpf", () => {
  it("aceita CPF com dígito verificador correto, com ou sem máscara", () => {
    expect(isValidCpf("529.982.247-25")).toBe(true);
    expect(isValidCpf("52998224725")).toBe(true);
  });

  it("rejeita sequência repetida", () => {
    expect(isValidCpf("111.111.111-11")).toBe(false);
  });

  it("rejeita dígito verificador incorreto", () => {
    expect(isValidCpf("529.982.247-99")).toBe(false);
  });

  it("rejeita tamanho errado", () => {
    expect(isValidCpf("123")).toBe(false);
    expect(isValidCpf("")).toBe(false);
  });
});
