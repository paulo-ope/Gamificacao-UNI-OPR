"use client";

import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, ScrollText, Search, ShieldAlert, Wallet } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/gamification/config-ui";
import { CollaboratorBalanceHistorySheet } from "@/components/gamification/collaborator-balance-history-sheet";
import { InfoHint } from "@/components/gamification/info-hint";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime, formatSignedPoints } from "@/lib/format";
import type { PointBalanceEntry } from "@/lib/types";

type Props = {
  isAdmin: boolean;
  calculationRunId?: number | null;
  referenceMonth?: number | null;
  referenceYear?: number | null;
  runStatus?: string | null;
};

type CollaboratorGroup = {
  collaboratorId: number;
  collaboratorName: string;
  entries: PointBalanceEntry[];
  totalPoints: number;
  warrantyCount: number;
  requiresReviewCount: number;
  lastDetectedAt: string | null;
};

type StatusFilter = "all" | "review";
type SortMode = "severity" | "name" | "recent";

function StatCard({
  icon: Icon,
  label,
  value,
  tone = "neutral"
}: {
  icon: typeof Wallet;
  label: string;
  value: string | number;
  tone?: "neutral" | "danger" | "warning" | "good";
}) {
  const toneClasses =
    tone === "danger"
      ? "border-red-200 bg-red-50/60"
      : tone === "warning"
        ? "border-amber-300 bg-amber-50 ring-1 ring-amber-200"
        : tone === "good"
          ? "border-emerald-200 bg-emerald-50/60"
          : "border-slate-200 bg-white";
  const iconToneClasses =
    tone === "danger"
      ? "bg-red-100 text-red-700"
      : tone === "warning"
        ? "bg-amber-100 text-amber-700"
        : tone === "good"
          ? "bg-emerald-100 text-emerald-700"
          : "bg-slate-100 text-slate-600";
  const valueToneClasses =
    tone === "danger" ? "text-red-700" : tone === "warning" ? "text-amber-800" : tone === "good" ? "text-emerald-700" : "text-slate-950";

  return (
    <div className={`flex items-center gap-3 rounded-2xl border px-3 py-3 transition-shadow ${toneClasses}`}>
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${iconToneClasses}`}>
        <Icon className="h-4.5 w-4.5" />
      </div>
      <div className="min-w-0">
        <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</div>
        <div className={`mt-0.5 text-lg font-semibold leading-tight ${valueToneClasses}`}>{value}</div>
      </div>
    </div>
  );
}

export function PointBalancePanel({ isAdmin, calculationRunId, referenceMonth, referenceYear, runStatus }: Props) {
  const isPaidPeriod = runStatus === "paid";
  const [entries, setEntries] = useState<PointBalanceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("severity");
  const [historyCollaboratorId, setHistoryCollaboratorId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.pointBalancePending(
        calculationRunId
          ? { calculation_run_id: calculationRunId }
          : referenceMonth && referenceYear
            ? { reference_month: referenceMonth, reference_year: referenceYear }
            : undefined
      );
      setEntries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar o saldo de pontos.");
    } finally {
      setLoading(false);
    }
  }, [calculationRunId, referenceMonth, referenceYear]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
    const byCollaborator = new Map<number, CollaboratorGroup>();
    for (const entry of entries) {
      const existing = byCollaborator.get(entry.collaborator_id);
      const name = entry.collaborator_name ?? `Colaborador #${entry.collaborator_id}`;
      if (existing) {
        existing.entries.push(entry);
        existing.totalPoints += entry.requires_review ? 0 : entry.points;
        if (entry.entry_type === "post_payment_warranty_debit") existing.warrantyCount += 1;
        if (entry.requires_review) existing.requiresReviewCount += 1;
        if (!existing.lastDetectedAt || entry.created_at > existing.lastDetectedAt) existing.lastDetectedAt = entry.created_at;
      } else {
        byCollaborator.set(entry.collaborator_id, {
          collaboratorId: entry.collaborator_id,
          collaboratorName: name,
          entries: [entry],
          totalPoints: entry.requires_review ? 0 : entry.points,
          warrantyCount: entry.entry_type === "post_payment_warranty_debit" ? 1 : 0,
          requiresReviewCount: entry.requires_review ? 1 : 0,
          lastDetectedAt: entry.created_at
        });
      }
    }
    return Array.from(byCollaborator.values());
  }, [entries]);

  const maxDebt = useMemo(() => Math.max(1, ...groups.map((group) => Math.abs(group.totalPoints))), [groups]);

  const filteredGroups = useMemo(() => {
    const term = search.trim().toLowerCase();
    let list = groups;
    if (term) list = list.filter((group) => group.collaboratorName.toLowerCase().includes(term));
    if (statusFilter === "review") list = list.filter((group) => group.requiresReviewCount > 0);

    const sorted = [...list];
    if (sortMode === "severity") sorted.sort((a, b) => a.totalPoints - b.totalPoints);
    else if (sortMode === "name") sorted.sort((a, b) => a.collaboratorName.localeCompare(b.collaboratorName, "pt-BR"));
    else sorted.sort((a, b) => (b.lastDetectedAt ?? "").localeCompare(a.lastDetectedAt ?? ""));
    return sorted;
  }, [groups, search, statusFilter, sortMode]);

  const totals = useMemo(
    () => ({
      collaboratorsCount: groups.length,
      totalPoints: groups.reduce((total, group) => total + group.totalPoints, 0),
      requiresReviewCount: groups.reduce((total, group) => total + group.requiresReviewCount, 0),
      warrantyCount: groups.reduce((total, group) => total + group.warrantyCount, 0)
    }),
    [groups]
  );

  return (
    <div className="grid gap-4 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-950">{isPaidPeriod ? "Saldo de pontos descontado" : "Saldo de pontos pendente"}</h3>
          <InfoHint
            ariaLabel="Ajuda sobre saldo de pontos"
            description="Se o período selecionado ainda não foi pago: mostra o que seria descontado dos colaboradores deste fechamento se ele fosse marcado como pago agora (independente de quando a garantia/reincidência foi detectada). Se o período já foi pago: mostra o que realmente foi descontado nesse pagamento. Clique em Detalhar para auditar todas as O.S de garantia de um colaborador."
          />
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={Wallet}
          label={isPaidPeriod ? "Colaboradores com débito descontado" : "Colaboradores com débito pendente"}
          value={totals.collaboratorsCount}
        />
        <StatCard icon={ScrollText} label={isPaidPeriod ? "Garantias descontadas" : "Garantias pendentes"} value={totals.warrantyCount} />
        <StatCard
          icon={AlertTriangle}
          label={isPaidPeriod ? "Pontos descontados" : "Pontos pendentes de abatimento"}
          value={formatSignedPoints(totals.totalPoints)}
          tone="danger"
        />
        <StatCard
          icon={ShieldAlert}
          label="Aguardando revisão manual"
          value={totals.requiresReviewCount}
          tone={totals.requiresReviewCount > 0 ? "warning" : "good"}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar colaborador..." className="pl-9" />
        </div>
        <div className="flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1">
          <button
            type="button"
            onClick={() => setStatusFilter("all")}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              statusFilter === "all" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            Todos
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter("review")}
            className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              statusFilter === "review" ? "bg-violet-700 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <ShieldAlert className="h-3 w-3" />
            Em revisão
            {totals.requiresReviewCount > 0 ? (
              <span className={`ml-0.5 rounded-full px-1.5 text-[10px] ${statusFilter === "review" ? "bg-white/25" : "bg-violet-100 text-violet-700"}`}>
                {totals.requiresReviewCount}
              </span>
            ) : null}
          </button>
        </div>
        <select
          value={sortMode}
          onChange={(event) => setSortMode(event.target.value as SortMode)}
          className="h-9 rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600"
          title="Ordenar por"
        >
          <option value="severity">Maior dívida primeiro</option>
          <option value="recent">Mais recentes primeiro</option>
          <option value="name">Nome (A-Z)</option>
        </select>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <div className="table-frame overflow-hidden rounded-[20px] border border-slate-200 bg-white">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
            <TableRow className="border-slate-700 hover:bg-slate-900">
              <TableHead>Colaborador</TableHead>
              <TableHead>Garantias pendentes</TableHead>
              <TableHead>Impacto total no pagamento</TableHead>
              <TableHead>Última detecção</TableHead>
              <TableHead className="text-right">Auditar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredGroups.map((group) => {
              const severityPct = Math.min(100, Math.round((Math.abs(group.totalPoints) / maxDebt) * 100));
              const isReviewOnly = group.totalPoints === 0 && group.requiresReviewCount > 0;
              return (
                <TableRow key={group.collaboratorId}>
                  <TableCell className="font-medium text-slate-900">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={group.collaboratorName} size="md" />
                      <button
                        type="button"
                        className="text-left underline decoration-dotted underline-offset-2 hover:text-blue-700"
                        onClick={() => setHistoryCollaboratorId(group.collaboratorId)}
                        title="Detalhar todas as garantias deste colaborador"
                      >
                        {group.collaboratorName}
                      </button>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-slate-700">
                    {group.warrantyCount} O.S de garantia
                    {group.requiresReviewCount > 0 ? (
                      <span className="ml-1 text-xs text-violet-700">· {group.requiresReviewCount} em revisão</span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <div className={isReviewOnly ? "font-medium text-violet-700" : "font-semibold text-red-600"}>
                      {isReviewOnly ? "Valor a definir" : formatSignedPoints(group.totalPoints)}
                    </div>
                    {!isReviewOnly && group.totalPoints !== 0 ? (
                      <div className="mt-1.5 h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full ${severityPct > 60 ? "bg-red-500" : severityPct > 25 ? "bg-orange-400" : "bg-amber-300"}`}
                          style={{ width: `${severityPct}%` }}
                        />
                      </div>
                    ) : null}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm text-slate-500">
                    <span className="inline-flex items-center gap-1">
                      <Clock3 className="h-3.5 w-3.5 text-slate-400" />
                      {formatDateTime(group.lastDetectedAt)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="outline" size="sm" className="h-8 px-3" onClick={() => setHistoryCollaboratorId(group.collaboratorId)}>
                      Detalhar
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {!loading && filteredGroups.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                  <div className="flex flex-col items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                    {search.trim() || statusFilter === "review"
                      ? "Nenhum colaborador encontrado para o filtro atual."
                      : isPaidPeriod
                        ? "Nenhum débito de garantia foi descontado neste período."
                        : "Nenhum débito de garantia pendente neste período."}
                  </div>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      <CollaboratorBalanceHistorySheet
        collaboratorId={historyCollaboratorId}
        open={historyCollaboratorId !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setHistoryCollaboratorId(null);
        }}
        isAdmin={isAdmin}
        onChanged={() => void load()}
      />
    </div>
  );
}
