"use client";

import { AlertTriangle, CheckCircle2, Plus, Undo2, Eye, EyeOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { OrderAuditSheet } from "@/components/gamification/order-audit-drawer";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime, formatMoney, formatPoints, formatSignedPoints } from "@/lib/format";
import type { CollaboratorMonthlyHistoryItem, CollaboratorOrderDetail, CollaboratorPointBalance, PointBalanceEntry } from "@/lib/types";

type Props = {
  collaboratorId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isAdmin?: boolean;
  onChanged?: () => void;
};

const ENTRY_TYPE_LABEL: Record<string, string> = {
  post_payment_warranty_debit: "Garantia pós-pagamento",
  period_settlement: "Saldo remanescente (carry-over)",
  manual_adjustment: "Ajuste manual"
};

const STATUS_META: Record<string, { label: string; className: string }> = {
  pending: { label: "Pendente", className: "border-amber-200 bg-amber-50 text-amber-800" },
  applied: { label: "Aplicado", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  reverted: { label: "Estornado", className: "border-slate-200 bg-slate-50 text-slate-500" }
};

function formatPeriod(month: number | null, year: number | null) {
  if (!month || !year) return null;
  return `${String(month).padStart(2, "0")}/${year}`;
}

export function entryTrace(entry: PointBalanceEntry) {
  if (entry.entry_type !== "post_payment_warranty_debit" || !entry.original_os_code) {
    return entry.reason ?? "-";
  }
  const originPeriod = formatPeriod(entry.origin_run_month, entry.origin_run_year);
  const targetPeriod = formatPeriod(entry.target_reference_month, entry.target_reference_year);
  let tail = targetPeriod
    ? `aguardando o fechamento de ${targetPeriod} (mês do retorno) ser pago`
    : "aguardando o próximo fechamento pago do colaborador";
  if (entry.status === "applied") {
    const appliedPeriod = formatPeriod(entry.applied_reference_month, entry.applied_reference_year);
    tail = appliedPeriod ? `aplicado no fechamento de ${appliedPeriod}` : "aplicado";
  } else if (entry.status === "reverted") {
    tail = "estornado manualmente";
  }
  return `O.S ${entry.original_os_code}${originPeriod ? ` (pago ${originPeriod})` : ""} → garantia O.S ${entry.related_os_code ?? "-"} → ${tail}`;
}

const TIMELINE_STATUS_TONE: Record<string, string> = {
  emerald: "border-emerald-300 bg-emerald-50 text-emerald-700",
  amber: "border-amber-300 bg-amber-50 text-amber-800",
  slate: "border-slate-300 bg-slate-50 text-slate-500"
};

function WarrantyTraceTimeline({
  entry,
  onOpenOrder
}: {
  entry: PointBalanceEntry;
  onOpenOrder: (serviceOrderId: number | null) => void;
}) {
  const originPeriod = formatPeriod(entry.origin_run_month, entry.origin_run_year);
  const appliedPeriod = formatPeriod(entry.applied_reference_month, entry.applied_reference_year);
  const targetPeriod = formatPeriod(entry.target_reference_month, entry.target_reference_year);
  const statusNode =
    entry.status === "applied"
      ? { label: appliedPeriod ? `Aplicado ${appliedPeriod}` : "Aplicado", tone: "emerald" }
      : entry.status === "reverted"
        ? { label: "Estornado", tone: "slate" }
        : { label: targetPeriod ? `Aguardando ${targetPeriod}` : "Aguardando pagamento", tone: "amber" };

  return (
    <div className="flex items-center gap-1 text-xs">
      <button
        type="button"
        onClick={() => onOpenOrder(entry.original_service_order_id)}
        className="flex min-w-0 flex-col items-center gap-0.5 rounded-lg border border-slate-200 bg-white px-2 py-1 transition hover:border-blue-300 hover:bg-blue-50/50"
        title="Ver auditoria da O.S original"
      >
        <span className="truncate font-semibold text-slate-800">{entry.original_os_code}</span>
        <span className="whitespace-nowrap text-[10px] text-slate-400">{originPeriod ? `pago ${originPeriod}` : "original"}</span>
      </button>
      <div className="h-px w-3 shrink-0 bg-slate-300" />
      <button
        type="button"
        onClick={() => onOpenOrder(entry.related_service_order_id)}
        className="flex min-w-0 flex-col items-center gap-0.5 rounded-lg border border-slate-200 bg-white px-2 py-1 transition hover:border-blue-300 hover:bg-blue-50/50"
        title="Ver auditoria da O.S de garantia"
      >
        <span className="truncate font-semibold text-slate-800">{entry.related_os_code ?? "-"}</span>
        <span className="whitespace-nowrap text-[10px] text-slate-400">garantia</span>
      </button>
      <div className="h-px w-3 shrink-0 bg-slate-300" />
      <div className={`shrink-0 rounded-lg border px-2 py-1 text-center ${TIMELINE_STATUS_TONE[statusNode.tone]}`}>
        <span className="whitespace-nowrap font-semibold">{statusNode.label}</span>
      </div>
    </div>
  );
}

export function CollaboratorBalanceHistorySheet({ collaboratorId, open, onOpenChange, isAdmin = false, onChanged }: Props) {
  const [data, setData] = useState<CollaboratorPointBalance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showReverted, setShowReverted] = useState(false);
  const [busyEntryId, setBusyEntryId] = useState<number | null>(null);
  const [auditOrder, setAuditOrder] = useState<(CollaboratorOrderDetail & { collaborator_name?: string }) | null>(null);
  const [monthly, setMonthly] = useState<CollaboratorMonthlyHistoryItem[]>([]);

  const [adjustmentOpen, setAdjustmentOpen] = useState(false);
  const [adjustmentPoints, setAdjustmentPoints] = useState("");
  const [adjustmentReason, setAdjustmentReason] = useState("");
  const [adjustmentError, setAdjustmentError] = useState<string | null>(null);
  const [adjustmentSubmitting, setAdjustmentSubmitting] = useState(false);

  const [reviewEntry, setReviewEntry] = useState<PointBalanceEntry | null>(null);
  const [reviewPoints, setReviewPoints] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [reviewError, setReviewError] = useState<string | null>(null);

  const [revertEntry, setRevertEntry] = useState<PointBalanceEntry | null>(null);
  const [revertReason, setRevertReason] = useState("");
  const [revertError, setRevertError] = useState<string | null>(null);

  async function openOsAudit(serviceOrderId: number | null) {
    if (!serviceOrderId) return;
    setError(null);
    try {
      const order = await api.auditOrderDetail(serviceOrderId);
      setAuditOrder(order);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível abrir a auditoria desta O.S.");
    }
  }

  const load = useCallback(() => {
    if (!collaboratorId) return;
    setLoading(true);
    setError(null);
    api
      .collaboratorPointBalance(collaboratorId)
      .then(setData)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [collaboratorId]);

  useEffect(() => {
    if (!open || !collaboratorId) return;
    load();
  }, [open, collaboratorId, load]);

  useEffect(() => {
    if (!open || !collaboratorId) {
      setMonthly([]);
      return;
    }
    let cancelled = false;
    api
      .collaboratorMonthlyHistory(collaboratorId)
      .then((rows) => {
        if (!cancelled) setMonthly(rows);
      })
      .catch(() => {
        if (!cancelled) setMonthly([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, collaboratorId]);

  function openManualAdjustment() {
    if (!isAdmin || !collaboratorId) return;
    setAdjustmentPoints("");
    setAdjustmentReason("");
    setAdjustmentError(null);
    setAdjustmentOpen(true);
  }

  async function submitManualAdjustment() {
    if (!collaboratorId) return;
    const points = Number(adjustmentPoints.replace(",", "."));
    if (!Number.isFinite(points) || points === 0) {
      setAdjustmentError("Valor inválido. Informe um número diferente de zero.");
      return;
    }
    if (!adjustmentReason.trim()) {
      setAdjustmentError("O motivo do ajuste manual é obrigatório.");
      return;
    }
    setAdjustmentSubmitting(true);
    setAdjustmentError(null);
    try {
      await api.createPointBalanceAdjustment({ collaborator_id: collaboratorId, points, reason: adjustmentReason.trim() });
      setAdjustmentOpen(false);
      load();
      onChanged?.();
    } catch (err) {
      setAdjustmentError(err instanceof Error ? err.message : "Erro ao lançar o ajuste manual.");
    } finally {
      setAdjustmentSubmitting(false);
    }
  }

  function openResolveReview(entry: PointBalanceEntry) {
    if (!isAdmin) return;
    setReviewPoints("");
    setReviewNote("");
    setReviewError(null);
    setReviewEntry(entry);
  }

  async function submitResolveReview() {
    if (!reviewEntry) return;
    const points = Number(reviewPoints.replace(",", "."));
    if (!Number.isFinite(points) || points >= 0) {
      setReviewError("Valor inválido. O débito confirmado deve ser um número negativo (ex: -10).");
      return;
    }
    setBusyEntryId(reviewEntry.id);
    setReviewError(null);
    try {
      await api.resolvePointBalanceReview(reviewEntry.id, points, reviewNote.trim() || undefined);
      setReviewEntry(null);
      load();
      onChanged?.();
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : "Erro ao resolver a revisão.");
    } finally {
      setBusyEntryId(null);
    }
  }

  function openRevert(entry: PointBalanceEntry) {
    if (!isAdmin) return;
    setRevertReason("");
    setRevertError(null);
    setRevertEntry(entry);
  }

  async function submitRevert() {
    if (!revertEntry) return;
    setBusyEntryId(revertEntry.id);
    setRevertError(null);
    try {
      await api.revertPointBalanceEntry(revertEntry.id, revertReason.trim() || undefined);
      setRevertEntry(null);
      load();
      onChanged?.();
    } catch (err) {
      setRevertError(err instanceof Error ? err.message : "Erro ao estornar o lançamento.");
    } finally {
      setBusyEntryId(null);
    }
  }

  const allEntries = data?.entries ?? [];
  const revertedCount = allEntries.filter((entry) => entry.status === "reverted").length;
  const visibleEntries = showReverted ? allEntries : allEntries.filter((entry) => entry.status !== "reverted");

  return (
    <>
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[min(1100px,96vw)]">
        <SheetHeader>
          <SheetTitle>Histórico de saldo de pontos - {data?.collaborator_name ?? "Colaborador"}</SheetTitle>
          <SheetDescription>
            {data ? (
              <>
                Saldo atual:{" "}
                <span className={data.balance_points < 0 ? "font-semibold text-red-600" : "font-semibold text-slate-700"}>
                  {formatSignedPoints(data.balance_points)}
                </span>
                {data.updated_at ? ` · atualizado em ${formatDateTime(data.updated_at)}` : ""}
              </>
            ) : (
              "Carregando..."
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-auto px-6 py-5">
          {isAdmin ? (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
              <span className="text-sm text-slate-600">Precisa corrigir o saldo manualmente? Todo ajuste fica registrado na auditoria.</span>
              <Button type="button" variant="outline" size="sm" onClick={openManualAdjustment}>
                <Plus className="h-4 w-4" />
                Lançar ajuste manual
              </Button>
            </div>
          ) : null}
          {error ? (
            <div className="mb-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          ) : null}

          {monthly.length > 0 ? (
            <div className="mb-5">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Histórico mês a mês</div>
              <div className="table-frame overflow-hidden rounded-lg border border-slate-200">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                    <TableRow className="border-slate-700 hover:bg-slate-900">
                      <TableHead>Mês</TableHead>
                      <TableHead>Situação</TableHead>
                      <TableHead>O.S</TableHead>
                      <TableHead>Pontos finais</TableHead>
                      <TableHead>Desconto de garantia</TableHead>
                      <TableHead>Valor pago/estimado</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {monthly.map((row) => (
                      <TableRow key={row.calculation_run_id}>
                        <TableCell className="whitespace-nowrap font-medium text-slate-900">
                          {String(row.reference_month).padStart(2, "0")}/{row.reference_year}
                        </TableCell>
                        <TableCell>
                          <Badge className={row.status === "paid" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"}>
                            {row.status === "paid" ? "Pago" : row.status === "approved" ? "Aprovado" : row.status === "review" ? "Conferência" : "Rascunho"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-slate-600">{row.service_orders_count}</TableCell>
                        <TableCell className="font-medium text-slate-900">{formatPoints(row.final_points)}</TableCell>
                        <TableCell className={row.balance_adjustment_points ? "font-medium text-red-600" : "text-slate-400"}>
                          {row.balance_adjustment_points ? formatSignedPoints(row.balance_adjustment_points) : "-"}
                        </TableCell>
                        <TableCell className="font-medium text-uni-royal">{formatMoney(row.estimated_payment)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : null}

          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Lançamentos de saldo de garantia</div>
            {revertedCount > 0 ? (
              <button
                type="button"
                onClick={() => setShowReverted((current) => !current)}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700"
              >
                {showReverted ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                {showReverted ? `Ocultar ${revertedCount} estornado(s)` : `Mostrar ${revertedCount} estornado(s)`}
              </button>
            ) : null}
          </div>
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
              <TableRow className="border-slate-700 hover:bg-slate-900">
                <TableHead>Status</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Impacto no pagamento</TableHead>
                <TableHead>Rastro (O.S original → garantia → aplicação)</TableHead>
                <TableHead>Detectado em</TableHead>
                {isAdmin ? <TableHead className="text-right">Ação</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleEntries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <Badge className={STATUS_META[entry.status]?.className ?? ""}>{STATUS_META[entry.status]?.label ?? entry.status}</Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm">{ENTRY_TYPE_LABEL[entry.entry_type] ?? entry.entry_type}</TableCell>
                  <TableCell className={entry.points < 0 ? "font-semibold text-red-600" : "font-semibold text-slate-700"}>
                    {entry.requires_review ? (
                      <span className="font-medium text-violet-700">Valor a definir</span>
                    ) : (
                      formatSignedPoints(entry.points)
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {entry.entry_type === "post_payment_warranty_debit" && entry.original_os_code ? (
                      <WarrantyTraceTimeline entry={entry} onOpenOrder={(id) => void openOsAudit(id)} />
                    ) : (
                      entryTrace(entry)
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm text-slate-500">{formatDateTime(entry.created_at)}</TableCell>
                  {isAdmin ? (
                    <TableCell className="text-right">
                      {entry.status === "pending" ? (
                        <div className="flex items-center justify-end gap-1">
                          {entry.requires_review ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2 text-emerald-700 hover:text-emerald-800"
                              disabled={busyEntryId === entry.id}
                              onClick={() => openResolveReview(entry)}
                              title="Resolver revisão manual (confirmar o valor do débito)"
                              aria-label="Resolver revisão manual (confirmar o valor do débito)"
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              <span className="ml-1 text-xs">Resolver</span>
                            </Button>
                          ) : null}
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-8 px-2 text-slate-500 hover:text-red-600"
                            disabled={busyEntryId === entry.id}
                            onClick={() => openRevert(entry)}
                            title={entry.requires_review ? "Descartar (sem aplicar débito)" : "Estornar garantia (diagnóstico incorreto)"}
                            aria-label={entry.requires_review ? "Descartar (sem aplicar débito)" : "Estornar garantia (diagnóstico incorreto)"}
                          >
                            <Undo2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ) : null}
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
              {!loading && visibleEntries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={isAdmin ? 6 : 5} className="py-8 text-center text-sm text-slate-500">
                    {allEntries.length === 0
                      ? "Nenhum lançamento de saldo para este colaborador."
                      : `Todos os ${revertedCount} lançamentos deste colaborador estão estornados.`}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
        <OrderAuditSheet
          order={auditOrder}
          open={Boolean(auditOrder)}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setAuditOrder(null);
          }}
        />
      </SheetContent>
    </Sheet>

    <Dialog open={adjustmentOpen} onOpenChange={setAdjustmentOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Lançar ajuste manual de saldo</DialogTitle>
          <DialogDescription>Use um número negativo para descontar pontos, ou positivo para creditar.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="adjustment-points">Pontos</Label>
            <Input
              id="adjustment-points"
              inputMode="decimal"
              placeholder="Ex: -10 (desconto) ou 5 (crédito)"
              value={adjustmentPoints}
              onChange={(event) => setAdjustmentPoints(event.target.value)}
              autoFocus
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="adjustment-reason">Motivo (obrigatório)</Label>
            <Textarea
              id="adjustment-reason"
              value={adjustmentReason}
              onChange={(event) => setAdjustmentReason(event.target.value)}
              placeholder="Explique o motivo do ajuste manual"
            />
          </div>
          {adjustmentError ? <p className="text-sm text-red-600">{adjustmentError}</p> : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setAdjustmentOpen(false)}>
            Cancelar
          </Button>
          <Button type="button" onClick={() => void submitManualAdjustment()} disabled={adjustmentSubmitting}>
            {adjustmentSubmitting ? "Lançando..." : "Lançar ajuste"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog open={reviewEntry !== null} onOpenChange={(nextOpen) => !nextOpen && setReviewEntry(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolver revisão manual</DialogTitle>
          <DialogDescription>
            O.S {reviewEntry?.related_os_code ?? reviewEntry?.id} - informe o valor do débito a confirmar (número negativo).
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="review-points">Débito confirmado</Label>
            <Input
              id="review-points"
              inputMode="decimal"
              placeholder="Ex: -10"
              value={reviewPoints}
              onChange={(event) => setReviewPoints(event.target.value)}
              autoFocus
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="review-note">Observação (opcional)</Label>
            <Textarea id="review-note" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
          </div>
          {reviewError ? <p className="text-sm text-red-600">{reviewError}</p> : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setReviewEntry(null)}>
            Cancelar
          </Button>
          <Button type="button" onClick={() => void submitResolveReview()} disabled={busyEntryId === reviewEntry?.id}>
            {busyEntryId === reviewEntry?.id ? "Resolvendo..." : "Resolver"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog open={revertEntry !== null} onOpenChange={(nextOpen) => !nextOpen && setRevertEntry(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{revertEntry?.requires_review ? "Descartar lançamento" : "Estornar garantia"}</DialogTitle>
          <DialogDescription>
            {revertEntry
              ? `${revertEntry.requires_review ? "Descartar" : "Estornar"} ${formatSignedPoints(revertEntry.points)} (O.S ${revertEntry.related_os_code ?? revertEntry.id})? Use isto se o diagnóstico de garantia estiver errado.`
              : null}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="revert-reason">Motivo (opcional)</Label>
            <Textarea id="revert-reason" value={revertReason} onChange={(event) => setRevertReason(event.target.value)} autoFocus />
          </div>
          {revertError ? <p className="text-sm text-red-600">{revertError}</p> : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setRevertEntry(null)}>
            Cancelar
          </Button>
          <Button type="button" variant="destructive" onClick={() => void submitRevert()} disabled={busyEntryId === revertEntry?.id}>
            {busyEntryId === revertEntry?.id ? "Enviando..." : revertEntry?.requires_review ? "Descartar" : "Estornar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
