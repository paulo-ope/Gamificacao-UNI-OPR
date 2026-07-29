import { describe, expect, it } from "vitest";

import { deriveClosureData } from "@/hooks/use-closure-data";
import type { CollaboratorScore, DashboardSummary, RegionalHealthItem } from "@/lib/types";

function buildScore(overrides: Partial<CollaboratorScore> = {}): CollaboratorScore {
  return {
    id: 1,
    collaborator_id: 1,
    collaborator_name: "Colaborador Teste",
    role: "technician",
    regional: "PVH",
    is_registered: true,
    service_orders_count: 10,
    gross_points: 100,
    penalty_points: 0,
    net_points: 100,
    health_multiplier: 1,
    health_status: "ok",
    final_points: 100,
    estimated_payment: 500,
    balance_adjustment_points: 0,
    balance_after: 0,
    scored_service_orders: 10,
    unscored_service_orders: 0,
    penalized_service_orders: 0,
    warranty_service_orders: 0,
    recurrence_service_orders: 0,
    rescheduled_service_orders: 0,
    pending_service_orders: 0,
    sla_out_service_orders: 0,
    annulled_service_orders: 0,
    diagnosis_penalized_service_orders: 0,
    manual_review_service_orders: 0,
    diagnosis_unmapped_service_orders: 0,
    ...overrides
  };
}

function buildHealth(overrides: Partial<RegionalHealthItem> = {}): RegionalHealthItem {
  return {
    regional: "PVH",
    health_status: "ok",
    sla_rate: 95,
    recurrence_rate: 5,
    recurrence_orders: 5,
    multiplier: 1,
    total_orders: 100,
    pending_orders: 0,
    rescheduled_orders: 0,
    cpk_status: null,
    cpk_adjustment: 0,
    ...overrides
  };
}

function buildSummary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    run: {
      id: 1,
      reference_month: 7,
      reference_year: 2026,
      regional: null,
      point_value: 10,
      source_import_id: null,
      source_filename: null,
      rules_version_id: null,
      result_summary: null,
      config_snapshot: null,
      status: "draft",
      status_changed_at: null,
      status_changed_by: null,
      status_note: null,
      approved_at: null,
      approved_by: null,
      paid_at: null,
      paid_by: null,
      executed_at: null,
      executed_by: null,
      created_at: "2026-07-01T00:00:00Z",
      scores: []
    },
    cards: {
      total_collaborators: 1,
      total_service_orders: 10,
      scored_service_orders: 10,
      unscored_service_orders: 0,
      penalized_service_orders: 0,
      warranty_service_orders: 0,
      recurrence_service_orders: 0,
      rescheduled_service_orders: 0,
      pending_service_orders: 0,
      sla_out_service_orders: 0,
      annulled_service_orders: 0,
      diagnosis_penalized_service_orders: 0,
      manual_review_service_orders: 0,
      diagnosis_unmapped_service_orders: 0,
      closure_pending_service_orders: 0,
      gross_points: 100,
      penalty_points: 0,
      lost_points: 0,
      lost_payment: 0,
      unscored_estimated_payment: 0,
      final_points: 100,
      estimated_payment: 500,
      orders_without_scoring_rule: 0
    },
    ranking: [buildScore()],
    leadership_bonus: {
      calculation_run_id: 1,
      results: [],
      pending_collaborators: [],
      total_base_amount: 0,
      total_bonus_amount: 0
    },
    penalty_distribution: [],
    health_by_regional: [buildHealth()],
    point_value: 10,
    cost_by_regional: [],
    cost_by_group: [],
    cost_by_subject: [],
    cost_by_collaborator: [],
    top_penalized_subjects: [],
    top_scoring_subjects: [],
    top_unmapped_subjects: [],
    ...overrides
  };
}

