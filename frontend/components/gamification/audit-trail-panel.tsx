"use client";

import { AlertTriangle, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AuditLog } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = {
  run: "Recalculou o fechamento",
  update_status: "Alterou o status do fechamento",
  update: "Atualizou",
  create: "Criou",
  delete: "Excluiu",
  soft_delete: "Inativou",
  import: "Importou",
  reset_default: "Restaurou o padrão",
  point_balance_debit_created: "Gerou débito de garantia",
  point_balance_debit_applied: "Aplicou débito de garantia no pagamento",
  point_balance_carry_over: "Carregou saldo de garantia para o próximo mês",
  point_balance_debit_reverted: "Estornou débito de garantia",
  point_balance_manual_adjustment: "Lançou ajuste manual de saldo"
};

const ENTITY_LABEL: Record<string, string> = {
  calculation_runs: "Fechamento",
  collaborator_scores: "Pontuação de colaborador",
  app_settings: "Configuração",
  gamification_config: "Regras da gamificação",
  collaborators: "Colaborador",
  point_balance_entry: "Saldo de pontos",
  users: "Usuário"
};

function actionLabel(action: string) {
  return ACTION_LABEL[action] ?? action;
}

function actionBadgeClass(action: string) {
  if (action.includes("revert") || action === "delete" || action === "soft_delete") return "border-rose-200 bg-rose-50 text-rose-700";
  if (action.includes("applied") || action === "update_status") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (action.includes("debit") || action.includes("carry")) return "border-amber-200 bg-amber-50 text-amber-800";
  if (action === "run") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function statusNote(log: AuditLog) {
  // Frase legível para as mudanças mais comuns (status de fechamento).
  if (log.action === "update_status" && log.after_data && typeof log.after_data.status === "string") {
    const status = String(log.after_data.status);
    const labels: Record<string, string> = {
      review: "enviado para conferência",
      approved: "aprovado",
      paid: "marcado como PAGO",
      cancelled: "cancelado",
      draft: "rascunho"
    };
    return `→ ${labels[status] ?? status}`;
  }
  return null;
}

export function AuditTrailPanel() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [entityFilter, setEntityFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.auditLogs({
        search: search.trim() || undefined,
        entity: entityFilter || undefined,
        limit: 300
      });
      setLogs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar a trilha de auditoria.");
    } finally {
      setLoading(false);
    }
  }, [search, entityFilter]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const entityOptions = useMemo(() => Object.entries(ENTITY_LABEL), []);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-blue-700" />
          <h3 className="text-sm font-semibold text-slate-950">Trilha de ações (quem fez o quê, quando)</h3>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
      </div>

      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por ação, entidade ou ID..." className="pl-9" />
        </div>
        <select
          className="h-10 rounded-md border border-input bg-white px-3 text-sm"
          value={entityFilter}
          onChange={(event) => setEntityFilter(event.target.value)}
        >
          <option value="">Todas as áreas</option>
          {entityOptions.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
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
              <TableHead>Quando</TableHead>
              <TableHead>Quem</TableHead>
              <TableHead>Ação</TableHead>
              <TableHead>Onde</TableHead>
              <TableHead>Detalhe</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.map((log) => (
              <TableRow key={log.id}>
                <TableCell className="whitespace-nowrap text-sm text-slate-600">{formatDateTime(log.created_at)}</TableCell>
                <TableCell className="text-sm font-medium text-slate-900">{log.user_name ?? "Sistema"}</TableCell>
                <TableCell>
                  <Badge className={actionBadgeClass(log.action)}>{actionLabel(log.action)}</Badge>
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-slate-600">
                  {ENTITY_LABEL[log.entity] ?? log.entity}
                  {log.entity_id ? <span className="ml-1 text-xs text-slate-400">#{log.entity_id}</span> : null}
                </TableCell>
                <TableCell className="max-w-md text-sm text-slate-500">
                  {statusNote(log) ?? (log.after_data?.note ? String(log.after_data.note) : "-")}
                </TableCell>
              </TableRow>
            ))}
            {!loading && logs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                  Nenhum registro de auditoria para os filtros atuais.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
