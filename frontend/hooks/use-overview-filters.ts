"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type {
  OperationFilterState,
  OperationPeriod,
  OperationSavedFilterValues,
  OverviewSupportFilterValues,
} from "@/lib/operations-api";

/**
 * Filtros de O.S. que a Visão Geral publica na URL e que uma visão global salva pode pré-setar.
 * Só as dimensões de uso executivo - jogar os ~30 filtros do módulo na URL deixaria o link
 * ilegível sem ganho real.
 */
export const OVERVIEW_LIST_KEYS = ["team_models", "regional_groups", "responsibles", "sectors", "os_types"] as const;

/**
 * Filtros do SGP Suporte. São um universo à parte (atendimentos, não O.S.) - por isso ficam de
 * fora de uma visão global salva (que é do domínio de O.S.) e nunca são enviados aos endpoints
 * de operação (ver `operationFiltersOf`). Aceitam VÁRIOS valores cada: o parâmetro da rota
 * `/support/opa/overview` é `str`, mas por baixo (`opa_filters.py::_selected_values`) ele quebra
 * por vírgula antes de montar o `IN (...)` da consulta - a mesma rota já aceita lista, só não
 * tinha sido ligada nenhuma seleção múltipla na tela até um usuário perguntar "consigo selecionar
 * mais de um?" (2026-09-03). Os valores viram string separada por vírgula só na hora da chamada
 * (`overview-screen.tsx`), a URL e o estado continuam em lista, igual aos filtros de O.S.
 */
export const OVERVIEW_SUPPORT_KEYS = ["support_department", "support_channel", "support_reason"] as const;

export type OverviewSupportFilters = {
  support_department?: string[];
  support_channel?: string[];
  support_reason?: string[];
};

/** O recorte completo da tela: filtros de O.S. + filtros do SGP. */
export type OverviewFilters = OperationFilterState & OverviewSupportFilters;

/**
 * Mês atual - mesmo padrão já usado pela Operação Analítica (`GET /operations/period` calcula
 * `date_from`/`date_to` do lado do backend, do dia 1 do mês corrente até hoje, dentro do ano
 * operacional). Pedido do usuário em 2026-09-18: a Visão Geral calculava seu próprio padrão
 * ("últimos 30 dias" a partir de `allowed_to`), ignorando esses dois campos - por isso a tela
 * nunca abria no mês atual, e não havia como fixar isso como padrão (o botão "Definir como
 * padrão" só salva filtros de dimensão, nunca período).
 */
export function defaultOverviewRange(period: OperationPeriod | null) {
  if (!period) return null;
  return { date_from: period.date_from, date_to: period.date_to };
}

function readUrlFilters(params: URLSearchParams) {
  const values: Partial<OverviewFilters> = {};
  const dateFrom = params.get("date_from");
  const dateTo = params.get("date_to");
  if (dateFrom) values.date_from = dateFrom;
  if (dateTo) values.date_to = dateTo;
  [...OVERVIEW_LIST_KEYS, ...OVERVIEW_SUPPORT_KEYS].forEach((key) => {
    const selected = params.getAll(key).filter((item) => item.trim());
    if (selected.length) values[key] = selected;
  });
  return values;
}

/** Só os filtros de O.S. do recorte - o que os endpoints de operação recebem. */
export function operationFiltersOf(filters: OverviewFilters): OperationFilterState {
  const rest: OverviewFilters = { ...filters };
  OVERVIEW_SUPPORT_KEYS.forEach((key) => {
    delete rest[key];
  });
  return rest;
}

export function useOverviewFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Lido uma vez: depois da primeira renderização quem manda é o estado, e a URL só recebe.
  const urlFilters = useRef(readUrlFilters(new URLSearchParams(searchParams.toString()))).current;
  const [filters, setFilters] = useState<OverviewFilters | null>(null);
  const initialized = useRef(false);

  /**
   * Espelha o estado na URL.
   *
   * Precisa ser um efeito, não uma chamada dentro do `setFilters`: o React executa a função de
   * atualização durante a renderização, e um `router.replace` disparado daí é descartado - foi
   * exatamente esse o bug encontrado na validação no navegador (mexer no filtro não mudava a URL
   * e o drill-through da tabela por filial não fazia nada). Como efeito, também garante que o
   * recorte inicial já apareça na URL, e o link fique compartilhável desde a primeira carga.
   */
  useEffect(() => {
    if (!filters) return;
    const params = new URLSearchParams();
    params.set("date_from", filters.date_from);
    params.set("date_to", filters.date_to);
    [...OVERVIEW_LIST_KEYS, ...OVERVIEW_SUPPORT_KEYS].forEach((key) => {
      (filters[key] ?? []).forEach((value) => params.append(key, value));
    });
    // `replace` e não `push`: mexer no filtro não é navegação, e empilhar histórico faria o
    // botão "voltar" desfazer filtro por filtro em vez de sair da tela.
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [filters, pathname, router]);

  const update = useCallback((patch: Partial<OverviewFilters>) => {
    setFilters((current) => (current ? { ...current, ...patch } : current));
  }, []);

  /**
   * Substitui o recorte inteiro, sem mesclar com o atual - diferente de `update` (que é um PATCH:
   * uma chave ausente no argumento simplesmente preserva o valor atual). Existe especificamente
   * pro "Voltar" do drill temporário (`overview-screen.tsx`): a fotografia de "antes do drill" pode
   * legitimamente não ter `regionals`/`team_models` (nenhum filtro selecionado ainda quando a tela
   * carregou é a chave AUSENTE, não uma lista vazia) - `update(fotografia)` nesse caso preservaria
   * o filtro aplicado durante o drill em vez de removê-lo (achado real, 2026-09-05: "Voltar" restaurava
   * o período mas deixava a filial clicada durante o drill presa no filtro).
   */
  const replace = useCallback((next: OverviewFilters) => {
    setFilters(next);
  }, []);

  /**
   * Monta o estado inicial na primeira vez que período e padrão estão disponíveis. Ordem de
   * precedência: o que veio na URL > o filtro padrão da Visão Geral (visão global pré-setada) >
   * vazio. Chamar de novo depois disso não faz nada - o usuário pode ter mexido no filtro.
   */
  const initialize = useCallback(
    (
      period: OperationPeriod,
      defaultValues: OperationSavedFilterValues | null,
      defaultSupportValues?: OverviewSupportFilterValues | null,
    ) => {
      if (initialized.current) return;
      const range = defaultOverviewRange(period);
      if (!range) return;
      initialized.current = true;
      const preset: Partial<OverviewFilters> = {};
      if (defaultValues) {
        OVERVIEW_LIST_KEYS.forEach((key) => {
          const selected = defaultValues[key];
          if (selected?.length) preset[key] = selected;
        });
      }
      if (defaultSupportValues) {
        OVERVIEW_SUPPORT_KEYS.forEach((key) => {
          const selected = defaultSupportValues[key];
          if (selected?.length) preset[key] = selected;
        });
      }
      setFilters({ ...range, ...preset, ...urlFilters });
    },
    [urlFilters],
  );

  return { filters, update, replace, initialize };
}
