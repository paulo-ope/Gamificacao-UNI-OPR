import { describe, expect, it } from "vitest";

import { secondsLabel } from "./format-duration";

describe("secondsLabel", () => {
  it("mostra traço quando o valor é nulo ou indefinido", () => {
    expect(secondsLabel(null)).toBe("-");
    expect(secondsLabel(undefined)).toBe("-");
  });

  it("mostra segundos sem arredondar pra minuto abaixo de 60s", () => {
    expect(secondsLabel(0)).toBe("0 s");
    expect(secondsLabel(14)).toBe("14 s");
    expect(secondsLabel(59)).toBe("59 s");
  });

  it("mostra minutos e segundos sem perder precisão entre 1min e 1h", () => {
    expect(secondsLabel(60)).toBe("1 min 00 s");
    expect(secondsLabel(89)).toBe("1 min 29 s");
    expect(secondsLabel(3599)).toBe("59 min 59 s");
  });

  it("mostra horas, minutos e segundos com padding a partir de 1h", () => {
    expect(secondsLabel(3600)).toBe("1 h 00 min 00 s");
    expect(secondsLabel(3735)).toBe("1 h 02 min 15 s");
    expect(secondsLabel(7325)).toBe("2 h 02 min 05 s");
  });

  it("arredonda frações de segundo sem trocar de faixa indevidamente", () => {
    expect(secondsLabel(13.6)).toBe("14 s");
    expect(secondsLabel(59.4)).toBe("59 s");
  });
});
