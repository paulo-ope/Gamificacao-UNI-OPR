"use client";

import { useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { formatInteger } from "@/lib/format";
import { operationsApi, type OperationBranchCapacitySummaryItem, type OperationFilterState } from "@/lib/operations-api";

function tierColor(item: OperationBranchCapacitySummaryItem): string | undefined {
  if (item.tier === "below") return undefined;
  if (item.tier === "good") return item.good_color;
  if (item.tier === "great") return item.great_color;
  return item.excellent_color;
}

// Indicador gerencial de capacidade por filial - paralelo às metas por modelo de equipe que já
// pintam cada célula do calendário (ver docstring de `OperationBranchCapacity` no backend). Só
// mostra filiais com capacidade cadastrada (Config > Capacidade por filial) - sem cadastro, não
// tem contra o que comparar o realizado.
export function OperationsCapacitySummaryCards({ filters }: { filters: OperationFilterState }) {
  const [items, setItems] = useState<OperationBranchCapacitySummaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    operationsApi
      .capacitySummary(filters)
      .then((result) => {
        if (active) setItems(result.items);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Falha ao carregar a capacidade por filial.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters]);

  if (loading) return null;
  if (error) return <p className="text-xs text-red-600">{error}</p>;
  if (!items.length) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Capacidade por filial">
      {items.map((item) => (
        <Card key={item.regional} className="min-w-0 rounded-2xl border-slate-200 shadow-sm">
          <CardContent className="grid gap-2 p-4">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 truncate text-sm font-semibold text-slate-900">{item.regional}</p>
              <span
                className="shrink-0 rounded-full border border-black/10 px-2 py-0.5 text-[10px] font-semibold text-slate-800"
                style={{ backgroundColor: tierColor(item) }}
              >
                {item.tier_label}
              </span>
            </div>
            <p className="text-2xl font-semibold text-slate-950">{formatInteger(item.realized)}</p>
            <p className="text-[11px] text-slate-500">
              Boa {formatInteger(item.good_threshold)} · Ótima {formatInteger(item.great_threshold)} · Excelente{" "}
              {formatInteger(item.excellent_threshold)}
            </p>
            <p className="text-[11px] text-slate-500">
              {item.collaborators_count} colaborador(es) · média {item.average_per_collaborator} por colaborador
            </p>
            {item.difference_to_next_tier !== null ? (
              <p className="text-[11px] text-slate-500">
                Faltam <span className="font-semibold text-slate-700">{formatInteger(item.difference_to_next_tier)}</span> para
                a próxima faixa
              </p>
            ) : (
              <p className="text-[11px] font-medium text-emerald-700">Já na faixa máxima (Excelente)</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
