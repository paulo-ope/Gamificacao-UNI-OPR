"use client";

import dynamic from "next/dynamic";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronsDownUp, ChevronsUpDown, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { OperationsTrendChart } from "@/components/operations/operations-trend-chart";
import { OverviewBlock } from "@/components/overview/overview-block";
import { KpiCard, SPARK_COLOR } from "@/components/overview/overview-kpi-strip";
import { sparkDayLabel } from "@/components/overview/overview-sparkline";
import { OverviewProgress, OverviewSectionHeading, OverviewTile } from "@/components/overview/overview-layout-parts";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { buildDailyFlowOption, buildDiagnosisDonutOption, buildHeatmapOption, buildHourOption, diagnosisColors } from "@/lib/occurrence-chart-options";
import type { SupportOccurrence, SupportOccurrenceGroupStat, SupportOccurrenceOverview } from "@/lib/types";

import { OccurrencesDrillSheet, type OccurrenceSelection } from "./occurrences-drill-sheet";
import { durationLabel, ixcDateTime, number, percent, regionalLabel } from "./occurrences-format";

// Visão geral das Ocorrências (assunto 211 do IXC), no mesmo desenho dos Indicadores do Suporte
// (`dashboard-macros.tsx`): cartões com mini-gráfico, blocos de números e gráficos por seção. Toda a
// regra (em aberto, ranking de regional/diagnóstico, tempos) vive em `occurrences_service.py`; aqui só
// exibe. Todo cartão, número, barra, célula e item de lista é clicável e abre as ocorrências por trás.

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[260px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráfico" />,
});

const NO_DIAGNOSIS = "Sem diagnóstico";

type ChartEvent = { dataIndex?: number; seriesName?: string; value?: unknown };

