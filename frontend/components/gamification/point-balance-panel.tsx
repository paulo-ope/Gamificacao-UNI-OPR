"use client";

import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Avatar, MetricCard } from "@/components/gamification/config-ui";
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

type BucketConfig = {
  bucket: PointBalanceEntry["bucket"];
  title: string;
  description: string;
  emptyLabel: string;
  countLabel: string;
  pointsLabel: string;
  // Quando a soma do grupo e positiva, o rotulo/tom padrao (pensado pra divida) fica ao contrario
  // do que esta acontecendo - isso e real, nao um bug: um estorno de debito invalido (ex.: saude
  // ja zerava o pagamento na origem) pode deixar so o credito de compensacao de pe, sem duvida
  // nenhuma pareada. Ver correcao de 2026-08-05.
  positivePointsLabel: string;
  tone: "danger" | "warning" | "neutral";
};

const BUCKET_CONFIG: BucketConfig[] = [
  {
    bucket: "eligible_pending",
    title: "Vai descontar neste fechamento",
    description: "Pendente e com alvo neste mês (ou anterior) - seria descontado se este fechamento fosse marcado como pago agora.",
    emptyLabel: "Nenhum débito vai ser descontado neste fechamento.",
    countLabel: "Colaboradores a descontar",
    pointsLabel: "Pontos a descontar",
    positivePointsLabel: "Pontos a favor do colaborador",
    tone: "danger"
  },
  {
    bucket: "applied",
    title: "Já descontado",
    description: "Débitos que já foram efetivamente consumidos por este fechamento (só existe depois que ele é marcado como pago).",
    emptyLabel: "Nenhum débito foi descontado deste fechamento ainda.",
    countLabel: "Colaboradores descontados",
    pointsLabel: "Pontos descontados",
    positivePointsLabel: "Pontos a favor do colaborador",
    tone: "neutral"
  },
  {
    bucket: "deferred_pending",
    title: "Pendente para mês futuro",
    description: "Pendente, mas com alvo num mês posterior a este - não tem relação com este fechamento, só aparece pra você saber que ainda existe.",
    emptyLabel: "Nenhum débito pendente para um mês futuro.",
    countLabel: "Colaboradores com pendência futura",
    pointsLabel: "Pontos pendentes (mês futuro)",
    positivePointsLabel: "Crédito pendente (mês futuro)",
    tone: "warning"
  }
];

function groupByCollaborator(entries: PointBalanceEntry[]): CollaboratorGroup[] {
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
}

