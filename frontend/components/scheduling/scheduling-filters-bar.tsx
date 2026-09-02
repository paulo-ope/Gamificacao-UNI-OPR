"use client";

import { Filter, Loader2, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { SchedulingFilterOptions, SchedulingFilterState, SchedulingSavedFilter } from "@/lib/scheduling-api";

import { SchedulingMultiSelect } from "./scheduling-multi-select";
import { SchedulingSavedViewsPopover } from "./scheduling-saved-views-popover";

// Resumo visual de quais filtros de recorte estão ligados - achado real de 2026-08-24: a tela não
// tinha nenhuma indicação de "quantos filtros estão ativos", diferente do padrão de Operações
// (FilterSummary em operations-filter-panel.tsx).
const ACTIVE_FILTER_CHIPS: Array<{ key: string; label: string; get: (filters: SchedulingFilterState) => unknown[] }> = [
  { key: "filial", label: "Filial", get: (filters) => filters.filial_ids },
  { key: "setor", label: "Setor", get: (filters) => filters.setor_ids },
  { key: "assunto", label: "Assunto", get: (filters) => filters.assunto_ids },
  { key: "operador", label: "Operador", get: (filters) => filters.operator_ids },
  { key: "tecnico", label: "Técnico", get: (filters) => filters.technician_ids },
];

// Barra de filtros secundária do cockpit - recolhida por padrão de propósito (pedido do usuário
// 2026-08-31: "configurações, equipe e backfill não devem competir com a operação diária"; o mesmo
// vale pros filtros de recorte, que a maioria dos supervisores nunca precisa tocar no dia a dia).
export function SchedulingFiltersBar({
  filters,
  options,
  loading,
  savedFilters,
  selectedSavedFilterId,
  filterName,
  savedFilterVisibility,
  canManageFilters,
  canManageGlobalViews,
  onChange,
  onApply,
  onSelectSavedFilter,
  onNameChange,
  onVisibilityChange,
  onSave,
  onUpdate,
  onDelete,
}: {
  filters: SchedulingFilterState;
  options: SchedulingFilterOptions;
  loading: boolean;
  savedFilters: SchedulingSavedFilter[];
  selectedSavedFilterId: number | null;
  filterName: string;
  savedFilterVisibility: "personal" | "global";
  canManageFilters: boolean;
  canManageGlobalViews: boolean;
  onChange: (next: SchedulingFilterState) => void;
  onApply: () => void;
  onSelectSavedFilter: (id: number | null) => void;
  onNameChange: (value: string) => void;
  onVisibilityChange: (value: "personal" | "global") => void;
  onSave: () => void;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const activeCount = ACTIVE_FILTER_CHIPS.reduce((total, { get }) => total + (get(filters).length ? 1 : 0), 0);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-slate-200 bg-white px-4 py-2 lg:px-7">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setExpanded((current) => !current)}>
          <Filter className="h-3.5 w-3.5" /> Filtros{activeCount ? ` (${activeCount})` : ""}
        </Button>
        {ACTIVE_FILTER_CHIPS.map(({ key, label, get }) => {
          const count = get(filters).length;
          if (!count) return null;
          return (
            <Badge key={key} className="border-slate-200 bg-slate-100 text-[11px] text-slate-700">
              {label}: {count}
            </Badge>
          );
        })}
        {activeCount ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[11px] text-blue-700"
            onClick={() =>
              onChange({
                ...filters,
                filial_ids: [],
                setor_ids: [],
                assunto_ids: [],
                operator_ids: [],
                technician_ids: [],
              })
            }
          >
            <X className="h-3 w-3" /> Limpar
          </Button>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <SchedulingSavedViewsPopover
            savedFilters={savedFilters}
            selectedSavedFilterId={selectedSavedFilterId}
            filterName={filterName}
            visibility={savedFilterVisibility}
            canManageViews={canManageFilters}
            canCreateGlobalViews={canManageGlobalViews}
            onSelect={onSelectSavedFilter}
            onNameChange={onNameChange}
            onVisibilityChange={onVisibilityChange}
            onSave={onSave}
            onUpdate={onUpdate}
            onDelete={onDelete}
          />
        </div>
      </div>

      {expanded ? (
        <div className="mt-2 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-2">
          <SchedulingMultiSelect
            label="Filial"
            options={options.filiais}
            selected={filters.filial_ids}
            onChange={(next) => onChange({ ...filters, filial_ids: next as string[] })}
          />
          <SchedulingMultiSelect
            label="Setor"
            options={options.setores}
            selected={filters.setor_ids}
            onChange={(next) => onChange({ ...filters, setor_ids: next as string[] })}
          />
          <SchedulingMultiSelect
            label="Assunto"
            options={options.assuntos}
            selected={filters.assunto_ids}
            onChange={(next) => onChange({ ...filters, assunto_ids: next as string[] })}
          />
          <SchedulingMultiSelect
            label="Operador"
            options={options.operators}
            selected={filters.operator_ids}
            onChange={(next) => onChange({ ...filters, operator_ids: next as number[] })}
            showTeamFilter
          />
          <SchedulingMultiSelect
            label="Técnico"
            options={options.technicians}
            selected={filters.technician_ids}
            onChange={(next) => onChange({ ...filters, technician_ids: next as number[] })}
          />
          <div>
            <label className="mb-1 block text-[11px] font-medium text-slate-500">Contagem (rankings)</label>
            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
              {([["all_events", "Cada ação"], ["distinct_orders", "O.S. distintas"]] as const).map(([mode, label]) => (
                <Button
                  key={mode}
                  type="button"
                  size="sm"
                  variant={filters.count_mode === mode ? "default" : "ghost"}
                  className="h-8 px-2.5 text-xs"
                  onClick={() => onChange({ ...filters, count_mode: mode })}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
          <Button type="button" size="sm" onClick={onApply} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Aplicar
          </Button>
        </div>
      ) : null}
    </div>
  );
}
