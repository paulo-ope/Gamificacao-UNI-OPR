import { describe, expect, it } from "vitest";

import { slaTone } from "@/lib/operations-sla";

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
