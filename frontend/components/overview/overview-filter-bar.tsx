"use client";

import { BookmarkCheck, ChevronDown, ListFilter, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { MultiSelect } from "@/components/ui/multi-select";
import {
  OVERVIEW_LIST_KEYS,
  OVERVIEW_SUPPORT_KEYS,
  type OverviewFilters,
} from "@/hooks/use-overview-filters";
import { formatIsoDate } from "@/lib/format";
import type {
  OperationFilters,
  OperationOverviewDefaultFilter,
  OperationOverviewFilterKey,
  OperationPeriod,
} from "@/lib/operations-api";
import type { SupportOpaFilterOption, SupportOpaFilters } from "@/lib/types";
import { cn } from "@/lib/utils";

type ListKey = (typeof OVERVIEW_LIST_KEYS)[number];
type SupportKey = (typeof OVERVIEW_SUPPORT_KEYS)[number];

/** Rótulo e placeholder de cada filtro de O.S.; a ORDEM de exibição vem do catálogo do backend. */
const LIST_FIELDS: Record<ListKey, { label: string; placeholder: string }> = {
  team_models: { label: "Modelo de equipe", placeholder: "Todos os modelos" },
  regionals: { label: "Filial", placeholder: "Todas as filiais" },
  sectors: { label: "Setor", placeholder: "Setores padrão" },
  os_types: { label: "Tipo de O.S.", placeholder: "Todos os tipos" },
  responsibles: { label: "Colaborador", placeholder: "Todos os colaboradores" },
};

/**
 * Filtros do SGP: aceitam vários valores cada (o backend já faz `IN (...)`, ver
 * `hooks/use-overview-filters.ts`). Opções vêm como `{value,label}` de `/support/opa/filters`,
 * por isso usam o mesmo `MultiSelect` genérico dos filtros de O.S., só com `getValue`/
 * `formatOption` pra extrair a chave e o texto do objeto.
 */
const SUPPORT_FIELDS: Record<SupportKey, { label: string; placeholder: string; options: keyof SupportOpaFilters }> = {
  support_department: { label: "Departamento (SGP)", placeholder: "Todos os departamentos", options: "departments" },
  support_channel: { label: "Canal (SGP)", placeholder: "Todos os canais", options: "channels" },
  support_reason: { label: "Motivo (SGP)", placeholder: "Todos os motivos", options: "reasons" },
};

function isListKey(key: OperationOverviewFilterKey): key is ListKey {
  return (OVERVIEW_LIST_KEYS as readonly string[]).includes(key);
}

function isSupportKey(key: OperationOverviewFilterKey): key is SupportKey {
  return (OVERVIEW_SUPPORT_KEYS as readonly string[]).includes(key);
}

const EXPANDED_STORAGE_KEY = "uni_overview_filters_expanded";

type Chip = { key: OperationOverviewFilterKey; label: string; onRemove: () => void };

/** Rótulo do chip a partir dos valores selecionados: até 2 por extenso, mais que isso vira contagem. */
function summarize(fieldLabel: string, displayValues: string[]) {
  const text = displayValues.length <= 2 ? displayValues.join(", ") : `${displayValues.length} selecionados`;
  return `${fieldLabel}: ${text}`;
}

/**
 * Barra de filtros da Visão Geral: recolhível, no padrão de ferramentas como Linear/Notion -
 * fechada mostra só o período e um resumo em chips do que está filtrado; aberta mostra o
 * formulário completo. O período fica sempre visível mesmo fechada, porque é o dado essencial
 * pra interpretar a tela - só os campos de recorte (filial, modelo de equipe...) se escondem.
 *
 * Quais campos aparecem vem de `visible` (configurado na Administração). Os filtros de O.S. e os
 * do SGP ficam em grupos visualmente separados e rotulados, porque são universos diferentes:
 * "filial" recorta O.S., "departamento" recorta atendimentos, e nada aqui finge que um vale pro
 * outro - misturar produziria números de recortes distintos lado a lado, sem erro nenhum.
 */
export function OverviewFilterBar({
  filters,
  visible,
  options,
  supportOptions,
  period,
  defaultFilter,
  onChange,
  onResetToDefault,
  onSaveAsDefault,
}: {
  filters: OverviewFilters;
  visible: OperationOverviewFilterKey[];
  options: OperationFilters | null;
  supportOptions: SupportOpaFilters | null;
  period: OperationPeriod | null;
  defaultFilter: OperationOverviewDefaultFilter | null;
  onChange: (patch: Partial<OverviewFilters>) => void;
  onResetToDefault: () => void;
  onSaveAsDefault?: () => void;
}) {
  const hasPreset = defaultFilter?.available ?? false;
  const listKeys = visible.filter(isListKey);
  const supportKeys = visible.filter(isSupportKey);

  // Nasce aberta (mesmo padrão da barra lateral): filtro é interação primária, não um detalhe
  // escondido no primeiro uso. Recolher fica guardado por navegador, não pelo padrão global.
  const [expanded, setExpanded] = useState(true);
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(EXPANDED_STORAGE_KEY);
      if (stored !== null) setExpanded(stored === "true");
    } catch {
      // Sem preferência acessível: segue aberta.
    }
  }, []);
  function toggleExpanded() {
    setExpanded((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(EXPANDED_STORAGE_KEY, String(next));
      } catch {
        // Preferência é conveniência: não impedir a interação se o armazenamento falhar.
      }
      return next;
    });
  }

  const chips = useMemo<Chip[]>(() => {
    const items: Chip[] = [];
    listKeys.forEach((key) => {
      const values = filters[key] ?? [];
      if (!values.length) return;
      items.push({
        key,
        label: summarize(LIST_FIELDS[key].label, values),
        onRemove: () => {
          const patch: Partial<OverviewFilters> = {};
          patch[key] = [];
          onChange(patch);
        },
      });
    });
    supportKeys.forEach((key) => {
      const values = filters[key] ?? [];
      if (!values.length) return;
      const field = SUPPORT_FIELDS[key];
      const catalog = supportOptions?.[field.options] ?? [];
      const displayValues = values.map((value) => catalog.find((option) => option.value === value)?.label ?? value);
      items.push({
        key,
        label: summarize(field.label, displayValues),
        onRemove: () => {
          const patch: Partial<OverviewFilters> = {};
          patch[key] = [];
          onChange(patch);
        },
      });
    });
    return items;
  }, [filters, listKeys, supportKeys, supportOptions, onChange]);

  const periodLabel = `${formatIsoDate(filters.date_from)} – ${formatIsoDate(filters.date_to)}`;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-2 p-3">
        <button
          type="button"
          onClick={toggleExpanded}
          aria-expanded={expanded}
          className="flex shrink-0 items-center gap-2 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-slate-50"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-uni-royal/10 text-uni-royal">
            <ListFilter className="h-3.5 w-3.5" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-slate-900">Filtros</span>
            <span className="block truncate text-[11px] text-slate-500">{periodLabel}</span>
          </span>
          <ChevronDown className={cn("h-4 w-4 shrink-0 text-slate-400 transition-transform", expanded && "rotate-180")} />
        </button>

        {/* Resumo em chips: só quando fechada - aberta, os próprios campos já mostram a seleção. */}
        {!expanded && chips.length ? (
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            {chips.map((chip) => (
              <span
                key={chip.key}
                className="inline-flex max-w-full items-center gap-1 rounded-full border border-slate-200 bg-slate-50 py-1 pl-2.5 pr-1 text-[11px] font-medium text-slate-700"
              >
                <span className="truncate">{chip.label}</span>
                <button
                  type="button"
                  onClick={chip.onRemove}
                  aria-label={`Remover filtro ${chip.label}`}
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
          </div>
        ) : (
          <div className="min-w-0 flex-1" />
        )}

        {!expanded ? (
          <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={toggleExpanded}>
            Editar filtros
          </Button>
        ) : null}
      </div>

      {/* Truque do CSS Grid (0fr/1fr) pra recolher com transição suave sem medir altura em JS -
          o filho com `overflow-hidden` é quem faz o conteúdo sumir de verdade quando a linha do
          grid vai a 0fr. */}
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <div className="border-t border-slate-100 p-4 pt-3">
            {/* Grid em vez de `flex-wrap`: com controles de larguras diferentes, o wrap deixava a
                última linha com um campo esticado e sem alinhamento com a linha de cima. */}
            <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
              <div className="min-w-0">
                <DateRangePicker
                  label="Período"
                  dateFrom={filters.date_from}
                  dateTo={filters.date_to}
                  min={period?.allowed_from}
                  max={period?.allowed_to}
                  onChange={(key, value) => onChange(key === "date_from" ? { date_from: value } : { date_to: value })}
                />
              </div>
              {listKeys.map((key) => (
                <div key={key} className="min-w-0">
                  <p className="pb-1 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400">{LIST_FIELDS[key].label}</p>
                  <MultiSelect
                    values={filters[key] ?? []}
                    options={options?.[key] ?? []}
                    placeholder={LIST_FIELDS[key].placeholder}
                    ariaLabel={LIST_FIELDS[key].label}
                    onChange={(values) => {
                      const patch: Partial<OverviewFilters> = {};
                      patch[key] = values;
                      onChange(patch);
                    }}
                  />
                </div>
              ))}
            </div>

            {supportKeys.length ? (
              <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-3">
                <p className="mb-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
                  Filtros do SGP Suporte{" "}
                  <span className="font-normal normal-case tracking-normal text-slate-400">
                    · recortam só os blocos de atendimento
                  </span>
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {supportKeys.map((key) => (
                    <div key={key} className="min-w-0">
                      <p className="pb-1 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400">{SUPPORT_FIELDS[key].label}</p>
                      <MultiSelect<SupportOpaFilterOption>
                        values={filters[key] ?? []}
                        options={supportOptions?.[SUPPORT_FIELDS[key].options] ?? []}
                        getValue={(option) => option.value}
                        formatOption={(option) => option.label}
                        placeholder={SUPPORT_FIELDS[key].placeholder}
                        ariaLabel={SUPPORT_FIELDS[key].label}
                        onChange={(values) => {
                          const patch: Partial<OverviewFilters> = {};
                          patch[key] = values;
                          onChange(patch);
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
              {hasPreset ? (
                <p className="min-w-0 flex-1 text-[11px] text-slate-500">
                  Este recorte é o filtro pré-setado desta tela, salvo só para a Visão Geral - não aparece nas visões da
                  Operação Analítica.
                </p>
              ) : (
                <p className="min-w-0 flex-1 text-[11px] text-slate-500">
                  Nenhum filtro padrão definido para esta tela. Quem administra visões globais pode definir o recorte
                  atual em &quot;Definir como padrão&quot;.
                </p>
              )}
              <div className="flex shrink-0 items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={onResetToDefault}>
                  <RotateCcw className="h-3.5 w-3.5" />
                  Restaurar padrão
                </Button>
                {onSaveAsDefault ? (
                  <Button type="button" variant="ghost" size="sm" onClick={onSaveAsDefault}>
                    <BookmarkCheck className="h-3.5 w-3.5" />
                    Definir como padrão
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
