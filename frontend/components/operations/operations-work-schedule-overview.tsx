"use client";

import { useState } from "react";
import { ClockAlert, SlidersHorizontal, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { MultiSelect } from "@/components/ui/multi-select";
import type { OperationWorkScheduleOverview } from "@/lib/operations-api";

export function OperationsWorkScheduleOverview({
  data,
  selectedModelIds,
  onModelIdsChange,
}: {
  data: OperationWorkScheduleOverview;
  selectedModelIds: number[];
  onModelIdsChange: (ids: number[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const modelNames = new Map(
    data.available_models.map((item) => [String(item.id), item.name]),
  );
  const options = data.available_models.map((item) => String(item.id));
  const insideSchedule = Math.max(0, data.classified - data.outside_schedule);

  return (
    <section
      className="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
      aria-label="Conformidade de jornada"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="rounded-lg bg-amber-50 p-2 text-amber-700">
            <ClockAlert className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-slate-950">
              Conformidade de jornada
            </h3>
            <p className="text-xs text-slate-500">
              {data.outside_schedule} finalizações fora da jornada •{" "}
              {insideSchedule} dentro do horário permitido
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          className="h-9"
          onClick={() => setOpen((current) => !current)}
        >
          {open ? <X className="h-4 w-4" /> : <SlidersHorizontal className="h-4 w-4" />}
          {open ? "Fechar" : "Ver detalhes"}
        </Button>
      </div>
      {open ? (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="mb-4 w-full sm:w-72">
            <p className="mb-1 text-[11px] font-medium text-slate-600">
              Modelo de equipe
            </p>
            <MultiSelect
              values={selectedModelIds.map(String)}
              options={options}
              placeholder="Todos os modelos"
              ariaLabel="Selecionar modelos para a análise de jornada"
              formatOption={(value) => modelNames.get(value) || value}
              onChange={(values) => onModelIdsChange(values.map(Number))}
            />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-3">
              <p className="text-[10px] font-semibold text-slate-500">
                Fora da jornada
              </p>
              <p className="mt-1 text-xl font-bold text-slate-950">
                {data.outside_schedule}
              </p>
              <p className="text-[10px] text-slate-500">
                {data.outside_rate === null
                  ? "Sem base classificada"
                  : `${data.outside_rate.toLocaleString("pt-BR", {
                      maximumFractionDigits: 1,
                    })}% das classificadas`}
              </p>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <p className="text-[10px] font-semibold text-slate-500">
                Dentro do horário
              </p>
              <p className="mt-1 text-xl font-bold text-slate-950">
                {insideSchedule}
              </p>
              <p className="text-[10px] text-slate-500">
                Conforme jornada do modelo
              </p>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <p className="text-[10px] font-semibold text-slate-500">
                Antes do início
              </p>
              <p className="mt-1 text-xl font-bold text-slate-950">
                {data.before_start}
              </p>
              <p className="text-[10px] text-slate-500">
                Fechamentos antes da jornada
              </p>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <p className="text-[10px] font-semibold text-slate-500">
                Depois do término
              </p>
              <p className="mt-1 text-xl font-bold text-slate-950">
                {data.after_end}
              </p>
              <p className="text-[10px] text-slate-500">
                Depois do término configurado
              </p>
            </div>
          </div>
          {data.by_model.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {data.by_model.map((item) => (
                <span
                  key={item.model_id}
                  className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-600"
                >
                  <strong className="text-slate-900">{item.model_name}</strong>{" "}
                  • {item.outside_schedule}/{item.completed}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
