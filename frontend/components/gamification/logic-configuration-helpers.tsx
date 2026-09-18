"use client";

// Tipos, constantes e funções puras usados por `logic-configuration-panel.tsx` e pelas seções que
// forem extraídas dele - achado real da auditoria de layout (Fase 5, 2026-09-17): viviam soltos no
// topo daquele arquivo de 3.075 linhas, sem dependência nenhuma do estado do componente principal,
// então podem ser compartilhados sem embaralhar responsabilidade. Nada aqui muda comportamento -
// é código movido, não reescrito.

import { Check, ChevronDown, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type {
  DiagnosisActionType,
  GamificationConfig,
  RecurrenceClassificationRule,
  ScoringGroup,
  ScoringSubjectRule,
  SlaPenaltyType
} from "@/lib/types";

export type Mode = "simple" | "advanced";
export type ConfigSection = "governance" | "categories" | "groups" | "subjects" | "diagnoses" | "recurrence" | "sla" | "integration" | "advanced";
export type SubjectFilter = "all" | "scored" | "not_scored" | "without_group";
export type DiagnosisFilter = "all" | "annuls_points" | "without_rule";
export type RecurrenceClassificationValue = RecurrenceClassificationRule["classification"];

export const SIMPLE_SECTIONS: Array<{ value: ConfigSection; label: string; help: string }> = [
  { value: "governance", label: "Governança geral", help: "Valor do ponto e janela de reincidência." },
  { value: "categories", label: "Tipos gerais", help: "Categorias reais vindas da planilha." },
  { value: "groups", label: "Grupos de pontuação", help: "Pontos e valor por grupo." },
  { value: "subjects", label: "Assuntos", help: "Tipo geral, grupo e status por assunto." },
  { value: "diagnoses", label: "Diagnósticos", help: "Regras principais de diagnóstico." }
];

export const ADVANCED_SECTIONS: Array<{ value: ConfigSection; label: string; help: string }> = [
  ...SIMPLE_SECTIONS,
  { value: "recurrence", label: "Reincidência", help: "Fluxo e regras completas." },
  { value: "sla", label: "SLA/Saúde", help: "Prazo e multiplicadores." },
  { value: "integration", label: "Integração IXC", help: "Sincronização automática e recálculo." },
  { value: "advanced", label: "Avançado", help: "JSON, histórico e restauração." }
];

export const IXC_SYNC_ENABLED_KEY = "ixc_sync_enabled";
export const IXC_SYNC_INTERVAL_MINUTES_KEY = "ixc_sync_interval_minutes";
export const IXC_SYNC_AUTO_RECALCULATE_KEY = "ixc_sync_auto_recalculate";

export const CPK_SYNC_ENABLED_KEY = "cpk_sync_enabled";
export const CPK_BONUS_POINTS_KEY = "cpk_bonus_points";

export const CPK_STATUS_LABEL: Record<string, string> = {
  na_meta: "Na meta",
  fora_meta: "Fora da meta",
  sem_base: "Sem base"
};

export function replaceById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

export const HEALTH_BELOW_MINIMUM_MULTIPLIER_SETTING = "health_below_minimum_multiplier";

export type GroupSnapshot = Pick<ScoringGroup, "name" | "default_points" | "point_value_override" | "active">;

export function groupSnapshot(group: ScoringGroup): GroupSnapshot {
  return {
    name: group.name,
    default_points: group.default_points,
    point_value_override: group.point_value_override ?? null,
    active: group.active,
  };
}

export function sameGroupSnapshot(a: GroupSnapshot | undefined, b: GroupSnapshot) {
  return (
    a?.name === b.name &&
    a?.default_points === b.default_points &&
    (a?.point_value_override ?? null) === (b.point_value_override ?? null) &&
    a?.active === b.active
  );
}

export function actionLabel(action: DiagnosisActionType | null) {
  if (action === "subtract_points") return "Subtrair pontos";
  if (action === "cancel_points") return "Anular pontos";
  if (action === "requires_review") return "Revisão manual";
  if (action === "force_points") return "Forçar pontos";
  if (action === "no_penalty") return "Sem anulação";
  return "Sem regra";
}

// O backend (scoring_detail.py) só lê o valor numérico pra "subtract_points" (desconta o valor
// exato) e "force_points" (usa como pontuação fixa). Pra "cancel_points" ele sempre zera 100% dos
// pontos da ocorrência, ignorando qualquer número digitado aqui; pra "requires_review" e
// "no_penalty" o valor nunca é lido. Sem isso, o campo parecia funcionar pra todo mundo e um admin
// podia achar que "Anular pontos" com valor "50" descontava 50 pontos, quando na verdade zera tudo.
export function diagnosisPointsFieldState(action: DiagnosisActionType): { editable: boolean; helper: string } {
  if (action === "subtract_points") return { editable: true, helper: "Pontos descontados desta ocorrência." };
  if (action === "force_points") return { editable: true, helper: "Pontuação fixa aplicada, substitui a regra do assunto." };
  if (action === "cancel_points") return { editable: false, helper: "Anula 100% da pontuação - este valor não é usado." };
  return { editable: false, helper: "Esta ação não usa valor numérico." };
}

// Mesma lógica do diagnóstico, mas pra regra de SLA: "cancel_points" sempre zera 100% dos pontos da
// O.S fora do prazo (ignora o valor); "none" e "requires_review" nunca leem o valor.
export function slaValueFieldState(penaltyType: SlaPenaltyType): { editable: boolean; helper: string } {
  if (penaltyType === "subtract_points") return { editable: true, helper: "Pontos descontados da O.S fora do prazo." };
  if (penaltyType === "percentage_reduction") return { editable: true, helper: "Percentual (0-100) reduzido da pontuação." };
  if (penaltyType === "cancel_points") return { editable: false, helper: "Anula 100% da pontuação - este valor não é usado." };
  return { editable: false, helper: "Este tipo não usa valor numérico." };
}

export function recurrenceClassificationLabel(value: string) {
  if (value === "recorrencia_operacional") return "Reincidência operacional";
  if (value === "reincidencia_tecnica") return "Reincidência de manutenção";
  if (value === "garantia") return "Reincidência após ativação";
  if (value === "os_nao_reincidente") return "O.S. não reincidente";
  if (value === "demandas_diferentes") return "Demandas diferentes";
  return "Não identificado";
}

// O backend (scoring_detail.py, RECURRENCE_DISCOUNT_CLASSIFICATIONS) só aplica o desconto na O.S
// original pra esses dois subtipos - marcar "Anula pontuação" em qualquer outro subtipo não tem
// efeito nenhum no cálculo, então o checkbox fica desabilitado pra evitar essa falsa impressão.
export function classificationSupportsDiscount(classification: string) {
  return classification === "reincidencia_tecnica" || classification === "garantia";
}

export function recurrenceActionLabel(value: string) {
  if (value === "annul_original") return "Anular pontuação da O.S original";
  if (value === "subtract_original") return "Anular pontos fixos da O.S original";
  if (value === "requires_review") return "Enviar para revisão manual";
  if (value === "no_penalty") return "Apenas sinalizar";
  return "Usar configuração do backend";
}

export function subjectStatus(rule: ScoringSubjectRule, group: ScoringGroup | null | undefined) {
  if (!group) return "sem_regra";
  if (!rule.active) return "nao_pontua";
  return "pontua";
}

export function subjectRuleKey(osType: string, osSubject: string) {
  return `${osType.trim().toLowerCase()}::${osSubject.trim().toLowerCase()}`;
}

export function subjectStatusLabel(status: string) {
  if (status === "pontua") return "Pontua";
  if (status === "nao_pontua") return "Não pontua";
  return "Sem regra";
}

export function subjectStatusClass(status: string) {
  if (status === "pontua") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "nao_pontua") return "border-slate-200 bg-slate-50 text-slate-700";
  return "border-amber-200 bg-amber-50 text-amber-800";
}

