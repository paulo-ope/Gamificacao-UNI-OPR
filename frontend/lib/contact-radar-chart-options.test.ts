import { describe, expect, it } from "vitest";

import { bucketLabel, seriesLabels } from "./contact-radar-chart-options";
import type { SupportContactRadarPoint } from "./types";

const point = (start: string, by_channel: Record<string, number>): SupportContactRadarPoint => ({
  start, contacts: Object.values(by_channel).reduce((sum, value) => sum + value, 0), located_contacts: 0, customers: 0, by_channel,
});

describe("rótulos de tempo do Radar de Contatos", () => {
  it("mostra o horário de Porto Velho (UTC-4), não o UTC", () => {
    expect(bucketLabel("2026-10-20T18:00:00Z", 60, false)).toBe("14h");
    expect(bucketLabel("2026-10-20T18:35:00Z", 5, false)).toBe("14:35");
    expect(bucketLabel("2026-10-20T18:00:00Z", 60, true)).toBe("20/10 14h");
    // 02:00Z ainda é o dia anterior em Porto Velho.
    expect(bucketLabel("2026-10-21T02:00:00Z", 1440, true)).toBe("20/10");
  });

  it("usa rótulo com data só quando a série cruza mais de um dia", () => {
    const sameDay = [point("2026-10-20T15:00:00Z", {}), point("2026-10-20T16:00:00Z", {})];
    expect(seriesLabels(sameDay, 60)).toEqual(["11h", "12h"]);
    const twoDays = [point("2026-10-20T15:00:00Z", {}), point("2026-10-21T15:00:00Z", {})];
    expect(seriesLabels(twoDays, 60)).toEqual(["20/10 11h", "21/10 11h"]);
  });
});
