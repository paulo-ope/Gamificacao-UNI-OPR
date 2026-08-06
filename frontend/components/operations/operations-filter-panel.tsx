"use client";

import * as Popover from "@radix-ui/react-popover";
import {
  Bookmark,
  Check,
  ChevronDown,
  Clock3,
  MoreHorizontal,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { InfoHint } from "@/components/gamification/info-hint";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { DateRangePicker, type DateRangePreset } from "@/components/ui/date-range-picker";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multi-select";
import { AppRadio } from "@/components/ui/radio";
import type {
  OperationFilterState,
  OperationFilters,
  OperationPeriod,
  OperationSavedFilter,
} from "@/lib/operations-api";

function toDateValue(value: Date) {
  return value.toISOString().slice(0, 10);
}

function parseLocalDateForPreset(value?: string | null) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year, month - 1, day, 12));
}

type ArrayFilterKey = Exclude<
  keyof OperationFilterState,
  | "date_from"
  | "date_to"
  | "search"
  | "responsible_mode"
  | "closed_time_from"
  | "closed_time_to"
  | "custom_window_start_weekday"
  | "custom_window_start_time"
  | "custom_window_end_weekday"
  | "custom_window_end_time"
>;
type FilterDefinition = {
  key: ArrayFilterKey;
  label: string;
  options: keyof OperationFilters;
};
type ActiveChip = { id: string; label: string; remove: () => void };

const mainFilters: FilterDefinition[] = [
  { key: "regionals", label: "Regional", options: "regionals" },
  { key: "team_models", label: "Modelo de equipe", options: "team_models" },
  { key: "os_types", label: "Tipo geral", options: "os_types" },
  { key: "subjects", label: "Assunto", options: "subjects" },
  { key: "responsibles", label: "Responsável", options: "responsibles" },
];

const advancedGroups: Array<{
  title: string;
  description: string;
  fields: FilterDefinition[];
}> = [
  {
    title: "Localização",
    description: "Empresa, UF e cidade.",
    fields: [
      { key: "companies", label: "Empresa / filial", options: "companies" },
      { key: "states", label: "UF", options: "states" },
      { key: "cities", label: "Cidade", options: "cities" },
    ],
  },
  {
    title: "Ordem de serviço",
    description: "Status, prioridade e diagnóstico.",
    fields: [
      { key: "statuses", label: "Status", options: "statuses" },
      { key: "priorities", label: "Prioridade", options: "priorities" },
      { key: "diagnoses", label: "Diagnóstico", options: "diagnoses" },
    ],
  },
  {
    title: "Cliente",
    description: "Tipo de pessoa e contrato.",
    fields: [
      { key: "person_types", label: "Tipo de pessoa", options: "person_types" },
      {
        key: "contract_types",
        label: "Tipo de contrato",
        options: "contract_types",
      },
    ],
  },
  {
    title: "Operação",
    description: "Estrutura, origem e classificações internas.",
    fields: [
      { key: "departments", label: "Departamento", options: "departments" },
      { key: "sectors", label: "Setor", options: "sectors" },
      { key: "creators", label: "Criador da O.S.", options: "creators" },
      { key: "projects", label: "Projeto", options: "projects" },
      { key: "pops", label: "POP", options: "pops" },
    ],
  },
  {
    title: "SLA",
    description: "Situação e horário de fechamento.",
    fields: [
      {
        key: "sla_statuses",
        label: "Situação do SLA",
        options: "sla_statuses",
      },
    ],
  },
  {
    title: "Dia da semana",
    description: "Recorte por dia da semana de abertura ou fechamento.",
    fields: [
      {
        key: "opened_weekdays",
        label: "Dia da semana (abertura)",
        options: "opened_weekdays",
      },
      {
        key: "closed_weekdays",
        label: "Dia da semana (fechamento)",
        options: "closed_weekdays",
      },
    ],
  },
  {
    title: "Janela personalizada",
    description:
      "Recorte contínuo de dia+hora (ex.: sábado 12h até domingo 23h59), ignora o filtro de Setor. No Calendário, os dias exibidos são sempre pela data de fechamento - marque \"Fechamento\" aqui pra restringir o calendário à janela; usar só \"Abertura\" filtra quais O.S. entram, mas elas continuam aparecendo espalhadas pelos dias em que fecharam.",
    fields: [],
  },
];

