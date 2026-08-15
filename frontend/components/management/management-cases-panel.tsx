"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  MessageSquare,
  Search,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import { cn } from "@/lib/utils";
import type {
  ManagementCase,
  ManagementCaseComment,
  ManagementCaseFilters,
  ManagementCasePage,
  ManagementCaseReason,
  ManagementOptions,
} from "@/lib/types";

const PAGE_SIZE = 25;

export const CASE_STATUS_LABELS: Record<string, string> = {
  pending: "Aguardando justificativa",
  justified: "Justificado",
  in_progress: "Em andamento",
  resolved: "Resolvido",
  rejected: "Rejeitado",
  overdue: "Em atraso",
};

const SEVERITY_LABELS: Record<string, string> = { high: "Alta", medium: "Média", low: "Baixa" };

export const CASE_TYPE_LABELS: Record<string, string> = {
  productivity_below_target: "Produtividade abaixo da meta",
  daily_performance_below_target: "Dia abaixo da meta",
};

function severityTone(severity: string) {
  if (severity === "high") return "border-red-200 bg-red-50 text-red-700";
  if (severity === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-100 text-slate-600";
}

function statusTone(status: string) {
  if (status === "resolved") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "rejected") return "border-slate-200 bg-slate-100 text-slate-600";
  if (status === "justified") return "border-blue-200 bg-blue-50 text-blue-700";
  if (status === "in_progress") return "border-violet-200 bg-violet-50 text-violet-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("pt-BR", { timeZone: "America/Porto_Velho" });
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Porto_Velho" });
}

function decimal(value: number | null) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value);
}

function previousMonth() {
  // A competência padrão é o mês anterior: cobrar produtividade do mês corrente, ainda em curso,
  // geraria caso em cima de dado incompleto.
  const now = new Date();
  const reference = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return { year: reference.getFullYear(), month: reference.getMonth() + 1 };
}

