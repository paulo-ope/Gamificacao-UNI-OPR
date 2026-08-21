"use client";

import { BarChart3 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ManagementCaseDiagnostics } from "@/lib/types";
import { CASE_STATUS_LABELS } from "./case-format-helpers";

export function ManagementCaseDiagnosticsPanel() {
  const [diagnostics, setDiagnostics] = useState<ManagementCaseDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ regional: "", status: "", only_open: true });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDiagnostics(
        await api.managementCaseDiagnostics({
          regional: filters.regional || undefined,
          status: filters.status || undefined,
          only_open: filters.only_open || undefined,
        })
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar o diagnóstico.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="grid gap-4">
      <StatusToast error={error} message={null} onDismissError={() => setError(null)} onDismissMessage={() => undefined} />
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <BarChart3 className="h-4 w-4 text-violet-600" />
        <p className="text-sm text-slate-600">
          Ranking de <strong>{diagnostics?.total_cases ?? 0}</strong> caso(s) no recorte abaixo.
        </p>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-600">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 rounded border-slate-300"
            checked={filters.only_open}
            onChange={(event) => setFilters({ ...filters, only_open: event.target.checked })}
          />
          Somente em aberto
        </label>
        <Input
          className="h-9 w-48"
          placeholder="Filtrar por regional"
          value={filters.regional}
          onChange={(event) => setFilters({ ...filters, regional: event.target.value })}
        />
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm"
          value={filters.status}
          onChange={(event) => setFilters({ ...filters, status: event.target.value })}
        >
          <option value="">Todos os status</option>
          {Object.entries(CASE_STATUS_LABELS)
            .filter(([value]) => value !== "overdue")
            .map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
        </select>
      </div>
      {loading ? (
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((item) => <div key={item} className="h-64 animate-pulse rounded-xl border border-slate-200 bg-white" />)}
        </div>
      ) : diagnostics ? (
        <div className="grid gap-4 md:grid-cols-3">
          {/* Ranking por motivo primeiro - pedido do usuário em 2026-08-20: os motivos
             pré-cadastrados (Ausência, Equipe incompleta etc.) são o diagnóstico que mais importa
             pra matriz decidir onde agir, não só "quem tem mais caso". */}
          <DiagnosticsColumn title="Ranking por motivo" buckets={diagnostics.by_reason} highlight />
          <DiagnosticsColumn title="Por colaborador" buckets={diagnostics.by_responsible} />
          <DiagnosticsColumn title="Por regional" buckets={diagnostics.by_regional} />
        </div>
      ) : (
        <p className="text-sm text-slate-500">Sem dados para este recorte.</p>
      )}
    </div>
  );
}

function DiagnosticsColumn({
  title,
  buckets,
  highlight = false,
}: {
  title: string;
  buckets: { key: string; label: string; total: number; open_cases: number; overdue_cases: number }[];
  highlight?: boolean;
}) {
  return (
    <div className={cn("rounded-xl border p-3", highlight ? "border-violet-200 bg-violet-50/40 md:col-span-1" : "border-slate-200 bg-white")}>
      <p className={cn("text-[11px] font-semibold uppercase tracking-wide", highlight ? "text-violet-700" : "text-slate-500")}>{title}</p>
      {buckets.length ? (
        <div className="mt-2 grid gap-1.5">
          {buckets.map((bucket) => (
            <div key={bucket.key} className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate text-slate-700" title={bucket.label}>
                {bucket.label}
              </span>
              <span className="flex shrink-0 items-center gap-1.5 tabular-nums">
                <span className="font-semibold text-slate-900">{bucket.total}</span>
                {bucket.overdue_cases > 0 ? (
                  <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
                    {bucket.overdue_cases} atrasado(s)
                  </span>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-400">Sem dados.</p>
      )}
    </div>
  );
}