const WEEKDAY_LABELS: Record<string, string> = {
  monday: "Segunda-feira",
  tuesday: "Terça-feira",
  wednesday: "Quarta-feira",
  thursday: "Quinta-feira",
  friday: "Sexta-feira",
  saturday: "Sábado",
  sunday: "Domingo",
};

const WEEKDAY_OPTIONS: Array<[string, string]> = Object.entries(WEEKDAY_LABELS);

const filterLabels: Array<[ArrayFilterKey, string]> = [
  ...mainFilters,
  ...advancedGroups.flatMap((group) => group.fields),
].map((item) => [item.key, item.label]);
const advancedKeys = new Set(
  advancedGroups.flatMap((group) => group.fields.map((field) => field.key)),
);

function filterOptionLabel(key: ArrayFilterKey, value: string) {
  if (key === "sla_statuses") {
    if (value === "on_time") return "No prazo";
    if (value === "out_of_time") return "Fora do prazo";
    return "Não identificada";
  }
  if (key === "opened_weekdays" || key === "closed_weekdays") {
    return WEEKDAY_LABELS[value] || value;
  }
  return value;
}

function lastUpdateLabel(value: string | null) {
  if (!value) return "Ainda não sincronizado";
  const formatted = new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
  return `Atualizado em ${formatted.replace(",", " às")}`;
}

function FilterField({
  filterKey,
  label,
  values,
  options,
  onChange,
}: {
  filterKey: ArrayFilterKey;
  label: string;
  values: string[];
  options: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <label className="grid min-w-0 gap-1.5 text-[11px] font-medium text-slate-600">
      {label}
      <MultiSelect
        ariaLabel={`Filtrar por ${label}`}
        values={values}
        options={options}
        formatOption={(value) => filterOptionLabel(filterKey, value)}
        onChange={onChange}
      />
    </label>
  );
}

function FilterConceptCard() {
  return (
    <div className="mt-3 rounded-2xl border border-slate-200 bg-[linear-gradient(135deg,#f8fafc_0%,#eff6ff_55%,#ffffff_100%)] p-3 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-blue-700">
            Leitura dos indicadores
          </p>
          <p className="mt-1 text-sm font-semibold text-slate-900">
            Alguns painéis preservam a lógica operacional da entrada da fila.
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            Passe o mouse ou foque nos itens para entender por que certos
            números não reagem a todos os filtros.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm">
            Aberturas
            <InfoHint
              ariaLabel="Ajuda sobre o indicador de aberturas"
              side="left"
              title="Conceito"
              description="Aberturas medem a entrada da demanda operacional. Por isso, elas podem ignorar filtros de responsável: a O.S. nasce antes de pertencer a um técnico específico."
            />
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm">
            Setor padrão
            <InfoHint
              ariaLabel="Ajuda sobre o escopo padrão de setores"
              side="left"
              title="Escopo atual"
              description="O módulo inicia com os 3 setores técnicos prioritários selecionados para manter o recorte operacional consistente. Eles só saem quando você limpa o próprio filtro de setor."
            />
          </span>
        </div>
      </div>
    </div>
  );
}

function FilterSummary({
  chips,
  onClearAll,
}: {
  chips: ActiveChip[];
  onClearAll: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!chips.length) return null;
  const visible = chips.slice(0, 3);
  const remaining = chips.length - visible.length;
  return (
    <div className="mt-2 flex min-h-7 flex-wrap items-center gap-1.5 text-xs text-slate-500">
      <span className="font-medium text-slate-700">
        {chips.length} filtros aplicados
      </span>
      {visible.map((chip) => (
        <button
          key={chip.id}
          type="button"
          onClick={chip.remove}
          className="inline-flex max-w-48 items-center gap-1 truncate rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-700 hover:bg-slate-200"
          title={`Remover ${chip.label}`}
        >
          <span className="truncate">{chip.label}</span>
          <X className="h-3 w-3 shrink-0" />
        </button>
      ))}
      {remaining > 0 ? (
        <span className="text-[10px] text-slate-500">+{remaining} filtros</span>
      ) : null}
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            type="button"
            className="text-[11px] font-medium text-blue-700 hover:text-blue-900"
          >
            Ver filtros
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            align="start"
            sideOffset={8}
            className="z-50 w-[min(26rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-3 shadow-xl"
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-slate-900">
                Filtros aplicados
              </p>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-slate-600"
                onClick={() => {
                  onClearAll();
                  setOpen(false);
                }}
              >
                Limpar tudo
              </Button>
            </div>
            <div className="flex max-h-52 flex-wrap content-start gap-1.5 overflow-y-auto pr-1">
              {chips.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  onClick={chip.remove}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border border-blue-100 bg-blue-50 px-2 py-1 text-[10px] text-blue-800 hover:border-blue-300"
                  title="Remover filtro"
                >
                  <span className="truncate">{chip.label}</span>
                  <X className="h-3 w-3 shrink-0" />
                </button>
              ))}
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}

