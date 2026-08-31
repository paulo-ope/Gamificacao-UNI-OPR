"use client";

import { AlertTriangle, CheckCircle2, Info, Loader2, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { StructureAudit, StructureAuditFinding, StructureAuditSeverity } from "@/lib/types";

// Auditoria da Estrutura Operacional Confiável (pedido do usuário em 2026-08-29) - fase
// preparatória antes de "capacidade regional automática". Só leitura: esta tela nunca altera
// nenhum dado, só mostra o que precisa de atenção antes de avançar.

const TYPE_LABELS: Record<string, string> = {
  collaborator_without_ixc_id: "Sem vínculo com o IXC",
  collaborator_without_cpf: "Sem CPF local",
  collaborator_without_team_type: "Sem tipo de equipe",
  collaborator_without_supervisor: "Sem supervisor",
  responsible_without_collaborator: "Responsável sem colaborador",
  responsible_multi_regional: "Produção em mais de uma regional",
  collaborator_regional_diverges_from_orders: "Regional divergente da produção",
  member_without_team_model: "Sem modelo de equipe",
  team_model_inactive_still_used: "Modelo de equipe inativo em uso",
  regional_without_branch_capacity: "Regional sem capacidade configurada",
  branch_capacity_invalid_thresholds: "Capacidade com limiares inválidos",
  member_pending_validation: "Pendente de validação",
  recent_production_pending_structure: "Produção recente com estrutura pendente",
};

const SEVERITY_ORDER: StructureAuditSeverity[] = ["critico", "atencao", "informativo"];

const SEVERITY_STYLES: Record<StructureAuditSeverity, { label: string; badge: string; icon: typeof ShieldAlert; card: string; iconColor: string }> = {
  critico: { label: "Crítico", badge: "bg-rose-50 text-rose-700", icon: ShieldAlert, card: "border-rose-200 bg-rose-50/40", iconColor: "text-rose-600" },
  atencao: { label: "Atenção", badge: "bg-amber-50 text-amber-700", icon: AlertTriangle, card: "border-amber-200 bg-amber-50/40", iconColor: "text-amber-600" },
  informativo: { label: "Informativo", badge: "bg-blue-50 text-blue-700", icon: Info, card: "border-blue-200 bg-blue-50/40", iconColor: "text-blue-600" },
};

function typeLabel(type: string): string {
  return TYPE_LABELS[type] || type;
}

export function StructureAuditPanel() {
  const [audit, setAudit] = useState<StructureAudit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [regionalFilter, setRegionalFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAudit(await api.managementStructureAudit());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar a auditoria da estrutura.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const regionals = useMemo(() => {
    if (!audit) return [];
    return Array.from(new Set(audit.findings.map((item) => item.regional).filter((item): item is string => Boolean(item)))).sort((left, right) =>
      left.localeCompare(right, "pt-BR")
    );
  }, [audit]);

  const types = useMemo(() => {
    if (!audit) return [];
    return Array.from(new Set(audit.findings.map((item) => item.type))).sort((left, right) => typeLabel(left).localeCompare(typeLabel(right), "pt-BR"));
  }, [audit]);

  const filteredFindings = useMemo(() => {
    if (!audit) return [];
    const term = search.trim().toLocaleLowerCase("pt-BR");
    return audit.findings.filter((item) => {
      if (severityFilter && item.severity !== severityFilter) return false;
      if (regionalFilter && item.regional !== regionalFilter) return false;
      if (typeFilter && item.type !== typeFilter) return false;
      if (!term) return true;
      return `${item.subject_name || ""} ${item.description} ${item.regional || ""}`.toLocaleLowerCase("pt-BR").includes(term);
    });
  }, [audit, severityFilter, regionalFilter, typeFilter, search]);

  return (
    <div className="grid gap-5">
      <StatusToast error={error} message={null} onDismissError={() => setError(null)} onDismissMessage={() => undefined} />

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-600">Auditoria estrutural</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">Estrutura Operacional Confiável</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Inconsistências entre Gamificação, Operação e Gestão que precisam ser resolvidas antes de avançar para capacidade regional automática. Leitura local, nenhum dado é alterado aqui.
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Atualizar
          </Button>
        </div>

        {audit ? (
          <div className="mt-5 grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-5">
            <div className="rounded-2xl bg-slate-50 px-3 py-3">
              <p className="text-lg font-bold text-slate-950">{audit.summary.total_collaborators}</p>
              <p className="text-slate-500">Colaboradores</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-3 py-3">
              <p className="text-lg font-bold text-slate-950">{audit.summary.collaborators_with_ixc_id}</p>
              <p className="text-slate-500">Com vínculo IXC</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-3 py-3">
              <p className="text-lg font-bold text-slate-950">{audit.summary.collaborators_with_cpf}</p>
              <p className="text-slate-500">Com CPF local</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-3 py-3">
              <p className="text-lg font-bold text-slate-950">{audit.summary.responsible_assignments}</p>
              <p className="text-slate-500">Responsáveis (Operação)</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-3 py-3">
              <p className="text-lg font-bold text-slate-950">{audit.summary.branch_capacity_rows}</p>
              <p className="text-slate-500">Regionais com capacidade</p>
            </div>
          </div>
        ) : null}
      </div>

      {loading && !audit ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-24 animate-pulse rounded-2xl border border-slate-200 bg-white" />
          ))}
        </div>
      ) : null}

      {audit ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {SEVERITY_ORDER.map((severity) => {
              const style = SEVERITY_STYLES[severity];
              const Icon = style.icon;
              const count = severity === "critico" ? audit.critical_count : severity === "atencao" ? audit.attention_count : audit.informative_count;
              const active = severityFilter === severity;
              return (
                <button
                  key={severity}
                  type="button"
                  onClick={() => setSeverityFilter(active ? "" : severity)}
                  className={cn(
                    "rounded-2xl border p-4 text-left transition",
                    style.card,
                    active ? "ring-2 ring-offset-1 ring-current" : "hover:shadow-sm"
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <Icon className={cn("h-5 w-5", style.iconColor)} aria-hidden="true" />
                    <span className="text-2xl font-bold text-slate-950">{count}</span>
                  </div>
                  <p className="mt-2 text-sm font-semibold text-slate-800">{style.label}</p>
                </button>
              );
            })}
          </div>

          {audit.total_findings > audit.findings.length ? (
            <p className="text-xs text-amber-700">
              Mostrando {audit.findings.length} de {audit.total_findings} achados - os contadores acima refletem o total real.
            </p>
          ) : null}

          <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-col gap-3 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
              <h3 className="text-lg font-semibold text-slate-950">Achados ({filteredFindings.length})</h3>
              <div className="flex flex-wrap gap-2">
                <Input
                  className="h-9 w-full sm:w-48"
                  placeholder="Buscar por nome/descrição"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <select
                  className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
                  value={severityFilter}
                  onChange={(event) => setSeverityFilter(event.target.value)}
                >
                  <option value="">Todas as severidades</option>
                  {SEVERITY_ORDER.map((severity) => (
                    <option key={severity} value={severity}>
                      {SEVERITY_STYLES[severity].label}
                    </option>
                  ))}
                </select>
                <select
                  className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
                  value={regionalFilter}
                  onChange={(event) => setRegionalFilter(event.target.value)}
                >
                  <option value="">Todas as regionais</option>
                  {regionals.map((regional) => (
                    <option key={regional} value={regional}>
                      {regional}
                    </option>
                  ))}
                </select>
                <select
                  className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700"
                  value={typeFilter}
                  onChange={(event) => setTypeFilter(event.target.value)}
                >
                  <option value="">Todos os tipos</option>
                  {types.map((type) => (
                    <option key={type} value={type}>
                      {typeLabel(type)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {filteredFindings.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-5 py-14 text-center">
                <CheckCircle2 className="h-8 w-8 text-emerald-500" aria-hidden="true" />
                <p className="text-sm font-medium text-slate-700">
                  {audit.findings.length === 0 ? "Nenhuma inconsistência encontrada." : "Nenhum achado para os filtros selecionados."}
                </p>
                <p className="text-xs text-slate-400">
                  {audit.findings.length === 0 ? "A estrutura operacional está consistente no recorte atual." : "Ajuste os filtros acima para ver outros achados."}
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto p-5">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Severidade</TableHead>
                      <TableHead>Tipo</TableHead>
                      <TableHead>Descrição</TableHead>
                      <TableHead>Regional</TableHead>
                      <TableHead>Responsável/Colaborador</TableHead>
                      <TableHead>Sugestão</TableHead>
                      <TableHead className="text-right">Bloqueia capacidade</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredFindings.slice(0, 500).map((finding, index) => (
                      <FindingRow key={`${finding.type}-${finding.entity_id ?? "-"}-${index}`} finding={finding} />
                    ))}
                  </TableBody>
                </Table>
                {filteredFindings.length > 500 ? (
                  <p className="mt-3 text-xs text-slate-400">
                    Mostrando as primeiras 500 linhas deste filtro ({filteredFindings.length} no total) - refine a busca ou os filtros acima para ver outras.
                  </p>
                ) : null}
              </div>
            )}
          </div>

          <p className="text-xs text-slate-400">Gerado em {new Date(audit.generated_at).toLocaleString("pt-BR")}.</p>
        </>
      ) : !loading ? (
        <div className="flex flex-col items-center gap-2 rounded-3xl border border-slate-200 bg-white px-5 py-14 text-center">
          <ShieldCheck className="h-8 w-8 text-slate-300" aria-hidden="true" />
          <p className="text-sm text-slate-500">Não foi possível carregar a auditoria agora.</p>
        </div>
      ) : null}
    </div>
  );
}

function FindingRow({ finding }: { finding: StructureAuditFinding }) {
  const style = SEVERITY_STYLES[finding.severity];
  return (
    <TableRow>
      <TableCell>
        <Badge className={style.badge}>{style.label}</Badge>
      </TableCell>
      <TableCell className="text-sm text-slate-600">{typeLabel(finding.type)}</TableCell>
      <TableCell className="max-w-sm text-sm text-slate-700">{finding.description}</TableCell>
      <TableCell className="text-sm text-slate-600">{finding.regional || "—"}</TableCell>
      <TableCell className="text-sm text-slate-600">{finding.subject_name || "—"}</TableCell>
      <TableCell className="max-w-xs text-xs text-slate-500">{finding.suggestion}</TableCell>
      <TableCell className="text-right">
        {finding.blocks_capacity ? (
          <Badge className="bg-rose-50 text-rose-700">Sim</Badge>
        ) : (
          <Badge className="bg-slate-100 text-slate-600">Não</Badge>
        )}
      </TableCell>
    </TableRow>
  );
}
