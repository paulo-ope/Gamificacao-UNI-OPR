"use client";

import { Download, FileSearch, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { OrderAuditSheet } from "@/components/gamification/order-audit-drawer";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatAnnulledPoints, formatDateTime, formatHours, formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { regionalName } from "@/lib/regional";
import type { CollaboratorOrderDetail, CollaboratorOrdersDetail, CollaboratorScore } from "@/lib/types";

type FilterMode = "all" | "scored" | "unscored" | "penalized" | "sla_out" | "recurrence" | "non_recurrent" | "diagnosis_blocked";

type CollaboratorOrdersSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  score: CollaboratorScore | null;
  calculationRunId?: number;
  groups?: { id: number; name: string; active?: boolean }[];
  rankingPosition?: number | null;
};

function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("anulada")) return "border-red-200 bg-red-50 text-red-700";
  if (normalized.includes("penal")) return "border-red-200 bg-red-50 text-red-700";
  if (normalized.includes("sem regra")) return "border-amber-200 bg-amber-50 text-amber-800";
  if (normalized.includes("garantia") || normalized.includes("reincid")) return "border-blue-200 bg-blue-50 text-blue-700";
  if (normalized.includes("revisão")) return "border-violet-200 bg-violet-50 text-violet-700";
  if (normalized.includes("pontuada")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function recurrenceClassificationLabel(value: string | null | undefined) {
  if (value === "reincidencia_tecnica") return "Reincidência de manutenção";
  if (value === "garantia") return "Reincidência após ativação";
  if (value === "possivel_retorno_sem_regra") return "Retorno dentro da janela sem regra ativa";
  if (value === "os_nao_reincidente") return "O.S não reincidente";
  if (value === "nao_identificado") return "Não identificado";
  if (value === "demandas_diferentes") return "Demandas diferentes";
  if (value === "recorrencia_operacional") return "Recorrência operacional";
  return "Sem classificação";
}

function compactStatusNotes(order: CollaboratorOrderDetail) {
  const notes = [
    order.recurrence_classification ? recurrenceClassificationLabel(order.recurrence_classification) : null,
    order.has_pending ? "Pendência" : null,
    order.has_reschedule ? "Reagendamento" : null,
    order.requires_manual_review ? "Revisão" : null
  ].filter(Boolean);
  return notes.join(" • ");
}

function formatPeriod(month: number | null | undefined, year: number | null | undefined) {
  if (!month || !year) return "Não informado";
  return `${String(month).padStart(2, "0")}/${year}`;
}

function csvEscape(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function uniqueSorted(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort((a, b) =>
    a.localeCompare(b, "pt-BR")
  );
}

export function CollaboratorOrdersSheet({
  open,
  onOpenChange,
  score,
  calculationRunId,
  groups = [],
  rankingPosition = null
}: CollaboratorOrdersSheetProps) {
  const [detail, setDetail] = useState<CollaboratorOrdersDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<FilterMode>("all");
  const [osType, setOsType] = useState("");
  const [osSubject, setOsSubject] = useState("");
  const [statusSla, setStatusSla] = useState("");
  const [groupId, setGroupId] = useState("");
  const [filterOptionsDetail, setFilterOptionsDetail] = useState<CollaboratorOrdersDetail | null>(null);
  const [selectedAuditOrder, setSelectedAuditOrder] = useState<(CollaboratorOrderDetail & { collaborator_name?: string }) | null>(null);
  const activeGroups = useMemo(() => groups.filter((group) => group.active !== false), [groups]);

  const filters = useMemo(
    () => ({
      calculation_run_id: calculationRunId,
      only_scored: mode === "scored" || undefined,
      only_unscored: mode === "unscored" || undefined,
      only_penalized: mode === "penalized" || undefined,
      only_sla_out: mode === "sla_out" || undefined,
      only_recurrence: mode === "recurrence" || undefined,
      only_non_recurrent: mode === "non_recurrent" || undefined,
      only_diagnosis_blocked: mode === "diagnosis_blocked" || undefined,
      group_id: groupId ? Number(groupId) : undefined,
      os_type: osType || undefined,
      os_subject: osSubject || undefined,
      status_sla: statusSla || undefined
    }),
    [calculationRunId, groupId, mode, osSubject, osType, statusSla]
  );

  useEffect(() => {
    if (!open || !score) return;

    setLoading(true);
    setError(null);
    api
      .collaboratorOrdersDetail(score.collaborator_id, filters)
      .then(setDetail)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters, open, score?.collaborator_id]);

  useEffect(() => {
    if (!open || !score) {
      setFilterOptionsDetail(null);
      return;
    }

    let cancelled = false;
    api
      .collaboratorOrdersDetail(score.collaborator_id, { calculation_run_id: calculationRunId })
      .then((payload) => {
        if (!cancelled) setFilterOptionsDetail(payload);
      })
      .catch(() => {
        if (!cancelled) setFilterOptionsDetail(null);
      });

    return () => {
      cancelled = true;
    };
  }, [calculationRunId, open, score?.collaborator_id]);

  const filterSourceOrders = filterOptionsDetail?.orders ?? detail?.orders ?? [];
  const osTypeOptions = useMemo(() => uniqueSorted(filterSourceOrders.map((order) => order.os_type)), [filterSourceOrders]);
  const osSubjectOptions = useMemo(
    () => uniqueSorted(filterSourceOrders.filter((order) => !osType || order.os_type === osType).map((order) => order.os_subject)),
    [filterSourceOrders, osType]
  );
  const slaOptions = useMemo(() => uniqueSorted(filterSourceOrders.map((order) => order.sla_status)), [filterSourceOrders]);
  const recurrenceCounts = useMemo(() => {
    const counts = new Map<string, number>();
    (detail?.orders ?? []).forEach((order) => {
      if (!order.recurrence_classification && !order.is_recurrence && !order.is_warranty) return;
      const label = recurrenceClassificationLabel(order.recurrence_classification);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    });
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [detail]);

  const cards = detail
    ? [
        ["Total de O.S", `${formatInteger(detail.summary.total_service_orders)} O.S`],
        ["O.S pontuadas", `${formatInteger(detail.summary.scored_service_orders)} O.S`],
        ["O.S anuladas", `${formatInteger(detail.summary.annulled_service_orders)} O.S`],
        ["Fora prazo", `${formatInteger(detail.summary.sla_out_service_orders)} O.S`],
        ["Reincidências", `${formatInteger(detail.summary.recurrence_service_orders ?? detail.summary.warranty_service_orders)} O.S`],
        ["Pontos brutos", formatPoints(detail.summary.gross_points)],
        ["Pontos anulados", formatAnnulledPoints(detail.summary.penalty_points)],
        ["Pontos finais", formatPoints(detail.summary.final_points)],
        ["Valor a ser pago", formatMoney(detail.summary.estimated_payment)]
      ]
    : [];
  const tabs: Array<[FilterMode, string]> = [
    ["all", "Resumo"],
    ["scored", "O.S pontuadas"],
    ["penalized", "O.S anuladas"],
    ["recurrence", "Reincidências"],
    ["sla_out", "Fora prazo"],
    ["unscored", "Sem regra"]
  ];

  function exportCsv() {
    if (!detail) return;

    const headers = [
      "ID O.S",
      "Cliente",
      "Login",
      "Plano/Contrato",
      "Regional",
      "Tipo Geral",
      "Assunto",
      "Diagnóstico",
      "Grupo",
      "Regra aplicada",
      "Origem",
      "SLA original",
      "SLA normalizado",
      "TMF/TMA",
      "Pontos base",
      "Ponto anulado por diagnóstico",
      "Ponto anulado por SLA",
      "Ponto anulado final",
      "Pontos líquidos",
      "Status",
      "Auditoria"
    ];
    const rows = detail.orders.map((order) => [
      order.os_code,
      order.customer_name,
      order.customer_login ?? "",
      order.contract_id,
      regionalName(order.regional),
      order.os_type,
      order.os_subject,
      order.diagnosis,
      order.group_name ?? "Sem regra",
      order.os_subject,
      order.rule_applied ?? "",
      order.sla_status,
      order.sla_status_normalized,
      formatHours(order.closing_time_hours),
      order.base_points,
      order.diagnosis_penalty_points,
      order.sla_penalty_points,
      order.additional_penalty_points,
      order.net_points,
      order.scoring_status,
      order.reasons.join(" | ")
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n");
    const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `extrato-${detail.collaborator.name.replace(/\s+/g, "-").toLowerCase()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[min(1500px,96vw)]">
        <SheetHeader>
          <SheetTitle>Extrato operacional - {score?.collaborator_name ?? "Colaborador"}</SheetTitle>
          <SheetDescription>
            {detail
              ? `${regionalName(detail.collaborator.regional)} · ${detail.period.reference_month}/${detail.period.reference_year}`
              : regionalName(score?.regional)}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-6 py-5">
          {error ? (
            <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          ) : null}

          {loading ? (
            <div className="mb-4 flex items-center gap-2 rounded-md border bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Carregando extrato operacional...
            </div>
          ) : null}

          {detail ? (
            <div className="grid gap-5">
              <section className="rounded-lg border bg-white p-5">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Extrato executivo</div>
                    <h2 className="mt-1 text-2xl font-semibold text-slate-950">{detail.collaborator.name}</h2>
                    <div className="mt-2 grid gap-1 text-sm text-slate-600 sm:grid-cols-2 xl:grid-cols-4">
                      <div>Regional: <span className="font-medium text-slate-950">{regionalName(detail.collaborator.regional)}</span></div>
                      <div>Cargo/função: <span className="font-medium text-slate-950">{detail.collaborator.role || score?.role || "Não informado"}</span></div>
                      <div>Período: <span className="font-medium text-slate-950">{formatPeriod(detail.period.reference_month, detail.period.reference_year)}</span></div>
                      <div>Ranking: <span className="font-medium text-slate-950">{rankingPosition ? `${rankingPosition}º lugar` : "Não informado"}</span></div>
                    </div>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {tabs.map(([value, label]) => (
                    <Button key={value} size="sm" variant={mode === value ? "default" : "outline"} onClick={() => setMode(value)}>
                      {label}
                    </Button>
                  ))}
                </div>
              </section>

              <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
                {cards.map(([label, value]) => (
                  <div key={label} className="rounded-md border bg-white p-4">
                    <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
                    <div className="mt-2 text-xl font-semibold text-slate-950">{value}</div>
                  </div>
                ))}
              </section>

              <section className="rounded-md border bg-white">
                <div className="grid gap-3 border-b p-4 xl:grid-cols-[1fr_1fr_1fr_1fr_auto] xl:items-end">
                  <div className="grid gap-1">
                    <Label>Tipo Geral</Label>
                    <select
                      className="h-9 min-w-0 rounded-md border border-input bg-white px-3 text-sm"
                      value={osType}
                      onChange={(event) => {
                        setOsType(event.target.value);
                        setOsSubject("");
                      }}
                    >
                      <option value="">Todos os tipos</option>
                      {osTypeOptions.map((type) => (
                        <option key={type} value={type}>
                          {type}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid gap-1">
                    <Label>Assunto</Label>
                    <select
                      className="h-9 min-w-0 rounded-md border border-input bg-white px-3 text-sm"
                      value={osSubject}
                      onChange={(event) => setOsSubject(event.target.value)}
                    >
                      <option value="">Todos os assuntos</option>
                      {osSubjectOptions.map((subject) => (
                        <option key={subject} value={subject}>
                          {subject}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid gap-1">
                    <Label>SLA</Label>
                    <select
                      className="h-9 min-w-0 rounded-md border border-input bg-white px-3 text-sm"
                      value={statusSla}
                      onChange={(event) => setStatusSla(event.target.value)}
                    >
                      <option value="">Todos os SLAs</option>
                      {slaOptions.map((sla) => (
                        <option key={sla} value={sla}>
                          {sla}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid gap-1">
                    <Label>Grupo</Label>
                    <select
                      className="h-9 rounded-md border border-input bg-white px-3 text-sm"
                      value={groupId}
                      onChange={(event) => setGroupId(event.target.value)}
                    >
                      <option value="">Todos</option>
                      {activeGroups.map((group) => (
                        <option key={group.id} value={group.id}>
                          {group.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button variant="outline" onClick={exportCsv}>
                    <Download className="h-4 w-4" />
                    Exportar
                  </Button>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm text-slate-600">
                  <span>
                    {formatInteger(detail.orders.length)} O.S exibida(s) em "{tabs.find(([value]) => value === mode)?.[1] ?? "filtro atual"}".
                  </span>
                  <span>Detalhes completos ficam no botão Auditar.</span>
                </div>
              </section>

              {(mode === "recurrence" || mode === "non_recurrent") && recurrenceCounts.length ? (
                <section className="flex flex-wrap gap-2 rounded-md border border-blue-100 bg-blue-50 p-3 text-xs">
                  {recurrenceCounts.map(([label, count]) => (
                    <span key={label} className="rounded-full border border-blue-200 bg-white px-3 py-1 font-medium text-slate-700">
                      {label}: {formatInteger(count)}
                    </span>
                  ))}
                </section>
              ) : null}

              <section className="overflow-hidden rounded-md border bg-white">
                  <Table className="table-fixed text-xs md:text-sm">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[88px]">ID da O.S</TableHead>
                        <TableHead className="w-[120px]">Data</TableHead>
                        <TableHead className="w-[16%]">Cliente</TableHead>
                        <TableHead className="w-[22%]">Assunto</TableHead>
                        <TableHead className="w-[18%]">Diagnóstico</TableHead>
                        <TableHead className="w-[14%]">SLA</TableHead>
                        <TableHead className="w-[12%]">Pontos</TableHead>
                        <TableHead className="w-[12%]">Status</TableHead>
                        <TableHead className="w-[88px]">Auditar</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.orders.map((order) => (
                        <TableRow key={order.id}>
                          <TableCell className="font-medium whitespace-nowrap">{order.os_code}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-slate-600 md:text-sm">{formatDateTime(order.closed_at ?? order.opened_at)}</TableCell>
                          <TableCell className="max-w-0">
                            <div className="break-words text-slate-800">{order.customer_name}</div>
                          </TableCell>
                          <TableCell className="max-w-0">
                            <div className="break-words font-medium text-slate-950">{order.os_subject}</div>
                            <div className="mt-1 break-words text-[11px] text-slate-500">{order.os_type}</div>
                          </TableCell>
                          <TableCell className="max-w-0">
                            <div className="break-words text-slate-800">{order.diagnosis}</div>
                          </TableCell>
                          <TableCell className="max-w-0">
                            <div className="break-words text-slate-800">{order.sla_status}</div>
                            <div className="mt-1 break-words text-[11px] text-slate-500">{order.sla_status_normalized}</div>
                          </TableCell>
                          <TableCell className="max-w-0">
                            <div className="font-medium text-slate-950">{formatPoints(order.net_points)}</div>
                            {order.penalty_points > 0 ? (
                              <div className="mt-1 break-words text-[11px] font-medium text-red-600">{formatAnnulledPoints(order.penalty_points)}</div>
                            ) : null}
                          </TableCell>
                          <TableCell className="max-w-0">
                            <div className="flex flex-col gap-1">
                              <Badge className={`${statusBadgeClass(order.scoring_status)} max-w-full justify-center whitespace-normal text-center`}>{order.scoring_status}</Badge>
                              {compactStatusNotes(order) ? (
                                <div className="break-words text-[11px] text-slate-500">{compactStatusNotes(order)}</div>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell className="whitespace-nowrap">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2"
                              onClick={() => setSelectedAuditOrder({ ...order, collaborator_name: detail.collaborator.name })}
                            >
                              <FileSearch className="h-4 w-4" />
                              <span className="hidden lg:inline">Auditar</span>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
              </section>

              <div className="text-xs text-slate-500">
                O extrato considera o período analisado {formatPeriod(detail.period.reference_month, detail.period.reference_year)}. Datas completas ficam disponíveis no botão Auditar.
              </div>
            </div>
          ) : null}
        </ScrollArea>
        <OrderAuditSheet
          order={selectedAuditOrder}
          open={Boolean(selectedAuditOrder)}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setSelectedAuditOrder(null);
          }}
        />
      </SheetContent>
    </Sheet>
  );
}