function SavedViewsPopover({
  savedFilters,
  selectedSavedFilterId,
  filterName,
  visibility,
  canManageViews,
  canCreateGlobalViews,
  onSelect,
  onNameChange,
  onVisibilityChange,
  onSave,
  onUpdate,
  onDelete,
}: {
  savedFilters: OperationSavedFilter[];
  selectedSavedFilterId: number | null;
  filterName: string;
  visibility: "personal" | "global";
  canManageViews: boolean;
  canCreateGlobalViews: boolean;
  onSelect: (id: number | null) => void;
  onNameChange: (value: string) => void;
  onVisibilityChange: (value: "personal" | "global") => void;
  onSave: () => void;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmUpdate, setConfirmUpdate] = useState(false);
  const active = savedFilters.find((item) => item.id === selectedSavedFilterId);
  const visible = savedFilters.filter((item) =>
    item.name
      .toLocaleLowerCase("pt-BR")
      .includes(search.toLocaleLowerCase("pt-BR")),
  );
  const choose = (id: number) => {
    onSelect(id);
    setCreating(false);
    setRenaming(false);
    setConfirmDelete(false);
    setConfirmUpdate(false);
    setOpen(false);
  };
  const saveNew = () => {
    onSave();
    setCreating(false);
  };
  const update = () => {
    onUpdate();
    setRenaming(false);
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          type="button"
          variant="outline"
          className="h-10 shrink-0 whitespace-nowrap"
        >
          <Bookmark className="h-4 w-4" />
          <span className="max-w-36 truncate">
            {active ? `Visão: ${active.name}` : "Visões"}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-[min(25rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-3 shadow-xl"
        >
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900">
                Visões salvas
              </p>
              <p className="text-[11px] text-slate-500">
                Combinações de filtros reutilizáveis.
              </p>
            </div>
            {active && canManageViews ? (
              <Popover.Root>
                <Popover.Trigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    aria-label="Opções da visão"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content
                    align="end"
                    sideOffset={6}
                    className="z-[60] w-44 rounded-lg border border-slate-200 bg-white p-1 shadow-lg"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmUpdate(true);
                        setRenaming(false);
                        setConfirmDelete(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Atualizar visão
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRenaming(true);
                        setCreating(false);
                        setConfirmUpdate(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Renomear e atualizar
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmDelete(true);
                        setConfirmUpdate(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-red-700 hover:bg-red-50"
                    >
                      Excluir visão
                    </button>
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            ) : null}
          </div>
          {active ? (
            <button
              type="button"
              onClick={() => {
                onSelect(null);
                onVisibilityChange("personal");
                setCreating(false);
                setRenaming(false);
                setConfirmDelete(false);
                setConfirmUpdate(false);
              }}
              className="mb-2 text-[11px] font-medium text-blue-700 hover:text-blue-900"
            >
              Retirar visão selecionada
            </button>
          ) : null}
          <label className="relative mb-2 block">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar visão"
              className="h-9 pl-8 text-xs"
            />
          </label>
          <div className="max-h-44 space-y-1 overflow-y-auto pr-1">
            {visible.length ? (
              visible.map((saved) => (
                <button
                  key={saved.id}
                  type="button"
                  onClick={() => choose(saved.id)}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs ${saved.id === selectedSavedFilterId ? "bg-blue-50 text-blue-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  <span className="min-w-0 truncate">
                    {saved.name}
                    <span className="ml-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase text-slate-500">
                      {saved.visibility === "global" ? "Global" : "Pessoal"}
                    </span>
                  </span>
                  {saved.id === selectedSavedFilterId ? (
                    <Check className="h-3.5 w-3.5 shrink-0" />
                  ) : null}
                </button>
              ))
            ) : (
              <p className="px-2 py-4 text-center text-xs text-slate-500">
                Nenhuma visão encontrada.
              </p>
            )}
          </div>
          {canManageViews ? <div className="mt-3 border-t border-slate-100 pt-3">
            {creating || renaming ? (
              <div className="space-y-2">
                <Input
                  value={filterName}
                  maxLength={120}
                  placeholder="Nome da visão"
                  onChange={(event) => onNameChange(event.target.value)}
                  className="h-9 text-xs"
                />
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Tipo da visão
                  </p>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    <label className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                      <AppRadio
                        checked={visibility === "personal"}
                        onSelect={() => onVisibilityChange("personal")}
                        ariaLabel="Pessoal"
                      />
                      Pessoal
                    </label>
                    {canCreateGlobalViews || active?.visibility === "global" ? (
                      <label className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                        <AppRadio
                          checked={visibility === "global"}
                          disabled={!canCreateGlobalViews && active?.visibility !== "global"}
                          onSelect={() => onVisibilityChange("global")}
                          ariaLabel="Global"
                        />
                        Global
                      </label>
                    ) : (
                      <div className="rounded-md bg-white px-2 py-1.5 text-xs text-slate-400">
                        Global indisponível para seu perfil
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 text-xs"
                    onClick={() => {
                      setCreating(false);
                      setRenaming(false);
                      if (!active) onVisibilityChange("personal");
                    }}
                  >
                    Cancelar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="h-8 text-xs"
                    disabled={!filterName.trim()}
                    onClick={creating ? saveNew : update}
                  >
                    {creating ? "Salvar visão" : "Atualizar visão"}
                  </Button>
                </div>
              </div>
            ) : confirmDelete ? (
              <div className="flex items-center justify-between gap-2 rounded-lg bg-red-50 p-2">
                <span className="text-[11px] text-red-800">
                  Excluir “{active?.name}”?
                </span>
                <div className="flex gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 text-[10px]"
                    onClick={() => setConfirmDelete(false)}
                  >
                    Cancelar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="h-7 bg-red-600 text-[10px] hover:bg-red-700"
                    onClick={() => {
                      onDelete();
                      setConfirmDelete(false);
                      setOpen(false);
                    }}
                  >
                    Excluir
                  </Button>
                </div>
              </div>
            ) : confirmUpdate ? (
              <div className="flex items-center justify-between gap-2 rounded-lg bg-blue-50 p-2">
                <span className="text-[11px] text-blue-800">
                  Atualizar “{active?.name}” com os filtros atuais?
                </span>
                <div className="flex gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 text-[10px]"
                    onClick={() => setConfirmUpdate(false)}
                  >
                    Cancelar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="h-7 text-[10px]"
                    onClick={() => {
                      onUpdate();
                      setConfirmUpdate(false);
                      setOpen(false);
                    }}
                  >
                    Atualizar
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 flex-1 text-xs"
                  onClick={() => {
                    onSelect(null);
                    onVisibilityChange("personal");
                    setCreating(true);
                    setRenaming(false);
                  }}
                >
                  Salvar como nova visão
                </Button>
              </div>
            )}
          </div> : null}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function OperationsFilterPanel({
  filters,
  options,
  period,
  savedFilters,
  selectedSavedFilterId,
  filterName,
  savedFilterVisibility,
  loading,
  importing,
  importProgress,
  lastUpdatedAt,
  canSyncIxc,
  syncScopeLabel,
  canManageViews,
  canCreateGlobalViews,
  datesIgnored,
  filterCount,
  onChange,
  onApply,
  onClearAll,
  onClearDates,
  onImport,
  onSelectSavedFilter,
  onFilterNameChange,
  onSavedFilterVisibilityChange,
  onSave,
  onUpdateSaved,
  onDeleteSaved,
}: {
  filters: OperationFilterState | null;
  options: OperationFilters;
  period: OperationPeriod | null;
  savedFilters: OperationSavedFilter[];
  selectedSavedFilterId: number | null;
  filterName: string;
  savedFilterVisibility: "personal" | "global";
  loading: boolean;
  importing: boolean;
  importProgress: string | null;
  lastUpdatedAt: string | null;
  canSyncIxc: boolean;
  syncScopeLabel: string;
  canManageViews: boolean;
  canCreateGlobalViews: boolean;
  datesIgnored: boolean;
  filterCount: number;
  onChange: (key: keyof OperationFilterState, value: string | string[]) => void;
  onApply: () => void;
  onClearAll: () => void;
  onClearDates: () => void;
  onImport: () => void;
  onSelectSavedFilter: (id: number | null) => void;
  onFilterNameChange: (name: string) => void;
  onSavedFilterVisibilityChange: (visibility: "personal" | "global") => void;
  onSave: () => void;
  onUpdateSaved: () => void;
  onDeleteSaved: () => void;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const activeChips = useMemo<ActiveChip[]>(() => {
    if (!filters) return [];
    const chips: ActiveChip[] = [];
    for (const [key, label] of filterLabels)
      for (const value of filters[key] || [])
        chips.push({
          id: `${key}:${value}`,
          label: `${label}: ${filterOptionLabel(key, value)}`,
          remove: () =>
            onChange(
              key,
              (filters[key] || []).filter((item) => item !== value),
            ),
        });
    if (filters.responsible_mode === "completed")
      chips.push({
        id: "responsible_mode",
        label: "Responsável: somente finalizadas",
        remove: () => onChange("responsible_mode", "all"),
      });
    if (filters.closed_time_from)
      chips.push({
        id: "closed_time_from",
        label: `Fechamento a partir de ${filters.closed_time_from}`,
        remove: () => onChange("closed_time_from", ""),
      });
    if (filters.closed_time_to)
      chips.push({
        id: "closed_time_to",
        label: `Fechamento até ${filters.closed_time_to}`,
        remove: () => onChange("closed_time_to", ""),
      });
    if (
      (filters.custom_window_basis || []).length &&
      filters.custom_window_start_weekday &&
      filters.custom_window_start_time &&
      filters.custom_window_end_weekday &&
      filters.custom_window_end_time
    ) {
      const basisLabel = (filters.custom_window_basis || [])
        .map((item) => (item === "opened" ? "abertura" : "fechamento"))
        .join(" ou ");
      chips.push({
        id: "custom_window",
        label: `Janela (${basisLabel}): ${WEEKDAY_LABELS[filters.custom_window_start_weekday]} ${filters.custom_window_start_time} até ${WEEKDAY_LABELS[filters.custom_window_end_weekday]} ${filters.custom_window_end_time}`,
        remove: () => {
          onChange("custom_window_basis", []);
          onChange("custom_window_start_weekday", "");
          onChange("custom_window_start_time", "");
          onChange("custom_window_end_weekday", "");
          onChange("custom_window_end_time", "");
        },
      });
    }
    return chips;
  }, [filters, onChange]);
  const advancedAppliedCount = activeChips.filter(
    (chip) =>
      advancedKeys.has(chip.id.split(":", 1)[0] as ArrayFilterKey) ||
      chip.id === "responsible_mode" ||
      chip.id === "custom_window" ||
      chip.id.startsWith("closed_time_"),
  ).length;
  const advancedPanel = (
    <div className="col-span-full max-h-[min(62vh,32rem)] overflow-y-auto rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
      <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-5">
        {advancedGroups.map((group) => {
          // Os campos são fixos por grupo (não somem quando a combinação atual de filtros zera
          // a contagem de O.S.) - filtrar por `options[...].length > 0` aqui escondia o campo (e
          // o card inteiro, quando todos os campos do grupo zeravam) toda vez que o filtro
          // aplicado não batia com nenhuma O.S., dando a impressão de painel quebrado.
          const fields = group.fields;
          const isOperation = group.title === "Operação";
          const isSla = group.title === "SLA";
          const isCustomWindow = group.title === "Janela personalizada";
          if (!fields.length && !isCustomWindow) return null;
          return (
            <fieldset
              key={group.title}
              className="min-w-0 space-y-3 rounded-lg bg-slate-50 p-3"
            >
              <legend className="px-1 text-xs font-semibold text-slate-800">
                {group.title}
              </legend>
              <p className="-mt-2 text-[10px] text-slate-500">
                {group.description}
              </p>
              {fields.map((field) => (
                <FilterField
                  key={field.key}
                  filterKey={field.key}
                  label={field.label}
                  values={filters?.[field.key] || []}
                  options={options[field.options]}
                  onChange={(value) => onChange(field.key, value)}
                />
              ))}
              {isOperation ? (
                <label className="grid gap-1.5 text-[11px] font-medium text-slate-600">
                  Opções de responsável
                  <select
                    value={filters?.responsible_mode || "all"}
                    onChange={(event) =>
                      onChange("responsible_mode", event.target.value)
                    }
                    className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-800"
                  >
                    <option value="all">Todas as O.S.</option>
                    <option value="completed">Somente O.S. finalizadas</option>
                  </select>
                </label>
              ) : null}
              {isSla ? (
                <div className="grid grid-cols-2 gap-2">
                  <label className="grid gap-1 text-[10px] text-slate-500">
                    Fechamento a partir de
                    <Input
                      type="time"
                      value={filters?.closed_time_from || ""}
                      onChange={(event) =>
                        onChange("closed_time_from", event.target.value)
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-[10px] text-slate-500">
                    Fechamento até
                    <Input
                      type="time"
                      value={filters?.closed_time_to || ""}
                      onChange={(event) =>
                        onChange("closed_time_to", event.target.value)
                      }
                    />
                  </label>
                </div>
              ) : null}
              {isCustomWindow ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-3 text-[11px] text-slate-600">
                    <label className="flex items-center gap-1.5">
                      <AppCheckbox
                        checked={(filters?.custom_window_basis || []).includes(
                          "opened",
                        )}
                        onCheckedChange={(checked) => {
                          const current = filters?.custom_window_basis || [];
                          const next = checked
                            ? [...current, "opened"]
                            : current.filter((item) => item !== "opened");
                          onChange("custom_window_basis", next);
                        }}
                        ariaLabel="Abertura"
                      />
                      Abertura
                    </label>
                    <label className="flex items-center gap-1.5">
                      <AppCheckbox
                        checked={(filters?.custom_window_basis || []).includes(
                          "closed",
                        )}
                        onCheckedChange={(checked) => {
                          const current = filters?.custom_window_basis || [];
                          const next = checked
                            ? [...current, "closed"]
                            : current.filter((item) => item !== "closed");
                          onChange("custom_window_basis", next);
                        }}
                        ariaLabel="Fechamento"
                      />
                      Fechamento
                    </label>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="grid gap-1 text-[10px] text-slate-500">
                      De (dia)
                      <select
                        value={filters?.custom_window_start_weekday || ""}
                        onChange={(event) =>
                          onChange(
                            "custom_window_start_weekday",
                            event.target.value,
                          )
                        }
                        className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800"
                      >
                        <option value="">Selecione</option>
                        {WEEKDAY_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="grid gap-1 text-[10px] text-slate-500">
                      De (hora)
                      <Input
                        type="time"
                        value={filters?.custom_window_start_time || ""}
                        onChange={(event) =>
                          onChange(
                            "custom_window_start_time",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                    <label className="grid gap-1 text-[10px] text-slate-500">
                      Até (dia)
                      <select
                        value={filters?.custom_window_end_weekday || ""}
                        onChange={(event) =>
                          onChange(
                            "custom_window_end_weekday",
                            event.target.value,
                          )
                        }
                        className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800"
                      >
                        <option value="">Selecione</option>
                        {WEEKDAY_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="grid gap-1 text-[10px] text-slate-500">
                      Até (hora)
                      <Input
                        type="time"
                        value={filters?.custom_window_end_time || ""}
                        onChange={(event) =>
                          onChange(
                            "custom_window_end_time",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                  </div>
                </div>
              ) : null}
            </fieldset>
          );
        })}
      </div>
    </div>
  );

  return (
    <section className="contents">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 bg-white px-4 pb-3 pt-3 lg:px-7">
        <div>
          <p className="text-sm font-semibold text-slate-950">
            Filtros da operação
          </p>
          <p className="text-xs text-slate-500">
            Aplique o recorte e mantenha os dados operacionais em foco.
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => setMobileFiltersOpen((current) => !current)}
            aria-expanded={mobileFiltersOpen}
            className="mt-2 h-9 w-full justify-center md:hidden"
          >
            <SlidersHorizontal className="h-4 w-4" />
            {mobileFiltersOpen ? "Ocultar filtros" : "Filtros"}
            {filterCount ? (
              <Badge className="border-blue-100 bg-blue-50 px-1.5 text-blue-700">
                {filterCount}
              </Badge>
            ) : null}
            <ChevronDown
              className={`h-4 w-4 transition ${mobileFiltersOpen ? "rotate-180" : ""}`}
            />
          </Button>
        </div>
        <div className="flex flex-col items-end gap-1">
          <>
            {canSyncIxc ? (
              <div className="flex flex-col items-end gap-0.5">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onImport}
                  disabled={importing || !filters}
                  className="h-9 border-blue-200 text-blue-700 hover:bg-blue-50"
                >
                  <RefreshCw
                    className={importing ? "h-4 w-4 animate-spin" : "h-4 w-4"}
                  />
                  {importing
                    ? `Sincronizando ${importProgress || "..."}`
                    : "Sincronizar dados"}
                </Button>
                <span className="max-w-64 text-right text-[10px] text-slate-400">
                  {syncScopeLabel}
                </span>
              </div>
            ) : null}
          </>
          <span className="inline-flex items-center gap-1 text-[10px] text-slate-500">
            <Clock3 className="h-3 w-3 text-slate-400" />
            {lastUpdateLabel(lastUpdatedAt)}
          </span>
        </div>
      </div>
      <div
        className={`${mobileFiltersOpen ? "grid" : "hidden"} max-h-[calc(100vh-65px)] items-end gap-2 overflow-y-auto border-y border-slate-200 bg-white px-4 py-2 shadow-sm md:sticky md:top-[65px] md:z-40 md:grid md:max-h-none md:grid-cols-2 md:overflow-visible lg:px-7 xl:grid-cols-3 2xl:grid-cols-[minmax(15.5rem,1.45fr)_repeat(5,minmax(0,1fr))_auto]`}
      >
        <DateRangePicker
          dateFrom={filters?.date_from || ""}
          dateTo={filters?.date_to || ""}
          min={period?.allowed_from}
          max={period?.allowed_to}
          onChange={onChange}
          presets={[
            {
              label: "Mês atual",
              range: () => {
                const end = parseLocalDateForPreset(period?.allowed_to) || new Date();
                const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 1, 12));
                return { from: toDateValue(start), to: toDateValue(end) };
              },
            },
            {
              label: "Ano até hoje",
              range: () => {
                const end = parseLocalDateForPreset(period?.allowed_to) || new Date();
                const start = parseLocalDateForPreset(period?.allowed_from) || new Date(Date.UTC(end.getUTCFullYear(), 0, 1, 12));
                return { from: toDateValue(start), to: toDateValue(end) };
              },
            },
          ]}
        />
        {mainFilters.map((field) => (
          <FilterField
            key={field.key}
            filterKey={field.key}
            label={field.label}
            values={filters?.[field.key] || []}
            options={options[field.options]}
            onChange={(value) => onChange(field.key, value)}
          />
        ))}
        <div className="flex flex-wrap gap-2 xl:flex-nowrap">
          <Button
            type="button"
            onClick={onApply}
            disabled={loading || !filters}
            className="h-10"
          >
            {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : null}
            Filtrar
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={onClearAll}
            disabled={loading || !filters}
            className="h-10 text-slate-600"
          >
            <RotateCcw className="h-4 w-4" />
            Limpar
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => setAdvancedOpen((current) => !current)}
            aria-expanded={advancedOpen}
            className="h-10 whitespace-nowrap"
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filtros avançados
            {advancedAppliedCount ? (
              <Badge className="border-blue-100 bg-blue-50 px-1.5 text-blue-700">
                {advancedAppliedCount}
              </Badge>
            ) : null}
            <ChevronDown
              className={`h-4 w-4 transition ${advancedOpen ? "rotate-180" : ""}`}
            />
          </Button>
          <SavedViewsPopover
            savedFilters={savedFilters}
            selectedSavedFilterId={selectedSavedFilterId}
            filterName={filterName}
            visibility={savedFilterVisibility}
            canManageViews={canManageViews}
            canCreateGlobalViews={canCreateGlobalViews}
            onSelect={onSelectSavedFilter}
            onNameChange={onFilterNameChange}
            onVisibilityChange={onSavedFilterVisibilityChange}
            onSave={onSave}
            onUpdate={onUpdateSaved}
            onDelete={onDeleteSaved}
          />
        </div>
        {advancedOpen ? advancedPanel : null}
      </div>
      <div className="border-b border-slate-200 bg-white px-4 pb-3 lg:px-7">
      {datesIgnored ? (
        <div className="mt-2 flex items-center gap-2 text-xs text-blue-700">
          <span>As datas não limitam o backlog em andamento.</span>
          <button
            type="button"
            className="font-medium underline"
            onClick={onClearDates}
          >
            Limpar datas
          </button>
        </div>
      ) : null}
      <FilterConceptCard />
      <FilterSummary chips={activeChips} onClearAll={onClearAll} />
      </div>
    </section>
  );
}