describe("deriveClosureData", () => {
  it("marca o fechamento como liberado quando não há pendências", () => {
    const summary = buildSummary({
      cards: { ...buildSummary().cards, unscored_service_orders: 0, diagnosis_unmapped_service_orders: 0 }
    });

    const { closure } = deriveClosureData(summary, [], 1);

    expect(closure.ready).toBe(true);
    expect(closure.pendingCount).toBe(0);
    expect(closure.isClosed).toBe(false);
  });

  it("marca o fechamento com pendência quando há O.S sem regra, diagnóstico sem regra ou colaborador pendente", () => {
    const summary = buildSummary({
      cards: { ...buildSummary().cards, unscored_service_orders: 3, diagnosis_unmapped_service_orders: 2 },
      leadership_bonus: {
        calculation_run_id: 1,
        results: [],
        pending_collaborators: [
          { collaborator_id: 9, name: "Fulano", regional: "PVH", suggested_regional: "PVH", service_orders_count: 4, estimated_payment: 120 }
        ],
        total_base_amount: 0,
        total_bonus_amount: 0
      }
    });

    const { closure } = deriveClosureData(summary, [], 1);

    expect(closure.ready).toBe(false);
    expect(closure.pendingCount).toBe(6);
    expect(closure.pendingItems.map((item) => item.value)).toEqual([3, 2, 1]);
  });

  it("marca isClosed quando o status é pago ou cancelado", () => {
    const paid = buildSummary({ run: { ...buildSummary().run!, status: "paid" } });
    const cancelled = buildSummary({ run: { ...buildSummary().run!, status: "cancelled" } });
    const draft = buildSummary({ run: { ...buildSummary().run!, status: "draft" } });

    expect(deriveClosureData(paid, [], 1).closure.isClosed).toBe(true);
    expect(deriveClosureData(cancelled, [], 1).closure.isClosed).toBe(true);
    expect(deriveClosureData(draft, [], 1).closure.isClosed).toBe(false);
  });

  it("calcula o total financeiro somando técnicos e liderança", () => {
    const summary = buildSummary({
      cards: { ...buildSummary().cards, estimated_payment: 1000 },
      leadership_bonus: {
        calculation_run_id: 1,
        results: [],
        pending_collaborators: [],
        total_base_amount: 0,
        total_bonus_amount: 250
      }
    });

    const { closureFinancials } = deriveClosureData(summary, [], 1);

    expect(closureFinancials.technicianAmount).toBe(1000);
    expect(closureFinancials.leadershipAmount).toBe(250);
    expect(closureFinancials.totalAmount).toBe(1250);
  });

  it("calcula o desconto de garantia a partir dos ajustes negativos de saldo", () => {
    const summary = buildSummary({
      ranking: [
        buildScore({ collaborator_id: 1, balance_adjustment_points: -10 }),
        buildScore({ collaborator_id: 2, balance_adjustment_points: -5 }),
        buildScore({ collaborator_id: 3, balance_adjustment_points: 0 }),
        buildScore({ collaborator_id: 4, balance_adjustment_points: 8 })
      ]
    });

    const { closureBalanceImpact } = deriveClosureData(summary, [], 1);

    expect(closureBalanceImpact.collaboratorCount).toBe(2);
    expect(closureBalanceImpact.points).toBe(-15);
  });

  it("filtra a saúde por regional e recalcula o contexto do gráfico quando há regionais selecionadas", () => {
    const summary = buildSummary({
      health_by_regional: [
        buildHealth({ regional: "PVH", total_orders: 100, recurrence_orders: 10 }),
        buildHealth({ regional: "JIP", total_orders: 50, recurrence_orders: 5 })
      ]
    });

    const allRegionals = deriveClosureData(summary, [], 3);
    expect(allRegionals.chartHealth).toHaveLength(2);
    expect(allRegionals.chartContext.serviceOrders).toBe(150);
    expect(allRegionals.chartContext.recurrenceOrders).toBe(15);
    expect(allRegionals.chartContext.recurrenceRate).toBeCloseTo(10);
    expect(allRegionals.chartContext.collaborators).toBe(3);
    expect(allRegionals.chartContext.label).toBe("Todas as regionais");

    const filtered = deriveClosureData(summary, ["PVH"], 3);
    expect(filtered.chartHealth).toHaveLength(1);
    expect(filtered.chartHealth[0].regional).toBe("PVH");
    expect(filtered.chartContext.serviceOrders).toBe(100);
    expect(filtered.chartContext.recurrenceOrders).toBe(10);
    expect(filtered.chartContext.recurrenceRate).toBeCloseTo(10);
    expect(filtered.chartContext.label).toBe("PVH");

    const multiple = deriveClosureData(summary, ["PVH", "JIP"], 3);
    expect(multiple.chartContext.label).toBe("2 regionais");
  });
});
