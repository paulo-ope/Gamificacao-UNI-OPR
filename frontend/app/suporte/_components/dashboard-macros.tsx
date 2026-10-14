"use client";

import { AlertTriangle, ListFilter } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { OperationsTrendChart } from "@/components/operations/operations-trend-chart";
import { OverviewBlock } from "@/components/overview/overview-block";
import { KpiCard, SPARK_COLOR } from "@/components/overview/overview-kpi-strip";
import { OverviewProgress, OverviewSectionHeading, OverviewTile } from "@/components/overview/overview-layout-parts";
import { MultiSelect } from "@/components/ui/multi-select";
import { api } from "@/lib/api";
import { formatInteger, formatPercent } from "@/lib/format";
import { percentChange } from "@/lib/period";
import { buildSupportDailyFlowOption, buildSupportWeeklyOption } from "@/lib/support-dashboard-chart-options";
import type { SupportMacroCard, SupportMacroCardStatus, SupportMacroDailyPoint, SupportMacroDashboard, SupportOpaFilterOption } from "@/lib/types";
import type { Tone } from "@/lib/tones";

import { DashboardGoalRings } from "./dashboard-goal-rings";
import { STATUS_TONE, coverageNote, formatCardChange, formatCardTarget, formatCardValue, isGoodWhenUp } from "./dashboard-format";
import { IxcPeriodBar, useIxcPeriod } from "./ixc-n1-panel";

// Dashboard Suporte (pedido do usuário, 2026-10-14), montado com os mesmos componentes e gráficos da Visão
// Geral (`/visao-geral`): faixa de cartões com mini-gráfico, anéis de meta, blocos de números, fluxo diário.
// Fórmulas, metas e status vivem no backend (`dashboard_macros.py`); esta tela só formata e desenha.

// Cor do valor/mini-gráfico quando o cartão não tem meta (então não há status para colorir).
const NO_TARGET_VIEW: Record<string, { tone: Tone; spark: string }> = {
  performed: { tone: "blue", spark: SPARK_COLOR.blue },
  solved: { tone: "emerald", spark: SPARK_COLOR.emerald },
  field: { tone: "violet", spark: SPARK_COLOR.violet },
  n2_total: { tone: "blue", spark: SPARK_COLOR.amber },
  tmr_human: { tone: "violet", spark: SPARK_COLOR.violet },
};

const STATUS_SPARK: Record<SupportMacroCardStatus, string> = {
  ok: SPARK_COLOR.emerald,
  attention: SPARK_COLOR.amber,
  critical: SPARK_COLOR.red,
  partial: SPARK_COLOR.blue,
  no_data: SPARK_COLOR.blue,
  no_target: SPARK_COLOR.blue,
};

function compact(values: readonly (number | null | undefined)[]) {
  return values.filter((value): value is number => typeof value === "number");
}

// Série diária de cada cartão para o mini-gráfico; dia sem atendimento no OPA não entra (sem inventar zero).
function sparkSeries(key: string, daily: readonly SupportMacroDailyPoint[]): number[] {
  switch (key) {
    case "csat":
      return compact(daily.map((point) => point.rating));
    case "tmr":
      return compact(daily.map((point) => point.tmr_seconds));
    case "tmr_human":
      return compact(daily.map((point) => point.tmr_human_seconds));
    case "tma":
      return compact(daily.map((point) => point.tma_seconds));
    case "performed":
      return daily.map((point) => point.performed);
    case "solved":
      return daily.map((point) => point.solved);
    case "field":
      return daily.map((point) => point.field);
    case "n2_total":
      return daily.map((point) => point.n2_total ?? 0);
    case "resolutivity":
      return daily.filter((point) => point.performed > 0).map((point) => (point.solved / point.performed) * 100);
    default:
      return [];
  }
}

// Macros (cartões grandes, no topo): os três indicadores do OPA. O restante da faixa entra como micros.
const MACRO_KEYS = ["csat", "tmr", "tma"];

function MacroKpiCard({ card, daily, previousLabel, large = false }: { card: SupportMacroCard; daily: readonly SupportMacroDailyPoint[]; previousLabel: string; large?: boolean }) {
  const noTarget = NO_TARGET_VIEW[card.key];
  const tone: Tone = card.status === "no_target" || card.status === "no_data" || card.status === "partial" ? (noTarget?.tone ?? "blue") : STATUS_TONE[card.status];
  const target = formatCardTarget(card);
  // Percentual relativo não faz sentido sobre um indicador que já é percentual: aí a variação é em p.p.
  const showPercentDelta = card.unit !== "percent";
  const hint = [card.unit === "percent" ? `${formatCardChange(card) ?? "sem base"} vs. ${previousLabel}` : null, target, coverageNote(card)].filter(Boolean).join(" · ");
  return (
    <KpiCard
      label={card.label}
      value={formatCardValue(card, card.value)}
      tone={tone}
      delta={showPercentDelta ? { value: percentChange(card.value, card.previous), goodWhenUp: isGoodWhenUp(card), againstLabel: previousLabel } : undefined}
      hint={hint || undefined}
      large={large}
      spark={sparkSeries(card.key, daily)}
      sparkColor={card.status === "no_target" || card.status === "no_data" || card.status === "partial" ? (noTarget?.spark ?? SPARK_COLOR.blue) : STATUS_SPARK[card.status]}
    />
  );
}

