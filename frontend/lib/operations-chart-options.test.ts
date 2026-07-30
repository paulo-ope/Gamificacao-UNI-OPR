import { describe, expect, it } from "vitest";

import { buildControlTowerOption, openingAnomalyThreshold, trendPointLabel } from "@/lib/operations-chart-options";
import type { OperationControlTower } from "@/lib/operations-api";

describe("operations chart options", () => {
  it("formats day, week and month labels in the operational timezone-neutral format", () => {
    expect(trendPointLabel("2026-07-21", "2026-07-21", "day")).toBe("21/07");
    expect(trendPointLabel("2026-07-20", "2026-07-26", "week")).toBe("20/07–26/07");
    expect(trendPointLabel("2026-07-01", "2026-07-31", "month")).toMatch(/jul/i);
  });

  it("only marks values above two standard deviations as anomalous", () => {
    const threshold = openingAnomalyThreshold([10, 10, 11, 9, 10, 10, 30]);
    expect(30).toBeGreaterThan(threshold);
    expect(11).toBeLessThan(threshold);
  });

  it("does not classify tiny samples", () => {
    expect(openingAnomalyThreshold([1, 10])).toBe(Number.POSITIVE_INFINITY);
  });

  it("builds the preventive chart with flow, expected limit and backlog", () => {
    const data: OperationControlTower = {
      reference_date: "2026-07-21",
      level: "subject",
      next_level: "regional",
      path: {},
      recent_days: 7,
      baseline_weeks: 8,
      timeline_days: 28,
      responsibles_ignored: true,
      calculation_note: "Teste",
      summary: { status: "attention", opened_recent: 10, expected_opened: 7, deviation_percentage: 42.9, completed_recent: 8, net_flow: 2, pressure_ratio: 1.25, backlog: 20, overdue_backlog: 4, average_backlog_age_hours: 30, persistent_days: 1, critical_nodes: 0, attention_nodes: 1, reasons: ["Teste"] },
      items: [],
      timeline: [{ date: "2026-07-21", opened: 10, completed: 8, expected_opened: 7, upper_limit: 9, outside_expected: true, backlog: 20 }]
    };
    const option = buildControlTowerOption(data);
    expect(option.series).toHaveLength(5);
    const series = JSON.stringify(option.series);
    expect(series).toContain("#ef4444");
    expect(series).toContain("Backlog");
    expect(series).toContain('"color":"#475569"');
    expect(series).toContain('"color":"#7c3aed"');
  });
});
