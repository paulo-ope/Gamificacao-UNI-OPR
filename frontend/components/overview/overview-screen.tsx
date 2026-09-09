"use client";

import { Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppSwitch } from "@/components/gamification/config-ui";
import { OverviewFilterBar } from "@/components/overview/overview-filter-bar";
import { Button } from "@/components/ui/button";
import { OverviewGamificationCard } from "@/components/overview/overview-gamification-card";
import { OverviewKpiStrip } from "@/components/overview/overview-kpi-strip";
import { OverviewRegionalTable } from "@/components/overview/overview-regional-table";
import { OverviewShareDonut } from "@/components/overview/overview-share-donut";
import { OverviewSupportCard } from "@/components/overview/overview-support-card";
import { OperationsTrendChart } from "@/components/operations/operations-trend-chart";
import { StatusToast } from "@/components/ui/status-toast";
import { useBlockQuery } from "@/hooks/use-block-query";
import {
  OVERVIEW_LIST_KEYS,
  OVERVIEW_SUPPORT_KEYS,
  defaultOverviewRange,
  operationFiltersOf,
  useOverviewFilters,
  type OverviewFilters,
} from "@/hooks/use-overview-filters";
import { usePrompt } from "@/hooks/use-prompt";
import { api } from "@/lib/api";
import { formatDateTime, formatIsoDate } from "@/lib/format";
import {
  buildBacklogTrendOption,
  buildOverviewOpeningsTrendOption,
  buildOverviewSlaTrendOption,
} from "@/lib/overview-chart-options";
import {
  operationsApi,
  type OperationFilterState,
  type OperationOverviewDefaultFilter,
  type OperationOverviewFilterKey,
  type OperationPeriod,
} from "@/lib/operations-api";
import { previousWindow, windowLengthDays } from "@/lib/period";
import type { AuthUser } from "@/lib/types";

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

// Enquanto a configuração de filtros visíveis não chega, a barra mostra o que sempre mostrou.
const FALLBACK_VISIBLE: OperationOverviewFilterKey[] = [...OVERVIEW_LIST_KEYS];

const SHOW_PREVIOUS_PERIOD_STORAGE_KEY = "uni_overview_show_previous_period";

/**
 * Visão Geral executiva: macrovisão da operação em uma tela, sem entrar em módulo.
 *
 * Nenhuma métrica é calculada aqui. Cada bloco chama o endpoint do módulo dono do dado (Operação,
 * SGP, Gamificação) por um `useBlockQuery` próprio - carrega, falha e recarrega de forma
 * independente - e some quando o perfil não tem a permissão daquele dado: a mesma tela serve
 * diretoria, coordenação regional e supervisão.
 *
 * Fontes por bloco (todas já existiam; o único endpoint criado para esta tela é o quadro por
 * filial):
 * - KPIs e comparação: `/operations/overview` no período e na janela imediatamente anterior;
 * - fluxo diário: `/operations/overview/trends`;
 * - donut por filial e quadro: `/operations/overview/regional-matrix`;
 * - donut por modelo de equipe: `/operations/overview/work-schedule` (`by_model`);
 * - meta da filial: `/operations/capacity-summary`;
 * - SGP (card + donut por canal): `/support/opa/overview`;
 * - gamificação: `/dashboard/gamification-preview`.
 */
