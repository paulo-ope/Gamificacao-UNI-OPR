import { describe, expect, it } from "vitest";

import type { OperationBacklogTrend, OperationTrendPoint, OperationTrendSeries } from "@/lib/operations-api";
import { buildOverviewSlaBacklogOption, buildSlaRingOption, buildSparklineOption } from "@/lib/overview-chart-options";

function point(day: string, sla: number | null): OperationTrendPoint {
  return {
    period_start: day,
    period_end: day,
    opened_operation: 10,
    opened_associated: 10,
    completed: 8,
    completed_on_time: 6,
    completed_out_of_time: 2,
    completed_unmeasurable: 0,
    sla_rate: sla,
    sla_cumulative_rate: sla,
  };
}

const trend: OperationTrendSeries = {
  granularity: "day",
  responsible_filter_active: false,
  openings_ignore_responsibles: false,
  points: [point("2026-10-01", 84), point("2026-10-02", 83), point("2026-10-03", null)],
};

// Fotografia só em 02/10: 01/10 e 03/10 não têm coleta.
const backlog: OperationBacklogTrend = {
  date_from: "2026-10-01",
  date_to: "2026-10-03",
  coverage_from: "2026-10-02",
  points: [{ snapshot_date: "2026-10-02", backlog: 700 }],
};

type SeriesList = { name?: string; data?: unknown[] }[];

describe("buildOverviewSlaBacklogOption", () => {
  it("alinha o backlog por data e deixa sem barra os dias sem fotografia", () => {
    const option = buildOverviewSlaBacklogOption(trend, backlog, 80);
    const series = option.series as SeriesList;
    expect(series.find((item) => item.name === "Backlog")?.data).toEqual([null, 700, null]);
    expect(series.find((item) => item.name === "SLA acumulado")?.data).toEqual([84, 83, null]);
  });

  it("só desenha a linha do período anterior quando há janela anterior", () => {
    expect((buildOverviewSlaBacklogOption(trend, backlog, 80).series as SeriesList).length).toBe(2);
    expect((buildOverviewSlaBacklogOption(trend, backlog, 80, trend).series as SeriesList).length).toBe(3);
  });

  it("funciona sem nenhum histórico de backlog", () => {
    const option = buildOverviewSlaBacklogOption(trend, null, 80);
    expect((option.series as SeriesList).find((item) => item.name === "Backlog")?.data).toEqual([null, null, null]);
  });
});

describe("buildSlaRingOption", () => {
  it("esconde o arco de progresso quando não há dado", () => {
    const [series] = buildSlaRingOption(null).series as { progress: { show: boolean }; data: { value: number }[] }[];
    expect(series.progress.show).toBe(false);
    expect(series.data[0].value).toBe(0);
  });

  it("desenha o arco com o valor do SLA", () => {
    const [series] = buildSlaRingOption(86.5).series as { progress: { show: boolean }; data: { value: number }[] }[];
    expect(series.progress.show).toBe(true);
    expect(series.data[0].value).toBe(86.5);
  });
});

describe("buildSparklineOption", () => {
  it("usa os valores como estão, sem inventar pontos", () => {
    const [series] = buildSparklineOption([1, 2, 3], "#000").series as { data: number[] }[];
    expect(series.data).toEqual([1, 2, 3]);
  });
});
