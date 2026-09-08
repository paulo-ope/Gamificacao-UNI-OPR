"use client";

import Link from "next/link";
import { ArrowUpRight, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { AppCheckbox } from "@/components/ui/checkbox";
import { SectionCard } from "@/components/ui/section-card";
import { useBlockQuery } from "@/hooks/use-block-query";
import {
  operationsApi,
  type OperationOverviewFilterKey,
  type OperationOverviewFilterOption,
} from "@/lib/operations-api";

const GROUP_LABEL: Record<OperationOverviewFilterOption["group"], { title: string; hint: string }> = {
  operations: {
    title: "Filtros de O.S.",
    hint: "Recortam os indicadores, o quadro por filial e os gráficos de produção.",
  },
  support: {
    title: "Filtros do SGP Suporte",
    hint: "Recortam SÓ os blocos de atendimento - aceitam vários valores cada.",
  },
};

/**
 * Configuração da Visão Geral executiva, na Administração (decisão do usuário em 2026-09-03).
 *
 * Dois ajustes, ambos válidos para todos os usuários:
 * - quais filtros a tela exibe, escolhidos de um catálogo que vive no backend (a tela só sabe
 *   desenhar o que o catálogo lista, então não há como marcar algo que não funcione);
 * - qual visão global é o filtro pré-setado (definida na própria Visão Geral, mostrada aqui só
 *   para leitura, com o caminho para trocar).
 */
export function OverviewSettingsPanel({
  onError,
  onMessage,
}: {
  onError: (message: string | null) => void;
  onMessage: (message: string | null) => void;
}) {
  const visible = useBlockQuery(() => operationsApi.overviewVisibleFilters(), []);
  const defaultFilter = useBlockQuery(() => operationsApi.overviewDefaultFilter(), []);
  const [selected, setSelected] = useState<Set<OperationOverviewFilterKey> | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible.data && selected === null) setSelected(new Set(visible.data.filters));
  }, [visible.data, selected]);

  const groups = useMemo(() => {
    const byGroup = new Map<OperationOverviewFilterOption["group"], OperationOverviewFilterOption[]>();
    (visible.data?.available ?? []).forEach((option) => {
      byGroup.set(option.group, [...(byGroup.get(option.group) ?? []), option]);
    });
    return byGroup;
  }, [visible.data]);

  const dirty = useMemo(() => {
    if (!visible.data || !selected) return false;
    const current = new Set(visible.data.filters);
    if (current.size !== selected.size) return true;
    return Array.from(current).some((key) => !selected.has(key));
  }, [visible.data, selected]);

  async function save() {
    if (!selected) return;
    setSaving(true);
    onError(null);
    try {
      const updated = await operationsApi.updateOverviewVisibleFilters(Array.from(selected));
      setSelected(new Set(updated.filters));
      onMessage("Filtros da Visão Geral atualizados para todos os usuários.");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Não foi possível salvar os filtros da Visão Geral.");
    } finally {
      setSaving(false);
    }
  }

  const canManage = visible.data?.can_manage ?? false;

  return (
    <SectionCard
      eyebrow="Visão Geral"
      title="Filtros e padrão da tela inicial"
      subtitle="O que aparece na barra de filtros da Visão Geral e qual visão global vem pré-setada. Vale para todos."
      actions={
        <Link href="/visao-geral" className="inline-flex items-center gap-1 text-[11px] font-semibold text-uni-royal hover:underline">
          Abrir Visão Geral
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      }
    >
      {visible.error ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{visible.error}</p>
      ) : visible.loading || !selected ? (
        <p className="flex items-center gap-2 py-4 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando configuração...
        </p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {(["operations", "support"] as const).map((group) => (
            <fieldset key={group} className="min-w-0 rounded-xl border border-slate-200 p-4">
              <legend className="px-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">{GROUP_LABEL[group].title}</legend>
              <p className="mb-3 text-[11px] text-slate-500">{GROUP_LABEL[group].hint}</p>
              <div className="space-y-2">
                {(groups.get(group) ?? []).map((option) => {
                  return (
                    <div
                      key={option.key}
                      className={cn("flex items-center gap-2 text-sm text-slate-700", !canManage && "opacity-70")}
                    >
                      <AppCheckbox
                        checked={selected.has(option.key)}
                        disabled={!canManage}
                        ariaLabel={option.label}
                        onCheckedChange={(checked) => {
                          setSelected((current) => {
                            const next = new Set(current);
                            if (checked) next.add(option.key);
                            else next.delete(option.key);
                            return next;
                          });
                        }}
                      />
                      <span>{option.label}</span>
                    </div>
                  );
                })}
              </div>
            </fieldset>
          ))}
          <div className="lg:col-span-2 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <p className="text-[11px] text-slate-500">
              Visão global pré-setada:{" "}
              {defaultFilter.data?.available ? (
                <span className="font-semibold text-slate-700">{defaultFilter.data.name}</span>
              ) : (
                <span className="text-slate-400">nenhuma - define-se na própria Visão Geral, em &quot;Definir como padrão&quot;</span>
              )}
            </p>
            {canManage ? (
              <Button type="button" size="sm" onClick={() => void save()} disabled={!dirty || saving}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                Salvar filtros
              </Button>
            ) : (
              <span className="text-[11px] text-slate-400">Seu perfil só consulta esta configuração.</span>
            )}
          </div>
        </div>
      )}
    </SectionCard>
  );
}