export function OverviewScreen({ user }: { user: AuthUser }) {
  const { filters, update, replace, initialize } = useOverviewFilters();
  const [period, setPeriod] = useState<OperationPeriod | null>(null);
  const [defaultFilter, setDefaultFilter] = useState<OperationOverviewDefaultFilter | null>(null);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ error: string | null; message: string | null }>({ error: null, message: null });
  const { promptText, PromptDialog } = usePrompt();

  /**
   * Liga/desliga a linha de período anterior nos 3 gráficos de tendência de uma vez só - pedido
   * explícito do usuário (2026-09-08: "quero em todos os gráficos e eu possa selecionar se quero
   * essa linha de comparação ou não"). Um switch só, não um por gráfico: é a mesma pergunta
   * ("quero comparar com o período anterior agora?") em todos eles. Nasce ligado (era o padrão
   * antes de virar opcional) e lembra a escolha por navegador, mesmo padrão de
   * `EXPANDED_STORAGE_KEY` em `overview-filter-bar.tsx`.
   */
  const [showPreviousPeriod, setShowPreviousPeriod] = useState(true);
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SHOW_PREVIOUS_PERIOD_STORAGE_KEY);
      if (stored !== null) setShowPreviousPeriod(stored === "true");
    } catch {
      // Sem preferência acessível: segue ligado.
    }
  }, []);
  function toggleShowPreviousPeriod(next: boolean) {
    setShowPreviousPeriod(next);
    try {
      window.localStorage.setItem(SHOW_PREVIOUS_PERIOD_STORAGE_KEY, String(next));
    } catch {
      // Preferência é conveniência: não impedir a interação se o armazenamento falhar.
    }
  }

  const canSeeSla = user.permissions.includes("operations:view_sla");
  const canSeeSupport = user.permissions.includes("support:read");
  const canSeeGamification = user.permissions.includes("dashboard:read");

  // Bootstrap: período disponível + filtro padrão da tela. Os dois juntos definem o estado
  // inicial do filtro, então nada mais é buscado antes deles.
  useEffect(() => {
    let active = true;
    Promise.all([operationsApi.period(), operationsApi.overviewDefaultFilter().catch(() => null)])
      .then(([availablePeriod, savedDefault]) => {
        if (!active) return;
        setPeriod(availablePeriod);
        setDefaultFilter(savedDefault);
        initialize(availablePeriod, savedDefault?.filters ?? null);
      })
      .catch((reason) => {
        if (active) setBootstrapError(errorMessage(reason, "Não foi possível carregar o período disponível."));
      });
    return () => {
      active = false;
    };
  }, [initialize]);

  const ready = Boolean(filters);
  // Só os filtros de O.S. vão para os endpoints de operação; os do SGP só para o SGP.
  const opFilters: OperationFilterState | null = filters ? operationFiltersOf(filters) : null;
  // Uma chave estável do recorte de O.S.: os `useBlockQuery` de operação recarregam quando ela
  // muda, e só então - mexer num filtro do SGP não refaz os indicadores de O.S.
  const filterKey = opFilters ? JSON.stringify(opFilters) : "";
  const previous = useMemo(
    () => (filters ? previousWindow(filters.date_from, filters.date_to, period?.allowed_from) : null),
    [filters, period?.allowed_from],
  );
  const previousFilters: OperationFilterState | null = opFilters && previous ? { ...opFilters, ...previous } : null;
  const supportKey = filters
    ? [
        filters.date_from,
        filters.date_to,
        ...(filters.support_department ?? []),
        "|",
        ...(filters.support_channel ?? []),
        "|",
        ...(filters.support_reason ?? []),
      ].join(",")
    : "";

  const options = useBlockQuery(() => operationsApi.filters(opFilters!), [filterKey], { enabled: ready });
  const overview = useBlockQuery(() => operationsApi.overview(opFilters!), [filterKey], {
    enabled: ready,
    fallbackError: "Não foi possível carregar os indicadores.",
  });
  const previousOverview = useBlockQuery(() => operationsApi.overview(previousFilters!), [filterKey], {
    enabled: ready && previousFilters !== null,
  });
  const trends = useBlockQuery(() => operationsApi.overviewTrends(opFilters!, "day"), [filterKey], {
    enabled: ready,
    fallbackError: "Não foi possível carregar a série diária.",
  });
  // Mesma janela que já alimenta o card de comparação do topo (`previousOverview`) - aqui vira
  // uma linha no gráfico, não só um número agregado.
  const previousTrends = useBlockQuery(() => operationsApi.overviewTrends(previousFilters!, "day"), [filterKey], {
    enabled: ready && previousFilters !== null,
  });
  const matrix = useBlockQuery(() => operationsApi.overviewRegionalMatrix(opFilters!), [filterKey], {
    enabled: ready,
    fallbackError: "Não foi possível carregar o quadro por filial.",
  });
  const backlogTrend = useBlockQuery(() => operationsApi.overviewBacklogTrend(opFilters!), [filterKey], {
    enabled: ready,
    fallbackError: "Não foi possível carregar o histórico de backlog.",
  });
  const previousBacklogTrend = useBlockQuery(() => operationsApi.overviewBacklogTrend(previousFilters!), [filterKey], {
    enabled: ready && previousFilters !== null,
  });
  const capacity = useBlockQuery(() => operationsApi.capacitySummary(opFilters!), [filterKey], { enabled: ready });
  const workSchedule = useBlockQuery(() => operationsApi.overviewWorkSchedule(opFilters!), [filterKey], {
    enabled: ready,
    fallbackError: "Não foi possível carregar a produção por modelo de equipe.",
  });
  const support = useBlockQuery(
    () =>
      api.supportOpaOverview({
        date_from: filters!.date_from,
        date_to: filters!.date_to,
        // A rota aceita lista via string separada por vírgula (`opa_filters.py::_selected_values`
        // faz o `.split(",")` do lado do backend) - é o mesmo mecanismo, só nunca tinha sido
        // ligado a uma seleção múltipla na tela.
        department_id: filters!.support_department?.join(",") || undefined,
        channel: filters!.support_channel?.join(",") || undefined,
        reason_id: filters!.support_reason?.join(",") || undefined,
      }),
    [supportKey],
    { enabled: ready && canSeeSupport, fallbackError: "Não foi possível carregar os atendimentos do SGP." },
  );
  // Quais filtros a barra exibe (Administração) e as opções dos filtros do SGP, se algum estiver visível.
  const visibleFilters = useBlockQuery(() => operationsApi.overviewVisibleFilters(), []);
  const visible = visibleFilters.data?.filters ?? FALLBACK_VISIBLE;
  const showsSupportFilters = canSeeSupport && visible.some((key) => (OVERVIEW_SUPPORT_KEYS as readonly string[]).includes(key));
  const supportOptions = useBlockQuery(
    () => api.supportOpaFilters({ date_from: filters!.date_from, date_to: filters!.date_to }),
    [filters?.date_from, filters?.date_to],
    { enabled: ready && showsSupportFilters },
  );
  // A prévia da gamificação e o frescor do dado não dependem do filtro: um pedido por abertura.
  const gamification = useBlockQuery(() => api.gamificationPreview(), [], {
    enabled: canSeeGamification,
    fallbackError: "Não foi possível carregar a prévia da gamificação.",
  });
  const freshness = useBlockQuery(() => operationsApi.dataFreshness(), []);

  const resetToDefault = useCallback(() => {
    if (!period) return;
    const range = defaultOverviewRange(period);
    if (!range) return;
    const preset: Partial<OverviewFilters> = {};
    OVERVIEW_LIST_KEYS.forEach((key) => {
      preset[key] = defaultFilter?.filters?.[key] ?? [];
    });
    // Os filtros do SGP não fazem parte da visão global: restaurar o padrão os limpa.
    OVERVIEW_SUPPORT_KEYS.forEach((key) => {
      preset[key] = [];
    });
    update({ ...range, ...preset });
  }, [defaultFilter, period, update]);

  /**
   * Torna o recorte atual o padrão da tela para todo mundo.
   *
   * O backend só aceita uma VISÃO GLOBAL como padrão (nunca um filtro pessoal, que os outros não
   * veriam nem poderiam editar), então o fluxo é: salvar o recorte atual como visão global e
   * apontar o padrão para ela. Assim o padrão continua editável pela tela de visões da Operação
   * Analítica, sem um cadastro paralelo só para esta tela.
   */
  const saveAsDefault = useCallback(async () => {
    if (!filters) return;
    const name = await promptText({
      title: "Definir o filtro padrão da Visão Geral",
      description:
        "O recorte atual é salvo como uma visão global da Operação Analítica e passa a ser o padrão desta tela para todos os usuários.",
      label: "Nome da visão global",
      placeholder: "Ex.: Visão da diretoria",
      confirmLabel: "Definir como padrão",
    });
    const trimmed = name?.trim();
    if (!trimmed) return;
    try {
      const values: Partial<OperationFilterState> = {};
      OVERVIEW_LIST_KEYS.forEach((key) => {
        values[key] = filters[key] ?? [];
      });
      const saved = await operationsApi.createSavedFilter(trimmed, values, "global");
      setDefaultFilter(await operationsApi.updateOverviewDefaultFilter(saved.id));
      setFeedback({ error: null, message: `"${trimmed}" agora é o filtro padrão da Visão Geral.` });
    } catch (reason) {
      setFeedback({ error: errorMessage(reason, "Não foi possível definir o filtro padrão."), message: null });
    }
  }, [filters, promptText]);

  const previousTrendForCharts = showPreviousPeriod ? previousTrends.data : null;
  const previousBacklogForChart = showPreviousPeriod ? previousBacklogTrend.data : null;
  const openingsOption = useMemo(
    () => (trends.data ? buildOverviewOpeningsTrendOption(trends.data, previousTrendForCharts) : null),
    [trends.data, previousTrendForCharts],
  );
  const slaOption = useMemo(
    () => (canSeeSla && trends.data ? buildOverviewSlaTrendOption(trends.data, previousTrendForCharts) : null),
    [canSeeSla, trends.data, previousTrendForCharts],
  );
  const backlogOption = useMemo(
    () => (backlogTrend.data?.points.length ? buildBacklogTrendOption(backlogTrend.data, previousBacklogForChart) : null),
    [backlogTrend.data, previousBacklogForChart],
  );
  // Aviso só quando o recorte pedido começa antes da coleta existir - não é erro, é a fotografia
  // diária não tendo retroatividade (ver `backlog_daily_trend`).
  const backlogCoverageNote =
    backlogTrend.data?.coverage_from && filters && filters.date_from < backlogTrend.data.coverage_from
      ? `Histórico de backlog disponível a partir de ${formatIsoDate(backlogTrend.data.coverage_from)}.`
      : null;

  /**
   * Drill TEMPORÁRIO: qualquer clique que recorta a Visão Geral (dia num gráfico de tendência,
   * filial/modelo num donut, filial na tabela) passa por aqui, não direto por `update`. É o mesmo
   * risco em todo drill da tela, não só o de dia - "ficar preso no filtro" foi pedido explicitamente
   * pelo usuário pra evitar (2026-09-04/05: primeiro só no drill por dia, depois generalizado pra
   * "todos os drill da visão macro").
   *
   * `preDrillFilters` guarda o recorte de ANTES do primeiro clique de uma sequência de drills -
   * clicar de novo (outro dia, outra filial, um modelo em cima disso) não pisa nessa memória, então
   * "Voltar" sempre desfaz a sequência inteira de uma vez, não passo a passo. Isso é deliberadamente
   * diferente de "Restaurar padrão" (que voltaria pro filtro padrão da tela, apagando qualquer coisa
   * que o usuário já tivesse escolhido antes de começar a explorar).
   */
  const [preDrillFilters, setPreDrillFilters] = useState<OverviewFilters | null>(null);
  const drillFilters = (patch: Partial<OverviewFilters>) => {
    setPreDrillFilters((current) => current ?? filters);
    update(patch);
  };
  const isDrilled = Boolean(preDrillFilters && filters && JSON.stringify(filters) !== JSON.stringify(preDrillFilters));
  const returnFromDrill = () => {
    if (!preDrillFilters) return;
    // `replace`, não `update`: a fotografia de antes do drill pode legitimamente não ter
    // `regionals`/`team_models` (chave ausente, não lista vazia) - um PATCH deixaria o filtro
    // aplicado durante o drill preso, em vez de removê-lo (ver `use-overview-filters.ts`).
    replace(preDrillFilters);
    setPreDrillFilters(null);
  };
  const drillIntoDay = (day: string) => drillFilters({ date_from: day, date_to: day });
  // Cada gráfico mapeia o índice clicado pro dia usando o PRÓPRIO array de pontos - o de backlog
  // pode ter menos pontos que o de fluxo/SLA (fotografia sem retroatividade, ver
  // `backlog_daily_trend`), então os índices não são intercambiáveis entre gráficos.
  const trendDrillEvents = trends.data
    ? {
        click: (params: unknown) => {
          const index = (params as { dataIndex?: number }).dataIndex;
          const day = index !== undefined ? trends.data!.points[index]?.period_start : undefined;
          if (day) drillIntoDay(day);
        },
      }
    : undefined;
  const backlogDrillEvents = backlogTrend.data
    ? {
        click: (params: unknown) => {
          const index = (params as { dataIndex?: number }).dataIndex;
          const day = index !== undefined ? backlogTrend.data!.points[index]?.snapshot_date : undefined;
          if (day) drillIntoDay(day);
        },
      }
    : undefined;
  const completedByRegional = useMemo(
    () => (matrix.data?.items ?? []).map((item) => ({ label: item.regional, value: item.completed })),
    [matrix.data],
  );
  const completedByTeamModel = useMemo(
    () => (workSchedule.data?.by_model ?? []).map((item) => ({ label: item.model_name, value: item.completed })),
    [workSchedule.data],
  );
  const attendancesByChannel = useMemo(
    () => (support.data?.by_channel ?? []).map((item) => ({ label: item.channel, value: item.total })),
    [support.data],
  );

  if (bootstrapError) {
    return (
      <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{bootstrapError}</p>
    );
  }
  if (!filters) {
    return (
      <p className="py-16 text-center text-sm text-slate-500" aria-busy="true">
        Carregando a Visão Geral...
      </p>
    );
  }

  const periodLabel = `${formatIsoDate(filters.date_from)} a ${formatIsoDate(filters.date_to)}`;
  const windowDays = windowLengthDays(filters.date_from, filters.date_to);
  const previousLabel = previous
    ? previous.truncated
      ? `${formatIsoDate(previous.date_from)}–${formatIsoDate(previous.date_to)} (janela cortada no início do ano)`
      : `${windowDays} dias anteriores`
    : "";

  return (
    <div className="space-y-4">
      <OverviewFilterBar
        filters={filters}
        visible={visible}
        options={options.data}
        supportOptions={supportOptions.data}
        period={period}
        defaultFilter={defaultFilter}
        onChange={update}
        onResetToDefault={resetToDefault}
        onSaveAsDefault={defaultFilter?.can_manage ? saveAsDefault : undefined}
      />

      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] text-slate-500">
        <span>
          Período <span className="font-semibold text-slate-700">{periodLabel}</span>
          {previous ? <> · comparado com {previousLabel}</> : <> · sem janela anterior comparável</>}
        </span>
        <div className="flex flex-wrap items-center gap-3">
          {previous ? (
            <AppSwitch
              checked={showPreviousPeriod}
              onCheckedChange={toggleShowPreviousPeriod}
              label="Comparar com período anterior"
            />
          ) : null}
          {freshness.data?.last_successful_import_at ? (
            <span>
              Dados do IXC sincronizados às{" "}
              <span className="font-semibold text-slate-700">{formatDateTime(freshness.data.last_successful_import_at)}</span>
            </span>
          ) : null}
        </div>
      </div>

      {/*
        Fixa (sticky) logo abaixo do cabeçalho do ecossistema (`app-shell.tsx`, `sticky top-0
        z-20`, 79px de altura medida ao vivo) - achado real, 2026-09-05: o aviso vivia só no topo
        da página,
        então quem clicava pra detalhar num gráfico ou na tabela lá embaixo (Backlog, SLA,
        "Quadro geral das filiais") precisava rolar de volta pro topo só pra achar o "Voltar".
        Aqui ele acompanha a rolagem, sempre visível enquanto o drill estiver ativo - "o local
        óbvio e evidente" pedido pelo usuário é literalmente "sempre à vista", não um lugar fixo
        na tela. Âmbar (não azul, já usado pelo resto da barra de filtros) pra se destacar como
        um estado temporário, não mais um filtro comum.
      */}
      {isDrilled && preDrillFilters ? (
        <div className="sticky top-[79px] z-10 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] text-amber-900 shadow-md">
          <span className="font-medium">
            Recorte temporário aplicado - clicou num dia, filial ou modelo pra detalhar só aquilo.
          </span>
          <Button
            type="button"
            size="sm"
            className="h-6 bg-amber-600 px-2 text-[11px] text-white hover:bg-amber-700"
            onClick={returnFromDrill}
          >
            <Undo2 className="mr-1 h-3 w-3" />
            Voltar para {formatIsoDate(preDrillFilters.date_from)} - {formatIsoDate(preDrillFilters.date_to)}
          </Button>
        </div>
      ) : null}

      <OverviewKpiStrip
        overview={overview.error ? null : overview.data}
        previous={previousOverview.error ? null : previousOverview.data}
        previousLabel={previousLabel}
        backlog={matrix.data?.total ?? null}
        canSeeSla={canSeeSla}
      />
      {overview.error ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{overview.error}</p>
      ) : null}

      {trends.error ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{trends.error}</p>
      ) : openingsOption ? (
        <OperationsTrendChart
          eyebrow="Fluxo diário"
          title="Aberturas e finalizações por dia"
          description={
            "Barras são O.S. abertas (demanda, sem recorte de equipe); a linha verde são as finalizações, que respeitam todos os filtros" +
            (previousTrendForCharts ? "; a linha cinza tracejada é a mesma finalização, no período anterior" : "") +
            ". Saldo do dia no tooltip. Clique num dia pra detalhar só ele."
          }
          badge={periodLabel}
          option={openingsOption}
          onEvents={trendDrillEvents}
        />
      ) : (
        <div className="h-[300px] animate-pulse rounded-2xl bg-slate-100" aria-label="Carregando gráfico" />
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {canSeeSla ? (
          slaOption ? (
            <OperationsTrendChart
              eyebrow="SLA operacional"
              title="SLA ponderado por dia"
              description={
                "Linha contínua: SLA acumulado ponderado do período. Linha tracejada: SLA do dia" +
                (previousTrendForCharts ? "; linha cinza tracejada: SLA acumulado do período anterior" : "") +
                ". Clique num dia pra detalhar só ele."
              }
              badge="Meta 80%"
              option={slaOption}
              onEvents={trendDrillEvents}
            />
          ) : (
            <div className="h-[300px] animate-pulse rounded-2xl bg-slate-100" aria-label="Carregando gráfico" />
          )
        ) : null}
        {backlogOption ? (
          <OperationsTrendChart
            eyebrow="Backlog"
            title="Histórico de backlog"
            description={
              "Estoque de O.S. em aberto por dia (não soma com abertas/finalizadas - é retrato, não fluxo)" +
              (previousBacklogForChart ? "; linha cinza tracejada: backlog do período anterior" : "") +
              ". Clique num dia pra detalhar só ele." +
              (backlogCoverageNote ? ` ${backlogCoverageNote}` : "")
            }
            option={backlogOption}
            onEvents={backlogDrillEvents}
          />
        ) : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <OverviewShareDonut
          eyebrow="Finalizadas por filial"
          title="Onde a produção se concentra"
          subtitle="Todas as filiais, cada uma com número e cor - sem agrupar em Outros."
          items={completedByRegional}
          totalLabel="finalizadas"
          state={{ loading: matrix.loading, error: matrix.error }}
          onSelect={(regional) => drillFilters({ regionals: [regional] })}
          // Pedido explícito do usuário (2026-09-04): "que os donuts apareça todas filial" - nunca
          // dobrar em "Outros" aqui, mesmo além do teto de cor da paleta (`CATEGORICAL_SLOTS`, 8
          // slots). Além do 8º nome, a fatia cai no cinza neutro (`assignSeriesColors`) e passa a
          // repetir cor com outra(s) filial(is) no ANEL - mas a lista ao lado (nome, número, %)
          // continua distinguindo cada uma individualmente, então nenhum dado fica escondido, só a
          // cor deixa de ser exclusiva a partir da 9ª. Nº de filiais reais hoje (~13-15) já
          // ultrapassa isso.
          maxSlices={completedByRegional.length}
        />
        <OverviewShareDonut
          eyebrow="Finalizadas por modelo de equipe"
          title="Quem executa a produção"
          subtitle="Respeita os filtros aplicados. Clique para recortar por um modelo."
          items={completedByTeamModel}
          totalLabel="finalizadas"
          state={{ loading: workSchedule.loading, error: workSchedule.error }}
          onSelect={(model) => drillFilters({ team_models: [model] })}
        />
        {canSeeSupport ? (
          <OverviewShareDonut
            eyebrow="SGP Suporte"
            title="Atendimentos por canal"
            subtitle="Somente o período - os filtros de O.S. não se aplicam a atendimentos."
            items={attendancesByChannel}
            totalLabel="atendimentos"
            state={{ loading: support.loading, error: support.error }}
          />
        ) : null}
      </div>

      <OverviewRegionalTable
        data={matrix.data}
        capacity={capacity.data?.items ?? null}
        state={{ loading: matrix.loading, error: matrix.error }}
        onDrillRegional={(regional) => drillFilters({ regionals: [regional] })}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        {canSeeSupport ? (
          <OverviewSupportCard
            data={support.data}
            state={{ loading: support.loading, error: support.error }}
            dateFrom={filters.date_from}
            dateTo={filters.date_to}
          />
        ) : null}
        {canSeeGamification ? (
          <OverviewGamificationCard data={gamification.data} state={{ loading: gamification.loading, error: gamification.error }} />
        ) : null}
      </div>

      <StatusToast
        error={feedback.error}
        message={feedback.message}
        onDismissError={() => setFeedback((current) => ({ ...current, error: null }))}
        onDismissMessage={() => setFeedback((current) => ({ ...current, message: null }))}
      />
      {PromptDialog}
    </div>
  );
}