export function ManagementCasesPanel({
  options,
  canReview,
  canJustify,
}: {
  options: ManagementOptions;
  canReview: boolean;
  canJustify: boolean;
}) {
  const initialPeriod = useMemo(previousMonth, []);
  const [data, setData] = useState<ManagementCasePage | null>(null);
  const [reasons, setReasons] = useState<ManagementCaseReason[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<ManagementCase | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    search: "",
    regional: "",
    severity: "",
    status: "",
    only_overdue: false,
    only_open: true,
  });
  const [period, setPeriod] = useState(initialPeriod);

  const load = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      setError(null);
      try {
        const query: ManagementCaseFilters = {
          page: targetPage,
          page_size: PAGE_SIZE,
          search: filters.search || undefined,
          regional: filters.regional || undefined,
          severity: filters.severity || undefined,
          status: filters.status || undefined,
          only_overdue: filters.only_overdue || undefined,
          only_open: filters.only_open || undefined,
        };
        setData(await api.managementCases(query));
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Não foi possível carregar os casos.");
      } finally {
        setLoading(false);
      }
    },
    [filters, page]
  );

  useEffect(() => {
    void load(1);
    setPage(1);
    // A busca é disparada pelo botão Filtrar; recarregar a cada tecla brigaria com a digitação.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.only_open, filters.only_overdue]);

  useEffect(() => {
    void api.managementCaseReasons().then(setReasons).catch(() => undefined);
  }, []);

  // Abre direto o caso quando a tela é acessada via link de notificação (?case_id=97) - só
  // precisa do id, o próprio CaseDetailDialog busca o resto (ver uso de `selected.id` abaixo).
  const searchParams = useSearchParams();
  useEffect(() => {
    const caseIdParam = searchParams.get("case_id");
    const caseId = caseIdParam ? Number(caseIdParam) : null;
    if (caseId && Number.isFinite(caseId)) {
      setSelected({ id: caseId } as ManagementCase);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function generate() {
    setGenerating(true);
    setError(null);
    setMessage(null);
    try {
      // Ano pode estar vazio (NaN) se o usuário limpou o campo pra digitar de novo - nunca mandar
      // isso pra API, cai no ano do período inicial.
      const year = Number.isFinite(period.year) ? period.year : initialPeriod.year;
      const result = await api.generateManagementCases(year, period.month);
      setMessage(
        result.created_cases > 0
          ? `${result.created_cases} caso(s) aberto(s) para ${String(period.month).padStart(2, "0")}/${period.year}.`
          : `Nenhum desvio acima do limiar em ${String(period.month).padStart(2, "0")}/${period.year} (${result.evaluated_members} colaborador(es) avaliado(s), ${result.skipped_existing} já tinham caso).`
      );
      await load(1);
      setPage(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao gerar casos.");
    } finally {
      setGenerating(false);
    }
  }

  const summary = data?.summary;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const regionals = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((item) => item.regional).filter(Boolean) as string[])).sort(),
    [data]
  );

  return (
    <div className="grid gap-4">
      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {(
          [
            ["Em aberto", summary?.open_cases ?? 0, "Ainda cobram ação", "text-slate-950"],
            ["Aguardando justificativa", summary?.pending_cases ?? 0, "Com o supervisor", "text-amber-700"],
            ["Em atraso", summary?.overdue_cases ?? 0, "Passaram do prazo", "text-red-700"],
            ["Severidade alta", summary?.high_severity_open ?? 0, "Prioridade da matriz", "text-red-700"],
            // Os contadores seguem o MESMO recorte da tabela. Com "somente em aberto" ligado,
            // "Resolvidos" seria zero por construção - nessa hora o número útil é quantos já
            // voltaram justificados e esperam a decisão da matriz.
            filters.only_open
              ? (["Justificados", summary?.justified_cases ?? 0, "Aguardam a matriz", "text-blue-700"] as const)
              : (["Resolvidos", summary?.resolved_cases ?? 0, "Encerrados no recorte", "text-emerald-700"] as const),
          ] as const
        ).map(([label, value, hint, tone]) => (
          <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-slate-500">{label}</p>
            <p className={`mt-2 text-3xl font-semibold tabular-nums ${tone}`}>{value}</p>
            <p className="mt-1 text-xs text-slate-400">{hint}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr_1fr_1fr_auto]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <Input
              className="pl-9"
              placeholder="Buscar colaborador, regional ou métrica"
              value={filters.search}
              onChange={(event) => setFilters({ ...filters, search: event.target.value })}
              onKeyDown={(event) => {
                if (event.key === "Enter") void load(1);
              }}
            />
          </div>
          <select
            className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
            value={filters.regional}
            onChange={(event) => setFilters({ ...filters, regional: event.target.value })}
          >
            <option value="">Todas as regionais</option>
            {regionals.map((regional) => (
              <option key={regional} value={regional}>
                {regional}
              </option>
            ))}
          </select>
          <select
            className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
            value={filters.severity}
            onChange={(event) => setFilters({ ...filters, severity: event.target.value })}
          >
            <option value="">Todas as severidades</option>
            {Object.entries(SEVERITY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
            value={filters.status}
            onChange={(event) => setFilters({ ...filters, status: event.target.value })}
          >
            <option value="">Todos os status</option>
            {Object.entries(CASE_STATUS_LABELS)
              .filter(([value]) => value !== "overdue")
              .map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
          </select>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setPage(1);
              void load(1);
            }}
            disabled={loading}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Filtrar
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-600">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 rounded border-slate-300"
              checked={filters.only_open}
              onChange={(event) => setFilters({ ...filters, only_open: event.target.checked })}
            />
            Somente em aberto
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-600">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 rounded border-slate-300"
              checked={filters.only_overdue}
              onChange={(event) => setFilters({ ...filters, only_overdue: event.target.checked })}
            />
            Somente em atraso
          </label>
          {canReview ? (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs font-medium text-slate-500">Competência</span>
              <select
                className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm"
                value={period.month}
                onChange={(event) => setPeriod({ ...period, month: Number(event.target.value) })}
              >
                {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => (
                  <option key={month} value={month}>
                    {String(month).padStart(2, "0")}
                  </option>
                ))}
              </select>
              <Input
                type="number"
                className="h-9 w-24"
                value={numericInputValue(period.year)}
                onChange={(event) => setPeriod({ ...period, year: parseNumericInput(event.target.value) })}
              />
              <Button type="button" onClick={() => void generate()} disabled={generating}>
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Gerar casos do mês
              </Button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto p-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Colaborador</TableHead>
                <TableHead>Regional</TableHead>
                <TableHead>Desvio</TableHead>
                <TableHead>Competência</TableHead>
                <TableHead>Severidade</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Prazo</TableHead>
                <TableHead>Supervisor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.items ?? []).map((item) => (
                <TableRow
                  key={item.id}
                  className="cursor-pointer odd:bg-slate-50/60 hover:bg-blue-50/60"
                  onClick={() => setSelected(item)}
                >
                  <TableCell className="min-w-56">
                    <div className="font-medium text-slate-950">{item.responsible_name ?? "—"}</div>
                    <div className="mt-0.5 text-xs text-slate-500">{CASE_TYPE_LABELS[item.case_type] ?? item.case_type}</div>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{item.regional ?? "—"}</TableCell>
                  <TableCell className="min-w-44 text-sm">
                    <span className="font-semibold tabular-nums text-slate-900">{decimal(item.actual_value)}</span>
                    <span className="text-slate-400"> de </span>
                    <span className="tabular-nums text-slate-600">{decimal(item.expected_value)}</span>
                    {item.deviation_value !== null ? (
                      <span className="ml-1 font-medium tabular-nums text-red-600">(-{decimal(item.deviation_value)}%)</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-sm tabular-nums text-slate-600">
                    {item.reference_month ? `${String(item.reference_month).padStart(2, "0")}/${item.reference_year}` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge className={severityTone(item.severity)}>{SEVERITY_LABELS[item.severity] ?? item.severity}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge className={statusTone(item.status)}>{CASE_STATUS_LABELS[item.status] ?? item.status}</Badge>
                      {item.comment_count > 0 ? (
                        <span className="inline-flex items-center gap-0.5 text-xs text-slate-400">
                          <MessageSquare className="h-3 w-3" />
                          {item.comment_count}
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className={item.is_overdue ? "font-semibold text-red-600" : "text-slate-600"}>
                      {formatDate(item.due_date)}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-44 truncate text-sm text-slate-600">{item.supervisor_name ?? "—"}</TableCell>
                </TableRow>
              ))}
              {data && !data.items.length ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-12 text-center text-sm text-slate-500">
                    {filters.only_open
                      ? "Nenhum caso em aberto neste recorte. 🎉"
                      : "Nenhum caso encontrado para este recorte."}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
        {data && data.total > PAGE_SIZE ? (
          <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
            <span>
              Página {data.page} de {totalPages} · {data.total} caso(s)
            </span>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page <= 1 || loading}
                onClick={() => {
                  const next = page - 1;
                  setPage(next);
                  void load(next);
                }}
              >
                Anterior
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page >= totalPages || loading}
                onClick={() => {
                  const next = page + 1;
                  setPage(next);
                  void load(next);
                }}
              >
                Próxima
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      {selected ? (
        <CaseDetailDialog
          caseId={selected.id}
          reasons={reasons}
          canReview={canReview}
          canJustify={canJustify}
          onClose={() => setSelected(null)}
          onChanged={() => void load(page)}
        />
      ) : null}
    </div>
  );
}

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
                {item.reference_month ? ` · ${String(item.reference_month).padStart(2, "0")}/${item.reference_year}` : ""}
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