function BucketSection({
  config,
  groups,
  onOpenHistory
}: {
  config: BucketConfig;
  groups: CollaboratorGroup[];
  onOpenHistory: (collaboratorId: number) => void;
}) {
  const totalPoints = groups.reduce((total, group) => total + group.totalPoints, 0);
  const requiresReviewCount = groups.reduce((total, group) => total + group.requiresReviewCount, 0);
  const maxDebt = Math.max(1, ...groups.map((group) => Math.abs(group.totalPoints)));

  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <h4 className="text-sm font-semibold text-slate-950">{config.title}</h4>
        <InfoHint ariaLabel={`Ajuda sobre ${config.title}`} description={config.description} />
        <span className="text-xs text-slate-400">({groups.length})</span>
      </div>

      {groups.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <MetricCard title={config.countLabel} value={groups.length} />
          <MetricCard
            title={totalPoints > 0 ? config.positivePointsLabel : config.pointsLabel}
            value={formatSignedPoints(totalPoints)}
            tone={totalPoints > 0 ? "success" : config.tone}
          />
          {requiresReviewCount > 0 ? <MetricCard title="Aguardando revisão manual" value={requiresReviewCount} tone="warning" /> : null}
        </div>
      ) : null}

      <div className="table-frame overflow-hidden rounded-[20px] border border-slate-200 bg-white">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
            <TableRow className="border-slate-700 hover:bg-slate-900">
              <TableHead>Colaborador</TableHead>
              <TableHead>Garantias</TableHead>
              <TableHead>Impacto no pagamento</TableHead>
              <TableHead>Última detecção</TableHead>
              <TableHead className="text-right">Auditar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups.map((group) => {
              const severityPct = Math.min(100, Math.round((Math.abs(group.totalPoints) / maxDebt) * 100));
              const isReviewOnly = group.totalPoints === 0 && group.requiresReviewCount > 0;
              return (
                <TableRow key={group.collaboratorId}>
                  <TableCell className="font-medium text-slate-900">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={group.collaboratorName} size="md" />
                      <button
                        type="button"
                        className="text-left underline decoration-dotted underline-offset-2 hover:text-uni-royal"
                        onClick={() => onOpenHistory(group.collaboratorId)}
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
                    <Button type="button" variant="outline" size="sm" className="h-8 px-3" onClick={() => onOpenHistory(group.collaboratorId)}>
                      Detalhar
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {groups.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                  <div className="flex flex-col items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                    {config.emptyLabel}
                  </div>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function PointBalancePanel({ isAdmin, calculationRunId, referenceMonth, referenceYear }: Props) {
  const [entries, setEntries] = useState<PointBalanceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("severity");
  const [historyCollaboratorId, setHistoryCollaboratorId] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    // Guarda por id de requisicao (nao so um cancelled flag de useEffect): "Atualizar" manual,
    // o onChanged do CollaboratorBalanceHistorySheet e a troca automatica de periodo podem
    // disparar chamadas sobrepostas - sem isso, uma resposta antiga (periodo anterior) que
    // chega DEPOIS de uma mais recente sobrescreve a tela com o saldo do periodo errado.
    const requestId = ++requestIdRef.current;
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
      if (requestIdRef.current !== requestId) return;
      setEntries(data);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setError(err instanceof Error ? err.message : "Erro ao carregar o saldo de pontos.");
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [calculationRunId, referenceMonth, referenceYear]);

  useEffect(() => {
    void load();
  }, [load]);

  const filterAndSort = useCallback(
    (groups: CollaboratorGroup[]) => {
      const term = search.trim().toLowerCase();
      let list = groups;
      if (term) list = list.filter((group) => group.collaboratorName.toLowerCase().includes(term));
      if (statusFilter === "review") list = list.filter((group) => group.requiresReviewCount > 0);

      const sorted = [...list];
      if (sortMode === "severity") sorted.sort((a, b) => a.totalPoints - b.totalPoints);
      else if (sortMode === "name") sorted.sort((a, b) => a.collaboratorName.localeCompare(b.collaboratorName, "pt-BR"));
      else sorted.sort((a, b) => (b.lastDetectedAt ?? "").localeCompare(a.lastDetectedAt ?? ""));
      return sorted;
    },
    [search, statusFilter, sortMode]
  );

  const sectionsData = useMemo(
    () =>
      BUCKET_CONFIG.map((config) => ({
        config,
        groups: filterAndSort(groupByCollaborator(entries.filter((entry) => entry.bucket === config.bucket)))
      })),
    [entries, filterAndSort]
  );

  const totalRequiresReview = useMemo(
    () => entries.filter((entry) => entry.requires_review).length,
    [entries]
  );

  return (
    <div className="grid gap-4 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-950">Saldo de pontos</h3>
          <InfoHint
            ariaLabel="Ajuda sobre saldo de pontos"
            description="Separado em três grupos: o que vai ser descontado se este fechamento for pago agora, o que já foi de fato descontado (só depois de pago) e o que está pendente mas com alvo num mês futuro. Clique em Detalhar para auditar todas as O.S de garantia de um colaborador."
          />
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
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
              statusFilter === "all" ? "bg-uni-royal text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            Todos
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter("review")}
            className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              statusFilter === "review" ? "bg-uni-royal text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <ShieldAlert className="h-3 w-3" />
            Em revisão
            {totalRequiresReview > 0 ? (
              <span className={`ml-0.5 rounded-full px-1.5 text-[10px] ${statusFilter === "review" ? "bg-white/25" : "bg-blue-50 text-uni-royal"}`}>
                {totalRequiresReview}
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

      {sectionsData.map(({ config, groups }) => (
        <BucketSection key={config.bucket} config={config} groups={groups} onOpenHistory={setHistoryCollaboratorId} />
      ))}

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