/** Torna um cartão/bloco clicável sem mexer nos componentes compartilhados da Visão Geral. */
function Clickable({ label, onClick, children, className = "" }: { label: string; onClick: () => void; children: ReactNode; className?: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      className={`block w-full min-w-0 rounded-2xl text-left transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${className}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

/**
 * Item de lista recolhido: só as etiquetas e uma linha do relato; clicar expande o texto completo
 * (e, nas finalizadas, também o relato da abertura). O botão do rodapé abre o painel lateral.
 */
function ItemAccordion({
  item,
  report,
  openingReport,
  expanded,
  onToggle,
  onOpen,
  children,
}: {
  item: SupportOccurrence;
  report: string;
  /** Relato da abertura, mostrado ao expandir uma finalização. */
  openingReport?: string | null;
  expanded: boolean;
  onToggle: () => void;
  onOpen: (item: SupportOccurrence) => void;
  children: ReactNode;
}) {
  return (
    <li className="min-w-0 rounded-xl border border-slate-200 transition hover:border-sky-300">
      <button
        type="button"
        className="flex w-full min-w-0 items-start gap-2 rounded-xl p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        aria-expanded={expanded}
        aria-label={`${expanded ? "Recolher" : "Expandir"} ocorrência ${item.protocol ?? item.source_id}`}
        onClick={onToggle}
      >
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">{children}</span>
          {expanded ? null : <span className="mt-1.5 block truncate text-sm text-slate-600">{report.replace(/\s+/g, " ")}</span>}
        </span>
        <ChevronDown size={16} aria-hidden="true" className={`mt-0.5 shrink-0 text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>
      {expanded ? (
        <div className="grid gap-2 border-t border-slate-100 px-3 pb-3 pt-2">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{openingReport === undefined ? "Relato" : "Relato da finalização"}</p>
            <p className="mt-1 whitespace-pre-line text-sm text-slate-800">{report}</p>
          </div>
          {openingReport ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Relato da abertura</p>
              <p className="mt-1 whitespace-pre-line text-sm text-slate-800">{openingReport}</p>
            </div>
          ) : null}
          <Button variant="outline" size="sm" className="w-fit" onClick={() => onOpen(item)}>
            Ver ocorrência completa
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function toggled(current: ReadonlySet<number>, id: number): ReadonlySet<number> {
  const next = new Set(current);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** Botão do cabeçalho que mostra ou oculta a lista inteira do bloco. */
function ShowListButton({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <Button variant="outline" size="sm" aria-expanded={shown} onClick={onToggle}>
      <ChevronDown size={14} aria-hidden="true" className={`transition-transform ${shown ? "rotate-180" : ""}`} />
      {shown ? "Ocultar lista" : "Mostrar lista"}
    </Button>
  );
}

/** Botão do cabeçalho de uma lista: expande ou recolhe todos os itens de uma vez. */
function ExpandAllButton({ allExpanded, disabled, onToggle }: { allExpanded: boolean; disabled: boolean; onToggle: () => void }) {
  const Icon = allExpanded ? ChevronsDownUp : ChevronsUpDown;
  return (
    <Button variant="outline" size="sm" disabled={disabled} onClick={onToggle}>
      <Icon size={14} aria-hidden="true" />
      {allExpanded ? "Recolher todas" : "Expandir todas"}
    </Button>
  );
}

/** Ranking de regionais: nome completo, barra do total e etiqueta de "em aberto" (cada parte é clicável). */
function RegionalRanking({
  rows,
  onOpenRegional,
}: {
  rows: SupportOccurrenceGroupStat[];
  onOpenRegional: (row: SupportOccurrenceGroupStat, status?: "open") => void;
}) {
  const max = Math.max(1, ...rows.map((row) => row.total));
  return (
    <ol className="grid gap-1.5">
      {rows.map((row, index) => (
        <li key={row.regional} className="flex items-center gap-2">
          <button
            type="button"
            className="grid min-w-0 flex-1 grid-cols-[1.5rem_minmax(0,11rem)_1fr_auto] items-center gap-3 rounded-xl px-2 py-1.5 text-left transition hover:bg-sky-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            aria-label={`Ver ocorrências de ${regionalLabel(row.regional)}`}
            onClick={() => onOpenRegional(row)}
          >
            <span className="text-xs font-semibold tabular-nums text-slate-400">{index + 1}º</span>
            <span className="truncate text-sm font-medium text-slate-800" title={regionalLabel(row.regional)}>{regionalLabel(row.regional)}</span>
            <span className="h-2.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
              <span className="block h-full rounded-full bg-blue-500" style={{ width: `${(row.total / max) * 100}%` }} />
            </span>
            <span className="w-24 text-right text-xs tabular-nums text-slate-500">
              <strong className="text-sm text-slate-900">{number(row.total)}</strong> · {percent(row.share_pct)}
            </span>
          </button>
          {row.open > 0 ? (
            <button
              type="button"
              className="w-24 shrink-0 rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-700 transition hover:bg-amber-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
              aria-label={`Ver ${row.open} em aberto de ${regionalLabel(row.regional)}`}
              onClick={() => onOpenRegional(row, "open")}
            >
              {number(row.open)} em aberto
            </button>
          ) : (
            <span className="w-24 shrink-0 rounded-full bg-emerald-50 px-2 py-1 text-center text-[11px] font-semibold text-emerald-700">tudo finalizado</span>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Rosca de diagnósticos + legenda clicável com nome, quantidade e participação. */
function DiagnosisDonut({
  rows,
  total,
  onOpenDiagnosis,
}: {
  rows: SupportOccurrenceGroupStat[];
  total: number;
  onOpenDiagnosis: (row: SupportOccurrenceGroupStat) => void;
}) {
  const option = useMemo(() => buildDiagnosisDonutOption(rows, total), [rows, total]);
  const colors = useMemo(() => diagnosisColors(rows), [rows]);
  return (
    <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,15rem)_1fr]">
      <div role="img" aria-label="Rosca com a participação de cada diagnóstico">
        <ReactECharts
          option={option}
          notMerge
          lazyUpdate
          opts={{ renderer: "canvas" }}
          style={{ height: 260, width: "100%" }}
          onEvents={{
            click: (params: { dataIndex?: number }) => {
              const row = rows[params.dataIndex ?? -1];
              if (row) onOpenDiagnosis(row);
            },
          }}
        />
      </div>
      <ul className="grid gap-1">
        {rows.map((row, index) => (
          <li key={row.name ?? NO_DIAGNOSIS}>
            <button
              type="button"
              className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition hover:bg-sky-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
              aria-label={`Ver ocorrências de ${row.name ?? NO_DIAGNOSIS}`}
              onClick={() => onOpenDiagnosis(row)}
            >
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colors[index] }} aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-sm text-slate-800" title={row.name ?? NO_DIAGNOSIS}>{row.name ?? NO_DIAGNOSIS}</span>
              <span className="w-20 text-right text-xs tabular-nums text-slate-500">
                <strong className="text-sm text-slate-900">{number(row.total)}</strong> · {percent(row.share_pct)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GroupBlock({
  eyebrow,
  title,
  subtitle,
  stat,
  name,
  onOpen,
  empty,
  finalizedOnly = false,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  stat: SupportOccurrenceGroupStat | null;
  name: string | null;
  onOpen: (status?: "open" | "finalized") => void;
  empty: string;
  /** Diagnóstico só existe na finalização: o bloco mostra apenas as finalizadas (sem "em aberto"). */
  finalizedOnly?: boolean;
}) {
  return (
    <OverviewBlock eyebrow={eyebrow} title={title} subtitle={subtitle} state={stat ? undefined : { empty: true }} emptyLabel={empty}>
      {stat && finalizedOnly ? (
        <>
          <p className="mb-3 truncate text-xl font-bold text-slate-950" title={name ?? undefined}>{name}</p>
          <div className="grid grid-cols-2 gap-2.5">
            <Clickable label={`Ver finalizadas de ${name}`} onClick={() => onOpen()} className="rounded-xl">
              <OverviewTile label="Finalizadas com este diagnóstico" value={number(stat.total)} accent="blue" sub={`${percent(stat.share_pct)} das finalizadas`} />
            </Clickable>
            <OverviewTile label="Tempo médio" value={<span className="text-[1.15rem]">{durationLabel(stat.avg_resolution_minutes)}</span>} accent="violet" sub="Abertura até a finalização" />
          </div>
        </>
      ) : stat ? (
        <>
          <p className="mb-3 truncate text-xl font-bold text-slate-950" title={name ?? undefined}>{name}</p>
          <div className="grid grid-cols-2 gap-2.5">
            <Clickable label={`Ver todas de ${name}`} onClick={() => onOpen()} className="rounded-xl">
              <OverviewTile label="Ocorrências" value={number(stat.total)} accent="blue" sub={`${percent(stat.share_pct)} do total`} />
            </Clickable>
            <Clickable label={`Ver em aberto de ${name}`} onClick={() => onOpen("open")} className="rounded-xl">
              <OverviewTile label="Em aberto" value={number(stat.open)} accent="amber" sub="Sem finalização no IXC" />
            </Clickable>
            <Clickable label={`Ver finalizadas de ${name}`} onClick={() => onOpen("finalized")} className="rounded-xl">
              <OverviewTile label="Finalizadas" value={number(stat.finalized)} accent="teal" sub="Com horário e relato" />
            </Clickable>
            <OverviewTile label="Tempo médio" value={<span className="text-[1.15rem]">{durationLabel(stat.avg_resolution_minutes)}</span>} accent="violet" sub="Abertura até a finalização" />
          </div>
          <OverviewProgress
            leftLabel="Finalizadas"
            leftValue={percent(stat.total ? (stat.finalized / stat.total) * 100 : null)}
            rightLabel="Em aberto"
            rightValue={number(stat.open)}
            percent={stat.total ? (stat.finalized / stat.total) * 100 : null}
          />
        </>
      ) : null}
    </OverviewBlock>
  );
}

type OverviewProps = { dateFrom: string; dateTo: string; regional: string; revision: number };

export function OccurrencesOverview({ dateFrom, dateTo, regional, revision }: OverviewProps) {
  const [data, setData] = useState<SupportOccurrenceOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [selection, setSelection] = useState<OccurrenceSelection | null>(null);
  // Itens expandidos de cada lista de Acompanhamento (por id da ocorrência).
  // Cada lista de Acompanhamento começa recolhida (só título e resumo); o botão do cabeçalho mostra/oculta.
  const [showOpenList, setShowOpenList] = useState(false);
  const [showDoneList, setShowDoneList] = useState(false);
  const [expandedOpen, setExpandedOpen] = useState<ReadonlySet<number>>(new Set());
  const [expandedDone, setExpandedDone] = useState<ReadonlySet<number>>(new Set());

  useEffect(() => {
    if (!dateFrom || !dateTo || dateFrom > dateTo) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportOccurrencesOverview({ date_from: dateFrom, date_to: dateTo, regional })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar a visão geral das ocorrências. Tente novamente ou contate o administrador.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, regional, revision, retry]);

  const dailyOption = useMemo(() => (data ? buildDailyFlowOption(data.daily) : null), [data]);
  const hourOption = useMemo(() => (data ? buildHourOption(data.by_hour) : null), [data]);
  const heatmapOption = useMemo(() => (data ? buildHeatmapOption(data) : null), [data]);

  if (error && !loading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
        <AlertCircle size={20} aria-hidden="true" />
        <p className="mr-auto">{error}</p>
        <Button variant="outline" size="sm" onClick={() => setRetry((current) => current + 1)}>Tentar novamente</Button>
      </div>
    );
  }
  if (!data || !dailyOption || !hourOption || !heatmapOption) {
    return (
      <p className="flex items-center justify-center gap-2 rounded-2xl bg-white p-12 text-sm text-slate-500 shadow-sm" role="status">
        <Loader2 className="animate-spin" size={18} aria-hidden="true" />Carregando visão geral…
      </p>
    );
  }

  const { kpis, daily } = data;
  // Dia de cada ponto dos mini-gráficos (tooltip ao passar o mouse); o tempo médio só existe em dias com finalização.
  const dayLabels = daily.map((point) => sparkDayLabel(point.day));
  const withResolution = daily.filter((point) => point.avg_resolution_minutes != null);
  const delta = kpis.delta_pct;
  const deltaHint =
    kpis.previous_total == null
      ? "Sem período anterior para comparar"
      : delta == null
        ? `Período anterior: ${number(kpis.previous_total)} (amostra pequena)`
        : `${delta > 0 ? "+" : ""}${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(delta)}% vs. período anterior (${number(kpis.previous_total)})`;
  const badge = `${dateFrom.split("-").reverse().slice(0, 2).join("/")} a ${dateTo.split("-").reverse().slice(0, 2).join("/")}`;

  const open = (next: OccurrenceSelection) => setSelection(next);
  const openItem = (item: SupportOccurrence) => open({ title: `Protocolo ${item.protocol ?? item.source_id}`, q: item.protocol ?? item.source_id });
  const suffix = (status?: "open" | "finalized") => (status === "open" ? " · em aberto" : status === "finalized" ? " · finalizadas" : "");
  const topRegional = data.top_regional;
  const topDiagnosis = data.top_diagnosis;
  const openRegionals = data.by_regional.filter((row) => row.open > 0).length;
  const openTone = kpis.open > 0 ? "amber" : "emerald";

  return (
    <div className="grid gap-4" aria-busy={loading}>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Clickable label="Ver todas as ocorrências" onClick={() => open({ title: "Todas as ocorrências" })}>
          <KpiCard label="Ocorrências registradas (assunto 211) - IXC" value={number(kpis.total)} tone="blue" hint={deltaHint} large spark={daily.map((point) => point.opened)} sparkLabels={dayLabels} sparkFormat={number} sparkColor={SPARK_COLOR.blue} />
        </Clickable>
        <Clickable label="Ver ocorrências em aberto" onClick={() => open({ title: "Ocorrências em aberto", status: "open" })}>
          <KpiCard
            label="Ainda não finalizadas - IXC"
            value={number(kpis.open)}
            tone={openTone}
            hint={kpis.total ? `${percent(100 - (kpis.finalization_rate_pct ?? 0))} do total · aberta há mais tempo: ${durationLabel(kpis.oldest_open_minutes)}` : undefined}
            large
            spark={daily.map((point) => point.open)}
            sparkLabels={dayLabels}
            sparkFormat={number}
            sparkColor={kpis.open > 0 ? SPARK_COLOR.amber : SPARK_COLOR.emerald}
          />
        </Clickable>
        <Clickable label="Ver ocorrências finalizadas" onClick={() => open({ title: "Ocorrências finalizadas", status: "finalized" })}>
          <KpiCard
            label="Tempo médio de finalização - IXC"
            value={durationLabel(kpis.avg_resolution_minutes)}
            tone="violet"
            hint={`Mediana ${durationLabel(kpis.median_resolution_minutes)} · da abertura do registro até a finalização`}
            large
            spark={withResolution.map((point) => point.avg_resolution_minutes as number)}
            sparkLabels={withResolution.map((point) => sparkDayLabel(point.day))}
            sparkFormat={durationLabel}
            sparkColor={SPARK_COLOR.violet}
          />
        </Clickable>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 2xl:grid-cols-6">
        <Clickable label="Ver ocorrências finalizadas" onClick={() => open({ title: "Ocorrências finalizadas", status: "finalized" })}>
          <KpiCard label="Finalizadas - IXC" value={number(kpis.finalized)} tone="emerald" hint={`${percent(kpis.finalization_rate_pct)} do total`} spark={daily.map((point) => point.finalized)} sparkLabels={dayLabels} sparkFormat={number} sparkColor={SPARK_COLOR.emerald} />
        </Clickable>
        <Clickable label="Ver regional mais afetada" onClick={() => topRegional && open({ title: regionalLabel(topRegional.regional), regional: topRegional.regional ?? undefined })}>
          <KpiCard label="Regional mais afetada" value={topRegional ? regionalLabel(topRegional.regional) : "—"} tone="red" hint={topRegional ? `${number(topRegional.total)} ocorrências · ${percent(topRegional.share_pct)} do total` : "Sem ocorrências"} spark={[]} sparkColor={SPARK_COLOR.red} />
        </Clickable>
        <Clickable label="Ver diagnóstico mais utilizado" onClick={() => topDiagnosis && open({ title: topDiagnosis.name ?? NO_DIAGNOSIS, diagnosis: topDiagnosis.name ?? undefined })}>
          <KpiCard label="Diagnóstico mais utilizado" value={topDiagnosis?.name ?? "—"} tone="blue" hint={topDiagnosis ? `${number(topDiagnosis.total)} ocorrências · ${percent(topDiagnosis.share_pct)} das finalizadas` : "Nenhum diagnóstico no período"} spark={[]} sparkColor={SPARK_COLOR.blue} />
        </Clickable>
        <Clickable label="Ver ocorrências sem diagnóstico" onClick={() => open({ title: NO_DIAGNOSIS, diagnosis: NO_DIAGNOSIS })}>
          <KpiCard label="Sem diagnóstico - IXC" value={number(kpis.without_diagnosis)} tone="amber" hint="Finalizadas sem diagnóstico no IXC" spark={[]} sparkColor={SPARK_COLOR.amber} />
        </Clickable>
        <Clickable label="Ver regional com mais ocorrências em aberto" onClick={() => data.top_open_regional && open({ title: `${regionalLabel(data.top_open_regional.regional)} · em aberto`, regional: data.top_open_regional.regional ?? undefined, status: "open" })}>
          <KpiCard label="Mais em aberto" value={data.top_open_regional ? regionalLabel(data.top_open_regional.regional) : "—"} tone="red" hint={data.top_open_regional ? `${number(data.top_open_regional.open)} em aberto de ${number(data.top_open_regional.total)}` : "Nenhuma em aberto"} spark={[]} sparkColor={SPARK_COLOR.red} />
        </Clickable>
        <KpiCard label="Regionais com ocorrência" value={number(data.by_regional.length)} tone="slate" hint={`${number(openRegionals)} com ocorrência em aberto`} spark={[]} sparkColor={SPARK_COLOR.blue} />
      </div>

      <OverviewSectionHeading>Quem mais sofre</OverviewSectionHeading>
      <div className="grid gap-4 xl:grid-cols-2">
        <GroupBlock
          eyebrow="Regional · IXC"
          title="Regional mais afetada"
          subtitle="A regional com mais ocorrências no período. Clique num número para ver as ocorrências."
          stat={topRegional}
          name={topRegional ? regionalLabel(topRegional.regional) : null}
          empty="Sem ocorrências no período."
          onOpen={(status) => topRegional && open({ title: `${regionalLabel(topRegional.regional)}${suffix(status)}`, regional: topRegional.regional ?? undefined, status })}
        />
        <GroupBlock
          eyebrow="Diagnóstico · IXC"
          title="Diagnóstico mais utilizado"
          subtitle="O diagnóstico mais registrado nos atendimentos do período. Clique num número para ver as ocorrências."
          stat={topDiagnosis}
          name={topDiagnosis?.name ?? null}
          empty="Nenhuma ocorrência diagnosticada no período."
          finalizedOnly
          onOpen={() => topDiagnosis && open({ title: topDiagnosis.name ?? NO_DIAGNOSIS, diagnosis: topDiagnosis.name ?? undefined })}
        />
      </div>

      <OverviewSectionHeading>Distribuição no período</OverviewSectionHeading>
      <div className="grid gap-4 xl:grid-cols-2">
        <OverviewBlock
          eyebrow="Por regional"
          title="Ocorrências por regional"
          subtitle="Ranking das regionais por quantidade de ocorrências. Clique numa regional, ou na etiqueta de em aberto, para ver as ocorrências."
          badge={badge}
          state={data.by_regional.length ? undefined : { empty: true }}
          emptyLabel="Nenhuma ocorrência no período."
        >
          <RegionalRanking
            rows={data.by_regional}
            onOpenRegional={(row, status) => open({ title: `${regionalLabel(row.regional)}${suffix(status)}`, regional: row.regional ?? undefined, status })}
          />
        </OverviewBlock>
        <OverviewBlock
          eyebrow="Por diagnóstico"
          title="Diagnósticos mais utilizados"
          subtitle="O diagnóstico só é registrado na finalização, então a rosca considera as ocorrências finalizadas. Clique numa fatia, ou na legenda, para ver as ocorrências."
          badge={badge}
          state={data.by_diagnosis.length ? undefined : { empty: true }}
          emptyLabel="Nenhuma ocorrência no período."
        >
          <DiagnosisDonut
            rows={data.by_diagnosis}
            total={kpis.finalized}
            onOpenDiagnosis={(row) => open({ title: row.name ?? NO_DIAGNOSIS, diagnosis: row.name ?? NO_DIAGNOSIS })}
          />
        </OverviewBlock>
      </div>

      <OverviewSectionHeading>Evolução e horários</OverviewSectionHeading>
      <div className="grid gap-4 xl:grid-cols-2">
        <OperationsTrendChart
          eyebrow="Fluxo diário"
          title="Ocorrências abertas e finalizadas por dia"
          description="Barras laranja são as ocorrências abertas no dia e azuis as finalizadas no dia. Clique num dia para ver as ocorrências."
          badge={badge}
          option={dailyOption}
          onEvents={{
            click: (raw) => {
              const point = data.daily[(raw as ChartEvent).dataIndex ?? -1];
              if (point) open({ title: `Ocorrências de ${point.day.split("-").reverse().slice(0, 2).join("/")}`, day: point.day });
            },
          }}
        />
        <OperationsTrendChart
          eyebrow="Horário de abertura"
          title="Em que horas as ocorrências são registradas"
          description="Quantidade de ocorrências abertas em cada hora do dia, no período. Clique numa hora para ver as ocorrências."
          badge={badge}
          option={hourOption}
          onEvents={{
            click: (raw) => {
              const point = data.by_hour[(raw as ChartEvent).dataIndex ?? -1];
              if (point) open({ title: `Abertas às ${String(point.hour).padStart(2, "0")}h`, hour: point.hour });
            },
          }}
        />
      </div>

      <OverviewSectionHeading>Regional × diagnóstico</OverviewSectionHeading>
      {data.matrix.length ? (
        <OperationsTrendChart
          eyebrow="Mapa de calor"
          title="Onde cada tipo de problema mais acontece"
          description="Cruza as regionais e os diagnósticos mais frequentes; quanto mais escuro, mais ocorrências. Clique numa célula para ver as ocorrências."
          badge={badge}
          option={heatmapOption}
          onEvents={{
            click: (raw) => {
              const value = (raw as ChartEvent).value as number[] | undefined;
              if (!value) return;
              const regionalName = data.matrix_regionals[data.matrix_regionals.length - 1 - value[1]];
              const diagnosis = data.matrix_diagnoses[value[0]];
              if (regionalName && diagnosis) open({ title: `${regionalLabel(regionalName)} · ${diagnosis}`, regional: regionalName, diagnosis });
            },
          }}
        />
      ) : (
        <OverviewBlock eyebrow="Mapa de calor" title="Regional × diagnóstico" state={{ empty: true }} emptyLabel="Nenhuma ocorrência no período.">
          <></>
        </OverviewBlock>
      )}

      <OverviewSectionHeading>Acompanhamento</OverviewSectionHeading>
      <div className="grid gap-4 xl:grid-cols-2">
        <OverviewBlock
          eyebrow="Em aberto · IXC"
          title="Ainda não finalizadas"
          subtitle="Mais antigas primeiro. Clique numa ocorrência para expandir ou recolher o relato."
          contentClassName={showOpenList ? "max-h-[560px] overflow-y-auto overflow-x-hidden" : undefined}
          actions={
            <>
              {showOpenList ? (
                <ExpandAllButton
                  allExpanded={data.open_items.length > 0 && expandedOpen.size === data.open_items.length}
                  disabled={!data.open_items.length}
                  onToggle={() => setExpandedOpen(expandedOpen.size === data.open_items.length ? new Set() : new Set(data.open_items.map((item) => item.id)))}
                />
              ) : null}
              <ShowListButton shown={showOpenList} onToggle={() => setShowOpenList((current) => !current)} />
            </>
          }
        >
          {!showOpenList ? (
            <p className="text-sm text-slate-600">
              {number(kpis.open)} {kpis.open === 1 ? "ocorrência em aberto" : "ocorrências em aberto"}
              {kpis.oldest_open_minutes != null ? ` · a mais antiga está aberta há ${durationLabel(kpis.oldest_open_minutes)}` : ""}. Clique em &quot;Mostrar lista&quot; para ver.
            </p>
          ) : data.open_items.length ? (
            <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
              {data.open_items.map((item) => (
                <ItemAccordion
                  key={item.id}
                  item={item}
                  report={item.report ?? "Sem relato"}
                  expanded={expandedOpen.has(item.id)}
                  onToggle={() => setExpandedOpen((current) => toggled(current, item.id))}
                  onOpen={openItem}
                >
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-700">Aberta há {durationLabel(item.open_minutes)}</span>
                  <span className="font-semibold text-slate-800">{regionalLabel(item.regional)}</span>
                  <span>Aberta em {ixcDateTime(item.created_at)}</span>
                  <span>Aguardando finalização</span>
                </ItemAccordion>
              ))}
            </ul>
          ) : (
            <p className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500">
              <CheckCircle2 size={18} aria-hidden="true" />Nenhuma ocorrência em aberto neste período.
            </p>
          )}
          {showOpenList && kpis.open > data.open_items.length ? (
            <Button variant="outline" size="sm" className="mt-3 w-full" onClick={() => open({ title: "Ocorrências em aberto", status: "open" })}>
              Ver todas as {number(kpis.open)} em aberto
            </Button>
          ) : null}
        </OverviewBlock>
        <OverviewBlock
          eyebrow="Finalizadas · IXC"
          title="Últimas finalizações"
          subtitle="Horário e relato de cada finalização. Clique numa ocorrência para expandir ou recolher."
          contentClassName={showDoneList ? "max-h-[560px] overflow-y-auto overflow-x-hidden" : undefined}
          actions={
            <>
              {showDoneList ? (
                <ExpandAllButton
                  allExpanded={data.recent_finalizations.length > 0 && expandedDone.size === data.recent_finalizations.length}
                  disabled={!data.recent_finalizations.length}
                  onToggle={() => setExpandedDone(expandedDone.size === data.recent_finalizations.length ? new Set() : new Set(data.recent_finalizations.map((item) => item.id)))}
                />
              ) : null}
              <ShowListButton shown={showDoneList} onToggle={() => setShowDoneList((current) => !current)} />
            </>
          }
        >
          {!showDoneList ? (
            <p className="text-sm text-slate-600">
              {number(kpis.finalized)} {kpis.finalized === 1 ? "ocorrência finalizada" : "ocorrências finalizadas"}
              {kpis.avg_resolution_minutes != null ? ` · tempo médio de finalização ${durationLabel(kpis.avg_resolution_minutes)}` : ""}. Clique em &quot;Mostrar lista&quot; para ver.
            </p>
          ) : data.recent_finalizations.length ? (
            <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
              {data.recent_finalizations.map((item) => (
                <ItemAccordion
                  key={item.id}
                  item={item}
                  report={item.finalization_report ?? "Finalizada sem relato"}
                  openingReport={item.report}
                  expanded={expandedDone.has(item.id)}
                  onToggle={() => setExpandedDone((current) => toggled(current, item.id))}
                  onOpen={openItem}
                >
                  <span className="rounded-full bg-sky-100 px-2 py-0.5 font-semibold text-sky-700">Finalizada em {ixcDateTime(item.finalized_at)}</span>
                  <span className="font-semibold text-slate-800">{regionalLabel(item.regional)}</span>
                  <span>{item.diagnosis_name ?? NO_DIAGNOSIS}</span>
                  <span>Resolvida em {durationLabel(item.resolution_minutes)}</span>
                </ItemAccordion>
              ))}
            </ul>
          ) : (
            <p className="py-8 text-center text-sm text-slate-500">Nenhuma finalização no período.</p>
          )}
          {showDoneList && kpis.finalized > data.recent_finalizations.length ? (
            <Button variant="outline" size="sm" className="mt-3 w-full" onClick={() => open({ title: "Ocorrências finalizadas", status: "finalized" })}>
              Ver todas as {number(kpis.finalized)} finalizadas
            </Button>
          ) : null}
        </OverviewBlock>
      </div>

      <OccurrencesDrillSheet selection={selection} dateFrom={dateFrom} dateTo={dateTo} regional={regional} onClose={() => setSelection(null)} />
    </div>
  );
}
