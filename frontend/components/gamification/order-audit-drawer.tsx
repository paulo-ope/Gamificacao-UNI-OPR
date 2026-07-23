"use client";

import { ChevronDown, FileSearch, Minus, Repeat, Sigma } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Info } from "@/components/ui/info-field";
import { Separator } from "@/components/ui/separator";
import { SecondaryPill, StatusBadge } from "@/components/ui/status-badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SummaryMetric } from "@/components/ui/summary-metric";
import { api } from "@/lib/api";
import { formatAnnulledPoints, formatDateTime, formatHours, formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { cleanOperationalText, recurrenceClassificationLabel, resolveRecurrenceDisplay } from "@/lib/recurrence-display";
import { regionalName } from "@/lib/regional";
import { type Tone, scoringStatusEntry, toneBadgeClass } from "@/lib/tones";
import type { CollaboratorOrderDetail, RecurrenceAudit } from "@/lib/types";

type AuditableOrder = CollaboratorOrderDetail & {
  collaborator_name?: string;
};

type OrderAuditDrawerProps = {
  order: AuditableOrder;
  label?: string;
};

type OrderAuditSheetProps = {
  order: AuditableOrder | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  calculationRunId?: number;
};

function safeText(value: string | number | null | undefined, fallback = "Não informado") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function yesNo(value: boolean) {
  return value ? "Sim" : "Não";
}

function diagnosisActionLabel(value: string | null | undefined) {
  if (value === "subtract_points") return "anular pontos fixos";
  if (value === "cancel_points") return "anular pontos";
  if (value === "requires_review") return "exigir revisão manual";
  if (value === "force_points") return "forçar pontuação";
  if (value === "no_penalty") return "não anular";
  return "ação não informada";
}

function slaPenaltyLabel(value: string | null | undefined) {
  if (value === "subtract_points") return "anular pontos fixos";
  if (value === "percentage_reduction") return "reduzir percentual";
  if (value === "cancel_points") return "anular pontos";
  if (value === "requires_review") return "exigir revisão manual";
  if (value === "none") return "não anular";
  return "sem regra aplicada";
}

function wasSuppressed(reason: string | null | undefined) {
  const normalized = (reason ?? "").toLowerCase();
  return normalized.includes("ignorada") || normalized.includes("nao foi aplicado") || normalized.includes("não foi aplicado");
}

function auditTone(order: AuditableOrder) {
  if (order.is_annulled) return "border-red-200 bg-red-50 text-red-700";
  if (order.is_unscored) return "border-amber-200 bg-amber-50 text-amber-800";
  if (order.requires_manual_review) return "border-blue-200 bg-blue-50 text-blue-700";
  if (order.is_penalized) return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function auditOutcomeLabel(order: AuditableOrder) {
  if (order.is_annulled) return "O.S anulada";
  if (order.is_unscored) return "Sem regra";
  if (order.requires_manual_review) return "Revisão manual";
  if (order.is_penalized) return "Pontuada com pontos anulados";
  return "O.S pontuada";
}

function recurrencePlainReason(order: AuditableOrder) {
  const relation = order.recurrence_related_os_code ? ` pela O.S de retorno ${order.recurrence_related_os_code}` : "";
  const days =
    order.recurrence_days_between !== null && order.recurrence_days_between !== undefined
      ? ` dentro de ${order.recurrence_days_between} dia(s)`
      : "";
  if (order.recurrence_discount_applied) {
    return `Esta O.S foi anulada porque houve retorno do mesmo contrato/login${days}${relation}.`;
  }
  if (order.recurrence_classification === "possivel_retorno_sem_regra") {
    return `Retorno encontrado dentro da janela${relation}, mas sem regra ativa para classificar como reincidência.`;
  }
  if (order.recurrence_classification) {
    return `Foi encontrada uma ocorrência relacionada${relation}, mas a regra atual não anulou pontos.`;
  }
  return "Não foi encontrada reincidência técnica para esta O.S.";
}

function operationalReason(order: AuditableOrder) {
  if (order.recurrence_discount_applied) return recurrencePlainReason(order);
  if (order.scoring_status === "Anulada por SLA") {
    return `Esta O.S foi anulada porque o SLA da planilha foi classificado como ${safeText(order.sla_status_normalized)}.`;
  }
  if (order.scoring_status === "Anulada por diagnóstico") {
    return `Esta O.S foi anulada porque o diagnóstico "${safeText(order.diagnosis)}" possui regra de anulação.`;
  }
  if (order.is_unscored || !order.group_name) {
    return `Esta O.S ficou sem pontuar porque o assunto "${safeText(order.os_subject)}" ainda não está vinculado a um grupo de pontuação ativo.`;
  }
  if (order.requires_manual_review) {
    return "Esta O.S precisa de revisão manual antes da aprovação da apuração.";
  }
  if (order.is_penalized) {
    return `Esta O.S pontuou, mas teve ${formatAnnulledPoints(order.penalty_points)} por regra operacional.`;
  }
  return `Esta O.S pontuou porque o assunto "${safeText(order.os_subject)}" está vinculado ao grupo "${safeText(order.group_name)}".`;
}

function appliedRuleText(order: AuditableOrder) {
  if (order.recurrence_discount_applied) return order.recurrence_rule_name || "Reincidência confirmada";
  if (order.recurrence_classification) return order.recurrence_rule_name || "Nenhuma regra de reincidência aplicada";
  if (order.scoring_status === "Anulada por SLA") return order.sla_penalty_type ? `SLA: ${slaPenaltyLabel(order.sla_penalty_type)}` : "SLA fora do prazo";
  if (order.scoring_status === "Anulada por diagnóstico") return order.diagnosis_rule_applied || "Diagnóstico com anulação";
  return order.rule_applied ?? order.scoring_rule_name ?? "Não identificada";
}

function DetailItem({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="min-w-0 rounded-md border bg-slate-50 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-950">{safeText(value)}</div>
    </div>
  );
}

function RuleDecisionCard({
  title,
  status,
  detail,
  tone = "slate"
}: {
  title: string;
  status: string;
  detail: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">{title}</div>
        <Badge className={toneBadgeClass(tone)}>{status}</Badge>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-700">{detail}</p>
    </div>
  );
}

function EvidenceList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-lg border bg-white">
      <div className="border-b px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</div>
      <div className="max-h-72 overflow-y-auto overflow-x-auto px-4 py-3">
        {items.length ? (
          <ul className="grid gap-2 text-sm text-slate-700">
            {items.map((item, index) => (
              <li key={`${item}-${index}`} className="rounded-md bg-slate-50 px-3 py-2">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">Sem evidência registrada para este bloco.</p>
        )}
      </div>
    </section>
  );
}

function RecurrenceOrderCard({
  title,
  order
}: {
  title: string;
  order: (CollaboratorOrderDetail & { collaborator_name?: string }) | null | undefined;
}) {
  if (!order) {
    return (
      <div className="rounded-lg border border-dashed bg-slate-50 p-4 text-sm text-slate-500">
        {title}: não identificado na base.
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-2 text-base font-semibold text-slate-950">O.S {order.os_code}</div>
      <div className="mt-3 grid gap-2 text-sm text-slate-700">
        <div>Colaborador: {safeText(order.collaborator_name)}</div>
        <div>Cliente: {safeText(order.customer_name)}</div>
        <div>Regional: {regionalName(order.regional)}</div>
        <div>Assunto: {safeText(order.os_subject)}</div>
        <div>Diagnóstico: {safeText(order.diagnosis)}</div>
        <div>Abertura: {formatDateTime(order.opened_at)}</div>
      </div>
    </div>
  );
}

function DecisionPill({ discountApplied }: { discountApplied: boolean }) {
  return (
    <Badge className={discountApplied ? "w-fit border-red-200 bg-red-50 text-red-700" : "w-fit border-emerald-200 bg-emerald-50 text-emerald-700"}>
      {discountApplied ? "Anula ponto" : "Não anula ponto"}
    </Badge>
  );
}

function TimelineOrderCard({
  item,
  currentOrderId
}: {
  item: CollaboratorOrderDetail & { collaborator_name?: string };
  currentOrderId: number;
}) {
  const isCurrent = item.id === currentOrderId;
  return (
    <article className={isCurrent ? "rounded-lg border border-blue-300 bg-blue-50 p-3" : "rounded-lg border bg-white p-3"}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{formatDateTime(item.opened_at)}</div>
          <div className="mt-1 text-sm font-semibold text-slate-950">
            O.S {item.os_code} {isCurrent ? "(selecionada)" : ""}
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-1">
          <Badge className="border-slate-200 bg-slate-50 text-slate-700">
            {item.recurrence_rule_name || recurrenceClassificationLabel(item.recurrence_classification)}
          </Badge>
          {item.recurrence_discount_applied ? <DecisionPill discountApplied /> : null}
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
        <div>
          <span className="font-medium text-slate-950">Assunto:</span> {safeText(item.os_subject)}
        </div>
        <div>
          <span className="font-medium text-slate-950">Diagnóstico:</span> {safeText(item.diagnosis)}
        </div>
        <div>
          <span className="font-medium text-slate-950">Colaborador:</span> {safeText(item.collaborator_name)}
        </div>
        <div>
          <span className="font-medium text-slate-950">Resultado:</span> {formatPoints(item.net_points)} / {formatAnnulledPoints(item.penalty_points)}
        </div>
      </div>
    </article>
  );
}

function RecurrenceAuditPanel({ audit }: { audit: RecurrenceAudit }) {
  const hasIdentity = audit.identity_value !== "Login/ID contrato não importado";
  const analyzedLabel = audit.identity_type === "Identidade" ? "Referência analisada" : `${audit.identity_type} analisado`;
  return (
    <section className="rounded-xl border bg-white">
      <div className="border-b px-4 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Análise de reincidência</div>
        <div className="mt-1 text-sm text-slate-600">
          {analyzedLabel}: <span className="font-semibold text-slate-950">{audit.identity_value}</span> - {formatInteger(audit.related_orders.length)} O.S na linha do tempo.
        </div>
      </div>

      <div className="grid gap-4 p-4">
        <div className={audit.discount_applied ? "rounded-lg border border-red-200 bg-red-50 p-4" : "rounded-lg border border-emerald-200 bg-emerald-50 p-4"}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Resultado da auditoria</div>
              <div className="mt-1 text-lg font-semibold text-slate-950">{recurrenceClassificationLabel(audit.classification)}</div>
              <p className="mt-1 text-sm text-slate-700">
                {hasIdentity
                  ? audit.discount_applied
                    ? `A O.S origem ${audit.discount_target_os_code} teve ${formatPoints(audit.discount_points)} anulados.`
                    : "Não houve anulação porque a evidência não confirmou reincidência técnica."
                  : "A planilha não trouxe login nem ID contrato válido para análise. A auditoria não utiliza nome de plano nem nome do cliente para classificar reincidência."}
              </p>
            </div>
            <DecisionPill discountApplied={audit.discount_applied} />
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-4">
          <DetailItem label={audit.identity_type} value={audit.identity_value} />
          <DetailItem label="O.S analisadas" value={formatInteger(audit.related_orders.length)} />
          <DetailItem label="O.S anulada" value={audit.discount_target_os_code ?? "Nenhuma"} />
          <DetailItem label="Pontos anulados" value={formatAnnulledPoints(audit.discount_points)} />
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <RecurrenceOrderCard title="O.S origem" order={audit.origin_order} />
          <RecurrenceOrderCard title="O.S posterior" order={audit.posterior_order} />
        </div>

        <div className="grid gap-2 rounded-lg border bg-slate-50 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Histórico da O.S</div>
          {audit.related_orders.map((item) => (
            <TimelineOrderCard key={item.id} item={item} currentOrderId={audit.current_order.id} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function OrderAuditSheet({ order: initialOrder, open, onOpenChange, calculationRunId }: OrderAuditSheetProps) {
  const [detailedOrder, setDetailedOrder] = useState<AuditableOrder | null>(null);
  const [recurrenceAudit, setRecurrenceAudit] = useState<RecurrenceAudit | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !initialOrder) return;

    let cancelled = false;
    setDetailedOrder(initialOrder);
    setRecurrenceAudit(null);
    setAuditLoading(true);
    setAuditError(null);
    Promise.all([
      api.auditOrderDetail(initialOrder.id, calculationRunId),
      api.recurrenceAudit(initialOrder.id)
    ])
      .then(([detailPayload, recurrencePayload]) => {
        if (cancelled) return;
        setDetailedOrder(detailPayload);
        setRecurrenceAudit(recurrencePayload);
      })
      .catch((error: Error) => {
        if (!cancelled) setAuditError(error.message);
      })
      .finally(() => {
        if (!cancelled) setAuditLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [calculationRunId, initialOrder, open]);

  if (!initialOrder) return null;
  const order = detailedOrder ?? initialOrder;

  const hasGroup = Boolean(order.group_name);
  const hasDiagnosisRule = Boolean(order.diagnosis_rule_id);
  const hasDiagnosisPenalty = order.diagnosis_penalty_points > 0;
  const diagnosisSuppressed = hasDiagnosisRule && wasSuppressed(order.diagnosis_penalty_reason);
  const hasSlaPenalty = order.sla_penalty_points > 0;
  const hasSlaRule = Boolean(order.sla_rule_id);
  const slaSuppressed = hasSlaRule && wasSuppressed(order.sla_penalty_reason);
  // Etiqueta única de retorno: nome da regra configurada > rótulo genérico > flags legadas.
  const recurrenceDisplay = resolveRecurrenceDisplay(order);
  const recurrenceClassification = recurrenceDisplay?.label ?? "Sem reincidência técnica aplicada";
  const statusEntry = scoringStatusEntry(order.scoring_status);
  const diagnosisAuditText = hasDiagnosisRule
    ? diagnosisSuppressed
      ? order.diagnosis_penalty_reason ||
        `Diagnóstico possui regra configurada para ${diagnosisActionLabel(order.diagnosis_action_type)}, porém não foi aplicado por prioridade.`
      : order.diagnosis_penalty_reason ||
        `Diagnóstico possui regra configurada para ${diagnosisActionLabel(order.diagnosis_action_type)}.`
    : "Diagnóstico sem regra de anulação configurada.";
  const slaAuditText = hasSlaRule
    ? slaSuppressed
      ? order.sla_penalty_reason || "SLA possui regra configurada, porém não foi aplicado por prioridade."
      : order.sla_penalty_reason || `SLA possui regra configurada para ${slaPenaltyLabel(order.sla_penalty_type)}.`
    : hasSlaPenalty
      ? `O SLA anulou ${formatAnnulledPoints(order.sla_penalty_points)}.`
      : "SLA no prazo ou sem regra de anulação aplicada.";
  const outcome = auditOutcomeLabel(order);
  const mainReason = operationalReason(order);
  const appliedRule = appliedRuleText(order);
  // Uma única lista de evidências (critérios + anulações + reincidência), sem repetição - antes o
  // mesmo motivo aparecia em até 4 seções diferentes do drawer.
  const allEvidence = Array.from(
    new Set(
      [...(order.reasons ?? []), ...(order.penalty_reasons ?? []), ...(order.recurrence_evidence ?? [])].map(cleanOperationalText)
    )
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="inset-y-2 right-2 h-[calc(100vh-1rem)] max-h-[calc(100vh-1rem)] w-[96vw] min-w-0 max-w-[calc(100vw-1rem)] overflow-hidden rounded-lg border sm:w-[min(920px,92vw)] sm:min-w-[560px] sm:max-w-[920px]">
          <SheetHeader className="shrink-0">
            <SheetTitle className="pr-6">Auditoria operacional da O.S {order.os_code}</SheetTitle>
            <SheetDescription>
              Resultado da regra aplicada, dados da planilha e motivo operacional da pontuação.
            </SheetDescription>
          </SheetHeader>

          <div className="min-h-0 flex-1 overflow-y-auto overflow-x-auto px-4 py-4 sm:px-6">
            <div className="grid min-w-0 max-w-full gap-4 [overflow-wrap:anywhere] [word-break:break-word]">
              <section className={`rounded-xl border p-4 ${auditTone(order)}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[10px] font-bold uppercase tracking-[0.14em] opacity-80">Resumo da decisão</div>
                    <div className="mt-1 text-xl font-semibold text-slate-950">{outcome}</div>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-700">{mainReason}</p>
                    <p className="mt-1 text-sm text-slate-700">
                      <span className="font-semibold text-slate-950">Regra aplicada:</span> {appliedRule}.{" "}
                      <span className="font-semibold text-slate-950">Resultado final:</span> {formatPoints(order.net_points)}.
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <StatusBadge tone={statusEntry.tone} icon={statusEntry.icon}>
                      {statusEntry.label}
                    </StatusBadge>
                    {recurrenceDisplay ? (
                      <SecondaryPill tone={recurrenceDisplay.tone} icon={Repeat}>
                        {recurrenceDisplay.label}
                      </SecondaryPill>
                    ) : null}
                  </div>
                </div>
              </section>

              <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Identificação</div>
                <div className="mt-3 grid gap-3 sm:grid-cols-3">
                  <Info label="ID da O.S" value={order.os_code} />
                  <Info label="Cliente" value={order.customer_name} />
                  <Info label="Contrato / login" value={[order.contract_id, order.customer_login].filter(Boolean).join(" / ") || null} />
                  <Info label="Colaborador" value={order.collaborator_name} />
                  <Info label="Regional" value={regionalName(order.regional)} />
                  <Info label="Tipo geral" value={order.os_type} />
                  <Info label="Assunto" value={order.os_subject} />
                  <Info label="Diagnóstico" value={order.diagnosis} />
                  <Info label="Grupo de pontuação" value={order.group_name ?? "Sem regra"} />
                  <Info label="SLA original" value={order.sla_status} />
                  <Info label="SLA normalizado" value={order.sla_status_normalized} />
                  <Info label="TMF/TMA" value={formatHours(order.closing_time_hours)} />
                  <Info label="Abertura" value={formatDateTime(order.opened_at)} />
                  <Info label="Fechamento" value={formatDateTime(order.closed_at)} />
                  <Info label="Origem do valor do ponto" value={order.point_value_source} />
                  <Info label="Regra de reincidência" value={order.recurrence_rule_name} />
                  <Info label="Revisão manual" value={yesNo(order.requires_manual_review)} />
                  <Info
                    label="Pontuação base"
                    value={hasGroup ? `${formatPoints(order.base_points)} · ${formatMoney(order.point_value)}/ponto` : null}
                  />
                </div>
              </section>

              <section className="rounded-lg border bg-white p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Critérios avaliados</div>
                <p className="mt-2 text-sm text-slate-600">
                  Quando uma reincidência anula a pontuação, os demais critérios ficam registrados para conferência, mas não anulam a mesma O.S novamente.
                </p>
                <div className="mt-4 grid gap-3 lg:grid-cols-3">
                  <RuleDecisionCard
                    title="Reincidências"
                    status={order.recurrence_discount_applied ? "Aplicada" : order.recurrence_classification ? "Classificada sem anulação" : "Não encontrada"}
                    tone={order.recurrence_discount_applied ? "red" : order.recurrence_classification ? "blue" : "slate"}
                    detail={
                      order.recurrence_classification
                        ? `${recurrenceClassification}${order.recurrence_related_os_code ? ` relacionada a O.S ${order.recurrence_related_os_code}` : ""}. ${
                            order.recurrence_discount_applied ? `Ponto anulado: ${formatAnnulledPoints(order.recurrence_penalty_points)}.` : "Sem anulação aplicada."
                          }`
                        : "Não houve evidência de reincidência técnica para esta O.S."
                    }
                  />
                  <RuleDecisionCard
                    title="Diagnóstico"
                    status={hasDiagnosisRule ? (diagnosisSuppressed ? "Encontrada, não aplicada" : hasDiagnosisPenalty ? "Aplicada" : "Encontrada") : "Não configurada"}
                    tone={diagnosisSuppressed ? "amber" : hasDiagnosisPenalty ? "red" : hasDiagnosisRule ? "blue" : "slate"}
                    detail={
                      hasDiagnosisRule
                        ? cleanOperationalText(`Regra: ${safeText(order.diagnosis_rule_applied)}. Ação: ${diagnosisActionLabel(order.diagnosis_action_type)}. ${diagnosisAuditText}`)
                        : "Não existe regra ativa cadastrada para este diagnóstico."
                    }
                  />
                  <RuleDecisionCard
                    title="SLA"
                    status={hasSlaRule ? (slaSuppressed ? "Encontrada, não aplicada" : hasSlaPenalty ? "Aplicada" : "Encontrada") : "Sem anulação"}
                    tone={slaSuppressed ? "amber" : hasSlaPenalty ? "red" : hasSlaRule ? "blue" : "slate"}
                    detail={cleanOperationalText(hasSlaRule ? `Regra: ${slaPenaltyLabel(order.sla_penalty_type)}. ${slaAuditText}` : slaAuditText)}
                  />
                </div>
              </section>

              <section className="grid gap-2 sm:grid-cols-3">
                <SummaryMetric icon={Sigma} label="Pontos base" value={formatPoints(order.base_points)} tone="slate" />
                <SummaryMetric
                  icon={Minus}
                  label="Pontos anulados"
                  value={formatAnnulledPoints(order.penalty_points)}
                  tone={order.penalty_points > 0 ? "red" : "emerald"}
                />
                <SummaryMetric icon={Sigma} label="Pontos finais" value={formatPoints(order.net_points)} tone="blue" />
              </section>

              <EvidenceList title="Evidências e critérios registrados" items={allEvidence} />

              {auditLoading ? (
                <div className="rounded-lg border bg-slate-50 p-4 text-sm text-slate-600">Carregando auditoria de reincidência...</div>
              ) : null}
              {auditError ? <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{auditError}</div> : null}
              {recurrenceAudit ? (
                <Collapsible className="rounded-xl border bg-white">
                  <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left">
                    <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      Análise detalhada de reincidência
                    </span>
                    <ChevronDown className="h-4 w-4 text-slate-400" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t p-2">
                    <RecurrenceAuditPanel audit={recurrenceAudit} />
                  </CollapsibleContent>
                </Collapsible>
              ) : null}
            </div>
          </div>
        </SheetContent>
    </Sheet>
  );
}

export function OrderAuditDrawer({ order, label = "Auditar" }: OrderAuditDrawerProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button type="button" variant="ghost" size="sm" className="h-8" onClick={() => setOpen(true)}>
        <FileSearch className="h-4 w-4" />
        {label}
      </Button>
      <OrderAuditSheet order={order} open={open} onOpenChange={setOpen} />
    </>
  );
}




