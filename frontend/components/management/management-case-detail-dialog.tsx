"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  MessageSquare,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ManagementCase, ManagementCaseComment, ManagementCaseReason } from "@/lib/types";
import {
  CASE_STATUS_LABELS,
  CASE_TYPE_LABELS,
  SEVERITY_LABELS,
  decimal,
  formatDate,
  formatDateTime,
  severityTone,
  statusTone,
} from "./case-format-helpers";

export function CaseDetailDialog({
  caseId,
  reasons,
  canReview,
  canJustify,
  onClose,
  onChanged,
}: {
  caseId: number;
  reasons: ManagementCaseReason[];
  canReview: boolean;
  canJustify: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [item, setItem] = useState<ManagementCase | null>(null);
  const [comments, setComments] = useState<ManagementCaseComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasonId, setReasonId] = useState<string>("");
  const [justification, setJustification] = useState("");
  const [actionPlan, setActionPlan] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [newComment, setNewComment] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextCase, nextComments] = await Promise.all([api.managementCase(caseId), api.managementCaseComments(caseId)]);
      setItem(nextCase);
      setComments(nextComments);
      setReasonId(nextCase.reason_id ? String(nextCase.reason_id) : "");
      setJustification(nextCase.justification_text ?? "");
      setActionPlan(nextCase.action_plan ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar o caso.");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const isClosed = item ? ["resolved", "rejected"].includes(item.status) : false;
  const selectedReason = reasons.find((reason) => String(reason.id) === reasonId);
  const needsLongText = Boolean(selectedReason?.requires_description);

  async function submitJustification() {
    if (!item) return;
    setSaving(true);
    setError(null);
    try {
      await api.justifyManagementCase(item.id, {
        reason_id: reasonId ? Number(reasonId) : null,
        justification_text: justification.trim(),
        action_plan: actionPlan.trim() || null,
      });
      await refresh();
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao enviar a justificativa.");
    } finally {
      setSaving(false);
    }
  }

  async function submitReview(status: string) {
    if (!item) return;
    setSaving(true);
    setError(null);
    try {
      await api.reviewManagementCase(item.id, { status, review_note: reviewNote.trim() || null });
      setReviewNote("");
      await refresh();
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao registrar a decisão.");
    } finally {
      setSaving(false);
    }
  }

  async function submitComment() {
    if (!item || !newComment.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.createManagementCaseComment(item.id, newComment.trim());
      setNewComment("");
      await refresh();
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao comentar.");
    } finally {
      setSaving(false);
    }
  }

  // Via portal direto em document.body: sem isso, este dialog fica preso na posicao normal do
  // DOM (dentro da arvore de quem o abriu) enquanto outros overlays baseados em Radix (Sheet,
  // Dialog) sao portados para o FIM do body pelo proprio Radix - quando os dois aparecem juntos
  // (ex.: aberto de dentro do drill do calendario, que usa Sheet), o portal do Radix, montado
  // depois, pintava por cima deste dialog mesmo com z-index igual, deixando o formulario de
  // justificativa visualmente atras e impossivel de clicar (achado real, 2026-08-13).
  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-600">Caso de gestão #{caseId}</p>
            <h3 className="mt-1 text-lg font-semibold text-slate-950">{item?.responsible_name ?? "Carregando..."}</h3>
            {item ? (
              <p className="mt-0.5 text-sm text-slate-500">
                {CASE_TYPE_LABELS[item.case_type] ?? item.case_type} · {item.regional ?? "sem regional"}
                {item.case_type === "daily_performance_below_target" && item.reference_date
                  ? ` · ${formatDate(item.reference_date)}`
                  : item.reference_month
                    ? ` · ${String(item.reference_month).padStart(2, "0")}/${item.reference_year}`
                    : ""}
              </p>
            ) : null}
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          {loading || !item ? (
            <div className="h-56 animate-pulse rounded-xl bg-slate-100" />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-4">
                {(
                  [
                    ["Realizado", decimal(item.actual_value)],
                    ["Esperado", decimal(item.expected_value)],
                    ["Desvio", item.deviation_value !== null ? `-${decimal(item.deviation_value)}%` : "—"],
                    ["Prazo", formatDate(item.due_date)],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-[11px] font-medium text-slate-500">{label}</p>
                    <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{value}</p>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={statusTone(item.status)}>{CASE_STATUS_LABELS[item.status] ?? item.status}</Badge>
                <Badge className={severityTone(item.severity)}>Severidade {SEVERITY_LABELS[item.severity] ?? item.severity}</Badge>
                {item.is_overdue ? (
                  <Badge className="border-red-200 bg-red-50 text-red-700">
                    <AlertTriangle className="mr-1 h-3.5 w-3.5" /> Em atraso
                  </Badge>
                ) : null}
                <span className="text-xs text-slate-400">{item.metric_name}</span>
              </div>

              {item.justification_text ? (
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Justificativa do supervisor</p>
                  {item.reason_name ? (
                    <Badge className="mt-2 border-blue-200 bg-blue-50 text-blue-700">{item.reason_name}</Badge>
                  ) : null}
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{item.justification_text}</p>
                  {item.action_plan ? (
                    <>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Plano de ação</p>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{item.action_plan}</p>
                    </>
                  ) : null}
                  <p className="mt-3 text-xs text-slate-400">Enviada em {formatDateTime(item.justified_at)}</p>
                </div>
              ) : null}

              {canJustify && !isClosed ? (
                <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
                  <p className="text-sm font-semibold text-slate-900">
                    {item.justification_text ? "Revisar justificativa" : "Justificar este caso"}
                  </p>
                  <div className="mt-3 grid gap-3">
                    <select
                      className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
                      value={reasonId}
                      onChange={(event) => setReasonId(event.target.value)}
                    >
                      <option value="">Selecione o motivo</option>
                      {reasons.map((reason) => (
                        <option key={reason.id} value={reason.id}>
                          {reason.name}
                        </option>
                      ))}
                    </select>
                    {selectedReason?.description ? (
                      <p className="-mt-1 text-xs text-slate-500">{selectedReason.description}</p>
                    ) : null}
                    <Textarea
                      rows={4}
                      placeholder={
                        needsLongText
                          ? "Este motivo exige detalhamento (mínimo de 15 caracteres)."
                          : "Descreva o que aconteceu no período."
                      }
                      value={justification}
                      onChange={(event) => setJustification(event.target.value)}
                    />
                    {needsLongText ? (
                      <p className={cn(
                        "-mt-1 text-xs",
                        justification.trim().length >= 15 ? "text-emerald-600" : "text-amber-600"
                      )}>
                        Este motivo exige detalhamento: {justification.trim().length}/15 caracteres mínimos.
                      </p>
                    ) : null}
                    <Textarea
                      rows={3}
                      placeholder="Plano de ação (opcional): o que será feito para corrigir."
                      value={actionPlan}
                      onChange={(event) => setActionPlan(event.target.value)}
                    />
                    <div className="flex justify-end">
                      <Button
                        type="button"
                        onClick={() => void submitJustification()}
                        disabled={saving || justification.trim().length < 3 || (needsLongText && justification.trim().length < 15)}
                      >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                        Enviar justificativa
                      </Button>
                    </div>
                  </div>
                </div>
              ) : null}

              {canReview && !isClosed ? (
                <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-4">
                  <p className="text-sm font-semibold text-slate-900">Decisão da matriz</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.status === "pending"
                      ? "O caso ainda não foi justificado — só é possível rejeitar ou devolver para andamento."
                      : "Aceite a justificativa, rejeite ou devolva para complemento."}
                  </p>
                  <Textarea
                    rows={2}
                    className="mt-3"
                    placeholder="Nota da decisão (opcional) — fica registrada como comentário."
                    value={reviewNote}
                    onChange={(event) => setReviewNote(event.target.value)}
                  />
                  <div className="mt-3 flex flex-wrap justify-end gap-2">
                    <Button type="button" variant="outline" disabled={saving} onClick={() => void submitReview("in_progress")}>
                      <Clock3 className="h-4 w-4" /> Devolver
                    </Button>
                    <Button type="button" variant="outline" disabled={saving} onClick={() => void submitReview("rejected")}>
                      <XCircle className="h-4 w-4" /> Rejeitar
                    </Button>
                    <Button type="button" disabled={saving || item.status === "pending"} onClick={() => void submitReview("resolved")}>
                      <CheckCircle2 className="h-4 w-4" /> Aceitar e resolver
                    </Button>
                  </div>
                </div>
              ) : null}

              {isClosed ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  Caso encerrado como <strong>{CASE_STATUS_LABELS[item.status]}</strong> em {formatDateTime(item.reviewed_at)}.
                </div>
              ) : null}

              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Histórico ({comments.length})</p>
                <div className="mt-2 grid gap-2">
                  {comments.map((comment) => (
                    <div key={comment.id} className="rounded-lg border border-slate-200 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-slate-800">{comment.user_name ?? "Usuário removido"}</span>
                        <span className="text-xs text-slate-400">{formatDateTime(comment.created_at)}</span>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{comment.comment}</p>
                    </div>
                  ))}
                  {!comments.length ? <p className="text-sm text-slate-400">Nenhum comentário ainda.</p> : null}
                </div>
                {canJustify ? (
                  <div className="mt-3 flex gap-2">
                    <Input
                      placeholder="Adicionar comentário"
                      value={newComment}
                      onChange={(event) => setNewComment(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void submitComment();
                      }}
                    />
                    <Button type="button" variant="outline" disabled={saving || newComment.trim().length < 2} onClick={() => void submitComment()}>
                      <MessageSquare className="h-4 w-4" /> Comentar
                    </Button>
                  </div>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
