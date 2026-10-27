"use client";

import { AlertTriangle, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { OverviewBlock } from "@/components/overview/overview-block";
import { KpiCard, SPARK_COLOR } from "@/components/overview/overview-kpi-strip";
import { sparkDayLabel } from "@/components/overview/overview-sparkline";
import { api } from "@/lib/api";
import { percentChange } from "@/lib/period";
import type { SupportFeedback, SupportFeedbackDetails, SupportFeedbackIndicator, SupportMacroCardStatus, SupportOpaFilterOption } from "@/lib/types";
import type { Tone } from "@/lib/tones";

import { STATUS_TONE, coverageNote, formatCardChange, formatCardTarget, formatCardValue, formatPreviousLine, isGoodWhenUp } from "./dashboard-format";
import { buildFeedbackAnalysis } from "./feedback-analysis";
import { STATUS_LABEL, dateBr, periodTargetLabel } from "./feedback-format";
import { FeedbackTeamTable } from "./feedback-team-table";
import { IxcPeriodBar, useIxcPeriod } from "./ixc-n1-panel";

// Feedback individual do Suporte (pedido do usuário, 2026-10-16): escolhe o colaborador e mostra, no mesmo desenho
// dos Indicadores do Suporte, os números dele contra as metas individuais. Valores, metas e status vêm prontos do
// backend (`feedback_service.py`); esta tela só formata, desenha e monta o plano de ação (que não é salvo no banco).

const STATUS_BADGE: Record<SupportMacroCardStatus, string> = {
  ok: "bg-emerald-600 text-white",
  attention: "bg-amber-400 text-amber-950",
  critical: "bg-red-500 text-white",
  partial: "bg-slate-200 text-slate-700",
  no_data: "bg-slate-200 text-slate-700",
  no_target: "bg-slate-200 text-slate-700",
};

const SPARK_BY_STATUS: Record<SupportMacroCardStatus, string> = {
  ok: SPARK_COLOR.emerald,
  attention: SPARK_COLOR.amber,
  critical: SPARK_COLOR.red,
  partial: SPARK_COLOR.blue,
  no_data: SPARK_COLOR.blue,
  no_target: SPARK_COLOR.blue,
};

// Valor e dia de cada ponto do mini-gráfico (e do tooltip); dia sem valor não entra.
function sparkFor(key: string, daily: SupportFeedback["daily"]): { values: number[]; labels: string[] } {
  const read = (point: SupportFeedback["daily"][number]): number | null => {
    switch (key) {
      case "operational":
      case "financial":
      case "field":
      case "opa_attendances":
        return point[key];
      case "rating":
        return point.rating;
      case "tma":
        return point.tma_seconds;
      case "tmr":
        return point.tmr_seconds;
      default:
        return null;
    }
  };
  const result: { values: number[]; labels: string[] } = { values: [], labels: [] };
  for (const point of daily) {
    const value = read(point);
    if (typeof value === "number") {
      result.values.push(value);
      result.labels.push(sparkDayLabel(point.day));
    }
  }
  return result;
}

function IndicatorKpi({ indicator, daily, previousLabel, extra }: { indicator: SupportFeedbackIndicator; daily: SupportFeedback["daily"]; previousLabel: string; extra?: string }) {
  const tone: Tone = STATUS_TONE[indicator.status];
  const change = indicator.value !== null && indicator.previous !== null ? indicator.value - indicator.previous : null;
  const spark = sparkFor(indicator.key, daily);
  const hint = [
    periodTargetLabel(indicator).replace("Mínimo", "Meta ≥").replace("Até", "Meta ≤"),
    coverageNote({ status: indicator.status, coverage: indicator.coverage }),
    indicator.note,
    extra,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <KpiCard
      label={indicator.label}
      value={formatCardValue(indicator, indicator.value)}
      tone={tone}
      delta={{
        value: percentChange(indicator.value, indicator.previous),
        goodWhenUp: isGoodWhenUp({ target: indicator.target, direction: indicator.direction }),
        againstLabel: previousLabel,
      }}
      // Pedido do usuário (2026-10-27): mostrar o resultado da semana anterior ("Antes"), igual aos Indicadores do Suporte.
      previousLine={formatPreviousLine({ unit: indicator.unit, value: indicator.value, previous: indicator.previous, change }) ?? undefined}
      hint={hint || (change !== null ? `${formatCardChange({ unit: indicator.unit, change })} vs. ${previousLabel}` : undefined)}
      spark={spark.values}
      sparkLabels={spark.labels}
      sparkFormat={(point) => formatCardValue({ unit: indicator.unit }, point)}
      sparkColor={SPARK_BY_STATUS[indicator.status]}
    />
  );
}

function FeedbackBody({ data }: { data: SupportFeedback }) {
  const [details, setDetails] = useState<SupportFeedbackDetails | null>(null);
  const [plan, setPlan] = useState("");
  const previousLabel = data.previous_date_from && data.previous_date_to ? `ant. (${dateBr(data.previous_date_from).slice(0, 5)} a ${dateBr(data.previous_date_to).slice(0, 5)})` : "período anterior";
  const overallStatus: SupportMacroCardStatus = data.summary.overall;

  useEffect(() => {
    let cancelled = false;
    api
      .supportFeedbackDetails({ date_from: data.date_from, date_to: data.date_to, attendant_id: data.attendant_id })
      .then((result) => {
        if (!cancelled) setDetails(result);
      })
      .catch(() => {
        // Sem a soma o feedback continua inteiro; só some a linha extra.
      });
    return () => {
      cancelled = true;
    };
  }, [data.attendant_id, data.date_from, data.date_to]);

  // Só a soma (pedido do usuário, 2026-10-27): notas boas/ruins do OPA e O.S. indevidas do IXC, em linha de texto.
  const extra: Record<string, string> = {};
  if (details) {
    const { good, bad } = details.ratings;
    if (details.ratings.rated_count) extra.rating = `${good.count} ${good.count === 1 ? "nota boa" : "notas boas"} · ${bad.count} ${bad.count === 1 ? "ruim" : "ruins"}`;
    if (details.improper_orders) extra.field = `${details.improper_orders.improper_count} de ${details.improper_orders.total_orders} indevidas`;
  }

  const analysis = useMemo(() => buildFeedbackAnalysis(data, details), [data, details]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="min-w-[200px]">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Colaborador</p>
          <p className="text-lg font-bold text-slate-900">{data.name}</p>
          <p className="text-xs text-slate-500">
            {dateBr(data.date_from)} a {dateBr(data.date_to)}
            {data.goal_scale !== 1 ? ` · metas de contagem proporcionais a ${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(data.goal_scale * 7)} dias` : ""}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Status</p>
          <span className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-bold ${STATUS_BADGE[overallStatus]}`}>{STATUS_LABEL[overallStatus]}</span>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Dentro da meta</p>
          <p className="text-lg font-bold text-slate-900">{data.summary.ok}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Atenção</p>
          <p className="text-lg font-bold text-slate-900">{data.summary.attention}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Evoluir</p>
          <p className="text-lg font-bold text-slate-900">{data.summary.critical}</p>
        </div>
      </div>

      {!data.ixc_linked ? (
        <div role="status" className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 shadow-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden /> Colaborador não encontrado no IXC pelo nome: registros e O.S. a campo aparecem sem valor.
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        {data.indicators.map((indicator) => (
          <IndicatorKpi key={indicator.key} indicator={indicator} daily={data.daily} previousLabel={previousLabel} extra={extra[indicator.key]} />
        ))}
      </div>

      <div className="grid gap-4">
        <div className="grid gap-4">
          <OverviewBlock eyebrow="Plano de ação" title="Combinado da conversa" subtitle="Texto livre, só nesta tela; não é salvo.">
            <textarea
              value={plan}
              onChange={(event) => setPlan(event.target.value)}
              rows={6}
              aria-label="Combinado da conversa"
              placeholder="Ex.: Meta da próxima semana: reduzir o TMR para até 00:02:20 e manter a O.S. a campo em até 25. Acompanhar diariamente."
              className="w-full resize-y rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none"
            />
          </OverviewBlock>

          <OverviewBlock eyebrow="Análise" title="Análise do período" subtitle="Gerada dos indicadores, das notas do OPA e das O.S. a campo deste colaborador.">
            <div className="grid gap-4">
              {analysis.map((section) => (
                <div key={section.title}>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{section.title}</p>
                  <ul className="grid gap-1.5 text-sm text-slate-800">
                    {section.lines.map((line) => (
                      <li key={line} className="flex gap-2">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" aria-hidden />
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </OverviewBlock>
        </div>
      </div>
    </>
  );
}

export function FeedbackPanel() {
  const [period, setPeriod] = useIxcPeriod();
  const [collaborators, setCollaborators] = useState<SupportOpaFilterOption[]>([]);
  const [attendantId, setAttendantId] = useState("");
  const [data, setData] = useState<SupportFeedback | null>(null);
  const [team, setTeam] = useState<SupportFeedback[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidPeriod = !period.date_from || !period.date_to || period.date_to < period.date_from;

  useEffect(() => {
    let cancelled = false;
    api
      .supportDashboardCollaborators()
      .then((options) => {
        if (!cancelled) setCollaborators(options);
      })
      .catch(() => {
        if (!cancelled) setError("Falha ao carregar a lista de colaboradores.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (attendantId || invalidPeriod) return;
    let cancelled = false;
    setTeam(null);
    setError(null);
    api
      .supportFeedbackTeam(period)
      .then((result) => {
        if (!cancelled) setTeam(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Falha ao carregar o feedback da equipe.");
      });
    return () => {
      cancelled = true;
    };
  }, [period, invalidPeriod, attendantId]);

  useEffect(() => {
    if (!attendantId || invalidPeriod) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportFeedback({ ...period, attendant_id: attendantId })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setData(null);
          setError(reason instanceof Error ? reason.message : "Falha ao carregar o feedback do colaborador.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period, invalidPeriod, attendantId]);

  return (
    <div className="grid gap-3">
      <IxcPeriodBar period={period} onChange={setPeriod} />
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <UserRound className="h-4 w-4 text-slate-400" aria-hidden />
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Colaborador
          <select
            value={attendantId}
            onChange={(event) => {
              setAttendantId(event.target.value);
              setData(null);
            }}
            className="h-8 w-64 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
          >
            <option value="">Todos os colaboradores</option>
            {collaborators.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <p className="text-[11px] text-slate-500">Período de até 30 dias. As metas de contagem são semanais e se ajustam ao tamanho do período.</p>
      </div>

      {invalidPeriod ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 shadow-sm">
          <AlertTriangle className="h-4 w-4" aria-hidden /> Informe um período válido: a data final não pode ser anterior à inicial.
        </div>
      ) : error ? (
        <div role="alert" className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
          <AlertTriangle className="h-4 w-4" aria-hidden /> {error}
        </div>
      ) : !attendantId ? (
        team ? (
          <FeedbackTeamTable team={team} onSelect={setAttendantId} />
        ) : (
          <div aria-busy className="grid gap-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="h-10 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        )
      ) : loading || !data ? (
        <div aria-busy className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-36 animate-pulse rounded-2xl bg-slate-100" />
          ))}
        </div>
      ) : (
        <FeedbackBody key={`${data.attendant_id}-${data.date_from}-${data.date_to}`} data={data} />
      )}
    </div>
  );
}