function countChange(current: number | null, previous: number | null | undefined, label: string) {
  if (current === null || previous === null || previous === undefined) return "sem base de comparação";
  const diff = current - previous;
  return `${diff > 0 ? "+" : ""}${formatInteger(diff)} vs. ${label}`;
}

function periodShort(from: string | null, to: string | null) {
  if (!from || !to) return null;
  const short = (iso: string) => iso.split("-").reverse().slice(0, 2).join("/");
  return `${short(from)} a ${short(to)}`;
}

function monthTitle(month: string) {
  const [year, number] = month.split("-");
  const names = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  return `${names[Number(number) - 1] ?? number}/${year}`;
}

function DashboardBody({ data }: { data: SupportMacroDashboard }) {
  const cards = useMemo(() => Object.fromEntries(data.cards.map((card) => [card.key, card])) as Record<string, SupportMacroCard>, [data.cards]);
  const previousPeriod = periodShort(data.previous_date_from, data.previous_date_to);
  const previousLabel = previousPeriod ? `ant. (${previousPeriod})` : "período anterior";
  const dailyOption = useMemo(() => buildSupportDailyFlowOption(data.daily, data.previous_daily), [data.daily, data.previous_daily]);
  const weeks = useMemo(() => data.weekly.buckets.filter((bucket) => bucket.key !== "month"), [data.weekly.buckets]);
  const monthly = data.weekly.buckets.find((bucket) => bucket.key === "month");
  const weeklyOption = useMemo(() => buildSupportWeeklyOption(weeks), [weeks]);
  const hasWeeklyData = weeks.some((week) => week.performed > 0);

  const { performed, solved, field, resolutivity, csat, tmr, tmr_human: tmrHuman, tma } = cards;
  const changeHint = (card: SupportMacroCard | undefined) => (card ? `${formatCardChange(card) ?? "sem base"} vs. ${previousLabel}` : undefined);

  return (
    <>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {data.cards
          .filter((card) => MACRO_KEYS.includes(card.key))
          .map((card) => (
            <MacroKpiCard key={card.key} card={card} daily={data.daily} previousLabel={previousLabel} large />
          ))}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 2xl:grid-cols-6">
        {data.cards
          .filter((card) => !MACRO_KEYS.includes(card.key))
          .map((card) => (
            <MacroKpiCard key={card.key} card={card} daily={data.daily} previousLabel={previousLabel} />
          ))}
      </div>

      <OverviewSectionHeading>Qualidade e nível de serviço</OverviewSectionHeading>
      <DashboardGoalRings cards={data.cards} previousLabel="vs. ant." />

      <OverviewSectionHeading>Volume e eficiência operacional</OverviewSectionHeading>
      <div className="grid gap-4 xl:grid-cols-2">
        <OverviewBlock
          eyebrow="Suporte Interno N1 · IXC"
          title="Atendimentos do período"
          subtitle="Protocolos N1 (operacional + financeiro) e O.S. abertas para campo pelos colaboradores N1 (vínculo pelo nome do criador da O.S.)."
        >
          <div className="grid grid-cols-2 gap-2.5">
            <OverviewTile label="Realizados" value={formatInteger(performed?.value)} accent="blue" sub={changeHint(performed)} />
            <OverviewTile label="Solucionados" value={formatInteger(solved?.value)} accent="teal" sub={changeHint(solved)} />
            <OverviewTile label="Foi a campo" value={formatInteger(field?.value)} accent="amber" sub={changeHint(field)} />
            <OverviewTile
              label="Resolutividade"
              value={formatPercent(resolutivity?.value)}
              accent="violet"
              sub={`${formatCardTarget(resolutivity ?? { unit: "percent", target: null, direction: "min" }) ?? ""} · ${changeHint(resolutivity) ?? ""}`}
            />
          </div>
          <OverviewProgress
            leftLabel="Solucionados"
            leftValue={formatPercent(resolutivity?.value)}
            rightLabel="Foi a campo"
            rightValue={formatInteger(field?.value)}
            percent={resolutivity?.value ?? null}
          />
        </OverviewBlock>

        <OverviewBlock
          eyebrow="Suporte Interno · OPA"
          title="Qualidade e tempos de atendimento"
          subtitle="Mesmos cálculos da Visão Geral do OPA: CSAT, TMR (geral inclui o bot; humano só respostas de humano) e TMA humano."
        >
          <div className="grid grid-cols-2 gap-2.5">
            <OverviewTile label="Qualidade percebida (CSAT)" value={formatCardValue({ unit: "score" }, csat?.value)} accent="blue" sub={`${formatCardTarget(csat) ?? ""} · ${changeHint(csat) ?? ""}`} />
            <OverviewTile label="TMR Geral" value={<span className="text-[1.15rem]">{formatCardValue({ unit: "seconds" }, tmr?.value)}</span>} accent="violet" sub={`${formatCardTarget(tmr) ?? ""} · ${changeHint(tmr) ?? ""}`} />
            <OverviewTile label="TMR Humano" value={<span className="text-[1.15rem]">{formatCardValue({ unit: "seconds" }, tmrHuman?.value)}</span>} accent="violet" sub={`Sem meta definida · ${changeHint(tmrHuman) ?? ""}`} />
            <OverviewTile label="TMA Humano" value={<span className="text-[1.15rem]">{formatCardValue({ unit: "seconds" }, tma?.value)}</span>} accent="teal" sub={`${formatCardTarget(tma) ?? ""} · ${changeHint(tma) ?? ""}`} />
          </div>
        </OverviewBlock>
      </div>

      <OverviewSectionHeading>Suporte N2</OverviewSectionHeading>
      <OverviewBlock
        eyebrow="Suporte N2 · IXC"
        title="Atendimentos, O.S. e Ativação de Novo Login"
        subtitle="Protocolos de Atendimento Interno N2 (motivo 80) e Externo N2 (motivo 81); O.S. abertas pelos colaboradores N2; e O.S. de Ativação de Novo Login/Transferência de Comodato (assunto 74) finalizadas no período. O Novo Login vem direto do IXC (atualiza a cada ~2 minutos)."
      >
        <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
          <OverviewTile label="Atendimentos Interno N2" value={formatInteger(data.n2.internal)} accent="blue" sub={countChange(data.n2.internal, data.previous_n2?.internal, previousLabel)} />
          <OverviewTile label="Atendimentos Externo N2" value={formatInteger(data.n2.external)} accent="amber" sub={countChange(data.n2.external, data.previous_n2?.external, previousLabel)} />
          <OverviewTile label="O.S. abertas pelo N2" value={formatInteger(data.n2.orders)} accent="violet" sub={countChange(data.n2.orders, data.previous_n2?.orders, previousLabel)} />
          <OverviewTile
            label="Ativação de Novo Login finalizadas"
            value={formatInteger(data.n2.new_login_finalized)}
            accent="teal"
            sub={
              data.n2.new_login_error ??
              `${formatInteger(data.n2.new_login_finalized_by_n2)} finalizadas pelo N2 · ${countChange(data.n2.new_login_finalized, data.previous_n2?.new_login_finalized, previousLabel)}`
            }
          />
        </div>
        <div className="mt-4 border-t border-slate-200 pt-4">
          <p className="mb-2 text-xs font-semibold text-slate-700">Atendimentos e O.S. abertas por colaborador N2</p>
          {data.n2_collaborators.rows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[400px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-3 font-medium">Colaborador</th>
                    <th className="px-3 py-2 text-right font-medium">Interno N2</th>
                    <th className="px-3 py-2 text-right font-medium">Externo N2</th>
                    <th className="py-2 pl-3 text-right font-medium">O.S. abertas</th>
                  </tr>
                </thead>
                <tbody>
                  {data.n2_collaborators.rows.map((row) => (
                    <tr key={row.user_id} className="border-b border-slate-100 last:border-0">
                      <td className="py-2 pr-3 text-slate-800">
                        {row.name}
                        {!row.active ? (
                          <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase text-slate-500">Inativo</span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-700">{formatInteger(row.internal)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-700">{formatInteger(row.external)}</td>
                      <td className="py-2 pl-3 text-right font-semibold tabular-nums text-slate-900">{formatInteger(row.orders)}</td>
                    </tr>
                  ))}
                  {data.n2_collaborators.others_internal || data.n2_collaborators.others_external ? (
                    <tr className="border-t border-slate-200 text-slate-500">
                      <td className="py-2 pr-3" title="Protocolos N2 abertos por quem não está na lista de colaboradores N2, ou sem operador">
                        Outros operadores
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatInteger(data.n2_collaborators.others_internal)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatInteger(data.n2_collaborators.others_external)}</td>
                      <td className="py-2 pl-3 text-right">-</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="py-3 text-sm text-slate-500">Nenhum colaborador N2 cadastrado.</p>
          )}
        </div>
      </OverviewBlock>

      <OverviewSectionHeading>Evolução no período</OverviewSectionHeading>
      <div className="grid gap-4 xl:grid-cols-2">
        <OperationsTrendChart
          eyebrow="Fluxo diário"
          title="Atendimentos realizados por dia"
          description="Barras são os atendimentos realizados (protocolos N1 + O.S. para campo; rosa quando o dia foge do padrão); linhas verde e laranja são os solucionados e os que foram a campo; a linha cinza tracejada é o total do período anterior."
          badge={`${data.date_from.split("-").reverse().slice(0, 2).join("/")} a ${data.date_to.split("-").reverse().slice(0, 2).join("/")}`}
          option={dailyOption}
        />
        {hasWeeklyData ? (
          <OperationsTrendChart
            eyebrow="Evolução semanal"
            title="Atendimentos por semana"
            description={`Semanas de domingo a sábado, cortadas nos limites do mês${monthly ? `; no mês: ${formatInteger(monthly.performed)} realizados, ${formatInteger(monthly.solved)} solucionados, ${formatInteger(monthly.field)} a campo` : ""}.`}
            badge={monthTitle(data.weekly.month)}
            option={weeklyOption}
          />
        ) : (
          <OverviewBlock eyebrow="Evolução semanal" title="Atendimentos por semana" state={{ empty: true }} emptyLabel="Nenhum atendimento N1 no mês.">
            <></>
          </OverviewBlock>
        )}
      </div>
    </>
  );
}

export function DashboardMacros() {
  const [period, setPeriod] = useIxcPeriod();
  // Filtros do OPA (departamento e colaborador/atendente): valem só para os indicadores do OPA (CSAT, TMR, TMA).
  const [departmentIds, setDepartmentIds] = useState<string[]>([]);
  const [attendantIds, setAttendantIds] = useState<string[]>([]);
  const [departments, setDepartments] = useState<SupportOpaFilterOption[]>([]);
  const [attendants, setAttendants] = useState<SupportOpaFilterOption[]>([]);
  const [data, setData] = useState<SupportMacroDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const invalidPeriod = !period.date_from || !period.date_to || period.date_to < period.date_from;

  // Departamentos: os do OPA (mesma fonte da tela Dados). Colaboradores: a equipe FIXA do Suporte Técnico
  // (lista no backend, `dashboard_macros.SUPPORT_TEAM`). Se uma das consultas falhar, o seletor fica vazio e o
  // resto do dashboard funciona.
  useEffect(() => {
    let cancelled = false;
    api
      .supportOpaFilters()
      .then((options) => {
        if (!cancelled) setDepartments(options.departments);
      })
      .catch(() => undefined);
    api
      .supportDashboardCollaborators()
      .then((options) => {
        if (!cancelled) setAttendants(options);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const departmentKey = departmentIds.join(",");
  const attendantKey = attendantIds.join(",");

  useEffect(() => {
    if (invalidPeriod) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportMacroDashboard({ ...period, department_id: departmentKey || undefined, attendant_id: attendantKey || undefined })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Falha ao carregar o Dashboard Suporte.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period, invalidPeriod, departmentKey, attendantKey]);

  return (
    <div className="grid gap-3">
      <IxcPeriodBar period={period} onChange={setPeriod} />
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <ListFilter className="h-4 w-4 text-slate-400" aria-hidden />
        <MultiSelect<SupportOpaFilterOption>
          className="h-8 w-56 text-[11px]"
          values={departmentIds}
          options={departments}
          getValue={(option) => option.value}
          formatOption={(option) => option.label}
          placeholder="Todos os departamentos"
          ariaLabel="Departamento do OPA"
          onChange={setDepartmentIds}
        />
        <MultiSelect<SupportOpaFilterOption>
          className="h-8 w-56 text-[11px]"
          values={attendantIds}
          options={attendants}
          getValue={(option) => option.value}
          formatOption={(option) => option.label}
          placeholder="Todos os colaboradores"
          ariaLabel="Colaborador do OPA"
          onChange={setAttendantIds}
        />
        <p className="text-[11px] text-slate-500">
          Os filtros de departamento e colaborador valem para os indicadores do OPA (CSAT, TMR e TMA). Protocolos, O.S. e N2 do IXC não mudam.
        </p>
      </div>

      {invalidPeriod ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 shadow-sm">
          <AlertTriangle className="h-4 w-4" aria-hidden /> Informe um período válido: a data final não pode ser anterior à inicial.
        </div>
      ) : error ? (
        <div role="alert" className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
          <AlertTriangle className="h-4 w-4" aria-hidden /> {error}
        </div>
      ) : loading || !data ? (
        <div aria-busy className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="h-44 animate-pulse rounded-2xl bg-slate-100" />
          ))}
        </div>
      ) : (
        <DashboardBody data={data} />
      )}
    </div>
  );
}