export function recurrenceIdentityFields(settings: Record<string, string>) {
  const value = settings.recurrence_identity_fields || "login,contract";
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function toggleIdentityField(settings: Record<string, string>, field: string, checked: boolean) {
  const current = new Set(recurrenceIdentityFields(settings));
  if (checked) {
    current.add(field);
  } else {
    current.delete(field);
  }
  return Array.from(current).join(",");
}

export function splitRuleValues(value: string | null | undefined) {
  return (value ?? "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function joinRuleValues(values: string[]) {
  return values.filter(Boolean).join(" | ") || null;
}

export function uniqueSorted(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((value) => value?.trim()).filter(Boolean) as string[])).sort((a, b) =>
    a.localeCompare(b, "pt-BR")
  );
}

export type SearchOption = {
  value: string;
  label: string;
  meta?: string;
};

export function normalizeSearchOptions(options: Array<string | SearchOption>) {
  return options.map((option) => (typeof option === "string" ? { value: option, label: option } : option));
}

export function SearchableMultiSelect({
  label,
  placeholder,
  options,
  value,
  onChange
}: {
  label: string;
  placeholder: string;
  options: Array<string | SearchOption>;
  value: string | null | undefined;
  onChange: (value: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = splitRuleValues(value);
  const normalizedSearch = search.trim().toLowerCase();
  const normalizedOptions = normalizeSearchOptions(options);
  const filteredOptions = normalizedOptions
    .filter((option) => {
      const haystack = [option.label, option.value, option.meta ?? ""].join(" ").toLowerCase();
      return !normalizedSearch || haystack.includes(normalizedSearch);
    })
    .slice(0, 80);

  function toggleOption(option: string) {
    const next = selected.includes(option) ? selected.filter((item) => item !== option) : [...selected, option];
    onChange(joinRuleValues(next));
  }

  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
        onClick={() => setOpen((value) => !value)}
      >
        <div className="min-w-0">
          <div className={selected.length ? "line-clamp-1 font-medium text-slate-950" : "text-sm text-slate-500"}>
            {selected.length ? `${selected.length} selecionado(s)` : placeholder}
          </div>
          <div className="truncate text-xs text-slate-500">
            {selected.length ? selected.slice(0, 3).join(", ") : "Busque e selecione os valores aplicáveis."}
          </div>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
      </button>
      {selected.length ? (
        <div className="flex flex-wrap gap-2">
          {selected.slice(0, 4).map((item) => (
            <button
              key={item}
              type="button"
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-[11px] font-medium text-sky-700"
              onClick={() => toggleOption(item)}
              title={item}
            >
              <span className="max-w-40 truncate">{item}</span>
              <X className="h-3 w-3" />
            </button>
          ))}
          {selected.length > 4 ? <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] text-slate-500">+{selected.length - 4}</span> : null}
        </div>
      ) : null}
      {open ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_18px_48px_rgba(15,23,42,0.12)]">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Pesquisar..." className="mb-3 h-10 text-sm" />
          <div className="max-h-56 space-y-1 overflow-auto">
            {filteredOptions.map((option) => {
              const checked = selected.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  className="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 text-left text-sm hover:border-slate-200 hover:bg-slate-50"
                  onClick={() => toggleOption(option.value)}
                  title={option.meta ? `${option.label} - ${option.meta}` : option.label}
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 items-center justify-center rounded border",
                      checked ? "border-uni-royal bg-uni-royal text-white" : "border-slate-300 bg-white text-transparent"
                    )}
                  >
                    {checked ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 font-medium text-slate-800">{option.label}</span>
                    {option.meta ? <span className="line-clamp-1 text-[11px] text-slate-500">{option.meta}</span> : null}
                  </span>
                </button>
              );
            })}
            {filteredOptions.length === 0 ? <div className="px-3 py-6 text-center text-sm text-slate-500">Nenhuma opção encontrada.</div> : null}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
            <Button type="button" variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => onChange(null)}>
              Limpar
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-8 px-3 text-xs" onClick={() => setOpen(false)}>
              Fechar
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function downloadJson(config: GamificationConfig) {
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "gamification_rules_config.json";
  link.click();
  URL.revokeObjectURL(url);
}
