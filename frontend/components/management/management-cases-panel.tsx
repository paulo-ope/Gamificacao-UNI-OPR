"use client";

import {
  CheckCircle2,
  FileDown,
  Loader2,
  MessageSquare,
  Search,
  Sparkles,
  Zap,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import { cn } from "@/lib/utils";
import type {
  ManagementAutoGenerateSettings,
  ManagementCase,
  ManagementCaseFilters,
  ManagementCasePage,
  ManagementCaseReason,
  ManagementOptions,
} from "@/lib/types";
import {
  CASE_STATUS_LABELS,
  CASE_TYPE_LABELS,
  SEVERITY_LABELS,
  decimal,
  formatDate,
  previousMonth,
  severityTone,
  statusTone,
} from "./case-format-helpers";
import { CaseDetailDialog } from "./management-case-detail-dialog";

export { CASE_STATUS_LABELS, CASE_TYPE_LABELS } from "./case-format-helpers";
export { ManagementCaseDiagnosticsPanel } from "./management-case-diagnostics-panel";
export { CaseDetailDialog } from "./management-case-detail-dialog";

const PAGE_SIZE = 25;

export function ManagementCasesPanel({
  options,
  canReview,
  canGenerate = false,
  canJustify,
  canAdmin = false,
}: {
  options: ManagementOptions;
  canReview: boolean;
  // Separado de canReview de propósito: "gerar casos do mês" e "aprovar/rejeitar a decisão da
  // matriz" já foram a mesma permissão (management:review) e isso deixava impossível dar acesso
  // de gerar sem também dar poder de aprovação (achado real) - ver management:generate_cases.
  canGenerate?: boolean;
  canJustify: boolean;
  canAdmin?: boolean;
}) {
  const initialPeriod = useMemo(previousMonth, []);
  const [data, setData] = useState<ManagementCasePage | null>(null);
  const [reasons, setReasons] = useState<ManagementCaseReason[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [autoGenerate, setAutoGenerate] = useState<ManagementAutoGenerateSettings | null>(null);
  const [autoGenerateSaving, setAutoGenerateSaving] = useState(false);
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
  // Aprovação em lote e exportação usam o MESMO recorte filtrado hoje na tabela - pedido do
  // usuário em 2026-08-20, pra matriz não ter que ir caso por caso. O diagnóstico (ranking por
  // motivo/colaborador/regional) mudou pra aba própria (ManagementCaseDiagnosticsPanel).
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkReviewing, setBulkReviewing] = useState(false);
  const [exporting, setExporting] = useState(false);

  const baseQuery = useMemo(
    (): Omit<ManagementCaseFilters, "page" | "page_size"> => ({
      search: filters.search || undefined,
      regional: filters.regional || undefined,
      severity: filters.severity || undefined,
      status: filters.status || undefined,
      only_overdue: filters.only_overdue || undefined,
      only_open: filters.only_open || undefined,
    }),
    [filters]
  );

  const load = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      setError(null);
      try {
        const query: ManagementCaseFilters = { ...baseQuery, page: targetPage, page_size: PAGE_SIZE };
        setData(await api.managementCases(query));
        setSelectedIds(new Set());
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Não foi possível carregar os casos.");
      } finally {
        setLoading(false);
      }
    },
    [baseQuery, page]
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

  useEffect(() => {
    if (!canGenerate) return;
    void api.managementAutoGenerateSettings().then(setAutoGenerate).catch(() => undefined);
  }, [canGenerate]);

  async function toggleAutoGenerate(next: boolean) {
    setAutoGenerateSaving(true);
    setError(null);
    try {
      setAutoGenerate(await api.updateManagementAutoGenerateSettings(next));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar a geração automática.");
    } finally {
      setAutoGenerateSaving(false);
    }
  }

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

  function toggleSelected(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    const visibleIds = (data?.items ?? []).map((item) => item.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set() : new Set(visibleIds));
  }

  async function bulkReview(status: "resolved" | "rejected") {
    if (!selectedIds.size) return;
    setBulkReviewing(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.bulkReviewManagementCases({ case_ids: Array.from(selectedIds), status });
      setMessage(
        `${result.updated_cases} caso(s) ${status === "resolved" ? "resolvido(s)" : "rejeitado(s)"}.` +
          (result.skipped_pending ? ` ${result.skipped_pending} pulado(s) - ainda não justificado(s).` : "")
      );
      await load(page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao aplicar a decisão em lote.");
    } finally {
      setBulkReviewing(false);
    }
  }

  async function exportCsv() {
    setExporting(true);
    setError(null);
    try {
      const blob = await api.exportManagementCases(baseQuery);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "casos_gestao.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao exportar os casos.");
    } finally {
      setExporting(false);
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
          {canGenerate ? (
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
        {canGenerate && autoGenerate ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2">
            <Zap className={cn("h-4 w-4", autoGenerate.enabled ? "text-emerald-600" : "text-slate-400")} />
            <span className="text-xs font-medium text-slate-800">
              Geração automática de casos: {autoGenerate.enabled ? "ativada" : "desativada"}
              {autoGenerate.last_run_date ? ` · ${formatDate(autoGenerate.last_run_date)}` : ""}
            </span>
            {canAdmin ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={autoGenerateSaving}
                onClick={() => void toggleAutoGenerate(!autoGenerate.enabled)}
              >
                {autoGenerateSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {autoGenerate.enabled ? "Desativar" : "Ativar"}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto p-4">
          <Table>
            <TableHeader>
              <TableRow>
                {canReview ? (
                  <TableHead className="w-8">
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 rounded border-slate-300"
                      aria-label="Selecionar todos os casos visíveis"
                      checked={Boolean(data?.items.length) && data!.items.every((item) => selectedIds.has(item.id))}
                      onChange={toggleSelectAllVisible}
                    />
                  </TableHead>
                ) : null}
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
                  {canReview ? (
                    <TableCell onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-slate-300"
                        aria-label={`Selecionar caso de ${item.responsible_name ?? "colaborador"}`}
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleSelected(item.id)}
                      />
                    </TableCell>
                  ) : null}
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
                    {/* Caso diário: mostra o dia exato (a competência mensal por si só escondia
                       QUAL dia gerou o caso). Caso mensal: mantém mês/ano, não há dia único. */}
                    {item.case_type === "daily_performance_below_target" && item.reference_date
                      ? formatDate(item.reference_date)
                      : item.reference_month
                        ? `${String(item.reference_month).padStart(2, "0")}/${item.reference_year}`
                        : "—"}
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
                  <TableCell colSpan={canReview ? 9 : 8} className="py-12 text-center text-sm text-slate-500">
                    {filters.only_open
                      ? "Nenhum caso em aberto neste recorte. 🎉"
                      : "Nenhum caso encontrado para este recorte."}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
        {canReview && selectedIds.size > 0 ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-violet-200 bg-violet-50/60 px-4 py-2.5 text-sm">
            <span className="font-medium text-slate-700">{selectedIds.size} caso(s) selecionado(s)</span>
            <Button type="button" size="sm" disabled={bulkReviewing} onClick={() => void bulkReview("resolved")}>
              {bulkReviewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              Aceitar e resolver selecionados
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={bulkReviewing} onClick={() => void bulkReview("rejected")}>
              {bulkReviewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5" />}
              Rejeitar selecionados
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
              Limpar seleção
            </Button>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" variant="outline" disabled={exporting} onClick={() => void exportCsv()}>
              {exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />}
              Exportar CSV
            </Button>
          </div>
          {data && data.total > PAGE_SIZE ? (
            <div className="flex items-center gap-3">
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
