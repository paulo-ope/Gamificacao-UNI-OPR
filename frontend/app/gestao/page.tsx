"use client";

import Link from "next/link";
import { ArrowLeft, BriefcaseBusiness, CheckCircle2, ExternalLink, Loader2, LogOut, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ManagementCaseDiagnosticsPanel, ManagementCasesPanel } from "@/components/management/management-cases-panel";
import { ManagementModuleSidebar, type ManagementTab } from "@/components/management/management-module-sidebar";
import { ManagementReasonsPanel } from "@/components/management/management-reasons-panel";
import { NotificationBell } from "@/components/workspace/notification-bell";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { api } from "@/lib/api";
import type { ManagementDashboard, ManagementOperationalMember, ManagementOptions, ManagementShiftPatternSuggestion } from "@/lib/types";

// Nome do modelo de equipe elegível pra escala alternada, espelhando
// ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES do backend (management/models.py) - só serve pra
// decidir se mostra o botão "Sugerir escala" aqui; quem valida de fato é o backend no PATCH.
const ALTERNATING_ELIGIBLE_TEAM_MODEL_NAME = "TECNICO 12/36H";

const statusLabels: Record<string, string> = {
  pending_validation: "Pendente",
  validated_operation: "Validado",
  outside_operation: "Fora da operação",
  without_supervisor: "Sem supervisor",
  without_team_model: "Sem modelo",
  active_management: "Ativo",
  conflict: "Conflito",
  inactive: "Inativo",
};

const gamificationLabels: Record<string, string> = {
  registered: "Cadastrado",
  pending: "Pendente",
  missing: "Não encontrado",
  inactive: "Inativo",
};

const structureStatusLabels: Record<string, string> = {
  pending_review: "Cadastro pendente",
  validated: "Cadastro validado",
  needs_fix: "Corrigir cadastro",
  outside_operation: "Fora da operação",
  inactive: "Inativo",
};

const teamTypeLabels: Record<string, string> = {
  field: "Campo",
  scheduling: "Agendamento",
  internal_support: "Suporte interno",
  regional: "Regional",
  administrative: "Administrativo",
  headquarters: "Matriz",
  other: "Outro",
};

// Consolida Gamificação + Status + Alertas numa única leitura de "Situação" - pedido do usuário
// em 2026-08-20 (a tela tinha 3 colunas separadas repetindo o mesmo tipo de sinal, e status como
// "sem supervisor"/"sem modelo" já é visível nas próprias colunas Supervisor/Modelo, então fica de
// fora daqui de propósito pra não duplicar). Prioridade: o pior sinal decide o badge principal;
// o resto vira detalhe no tooltip/lista secundária, não em colunas próprias.
type MemberSituation = {
  tone: "red" | "blue" | "amber" | "slate" | "emerald";
  label: string;
  detail: string[];
  needsCorrection: boolean;
};

function memberSituation(member: ManagementOperationalMember): MemberSituation {
  const detail: string[] = [];
  if (member.collaborator_structure_status && member.collaborator_structure_status !== "validated") {
    detail.push(structureStatusLabels[member.collaborator_structure_status] ?? member.collaborator_structure_status);
  }
  detail.push(...member.alerts);
  if (member.gamification_status !== "registered") {
    detail.push(`Gamificação: ${gamificationLabels[member.gamification_status] ?? member.gamification_status}`);
  }

  if (member.status === "conflict") {
    return { tone: "red", label: "Conflito", detail, needsCorrection: true };
  }
  if (member.collaborator_structure_status && member.collaborator_structure_status !== "validated") {
    return {
      tone: "blue",
      label: structureStatusLabels[member.collaborator_structure_status] ?? member.collaborator_structure_status,
      detail,
      needsCorrection: true,
    };
  }
  if (member.alerts.length) {
    return { tone: "amber", label: member.alerts.length === 1 ? member.alerts[0] : `${member.alerts.length} alertas`, detail, needsCorrection: true };
  }
  if (member.gamification_status !== "registered") {
    return { tone: "amber", label: gamificationLabels[member.gamification_status] ?? member.gamification_status, detail, needsCorrection: true };
  }
  if (member.status === "pending_validation") {
    return { tone: "amber", label: "Pendente", detail, needsCorrection: true };
  }
  if (member.status === "outside_operation" || member.status === "inactive") {
    return { tone: "slate", label: statusLabels[member.status] ?? member.status, detail, needsCorrection: false };
  }
  return { tone: "emerald", label: "OK", detail, needsCorrection: false };
}

const SITUATION_TONE_CLASS: Record<MemberSituation["tone"], string> = {
  red: "border-red-200 bg-red-50 text-red-700",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  slate: "border-slate-200 bg-slate-100 text-slate-600",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

function metricCards(data: ManagementDashboard | null) {
  const summary = data?.summary;
  return [
    ["Pendentes", summary?.pending_validation ?? 0, "Validação operacional"],
    ["Sem supervisor", summary?.without_supervisor ?? 0, "Vínculo de liderança"],
    ["Sem modelo", summary?.without_team_model ?? 0, "Meta/equipe indefinida"],
    ["Sem Gamificação", summary?.without_gamification ?? 0, "Cadastro ou registro pendente"],
    ["Conflitos", summary?.conflicts ?? 0, "Revisão da matriz"],
  ];
}

export default function ManagementPage() {
  const { user, checking, error: authError, login, logout } = useWorkspaceAuth();
  const [data, setData] = useState<ManagementDashboard | null>(null);
  const [options, setOptions] = useState<ManagementOptions>({ supervisors: [], team_models: [] });
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ search: "", regional: "", status: "", supervisor_user_id: "", collaborator_regional: "" });
  const [tab, setTab] = useState<ManagementTab>("structure");
  // Ação em massa sobre colaboradores selecionados - pedido do usuário em 2026-08-21: antes só
  // dava pra aplicar escala 12x36 em lote; modelo de equipe e supervisor (ex.: um time inteiro em
  // horário comercial) precisavam ser configurados um por um. Um único seletor de ação (em vez de
  // três barras separadas) decide qual campo o valor abaixo alimenta.
  const [selectedMemberIds, setSelectedMemberIds] = useState<Set<number>>(new Set());
  const [bulkAction, setBulkAction] = useState<"team_model" | "supervisor" | "shift">("team_model");
  const [bulkTeamModelId, setBulkTeamModelId] = useState("");
  const [bulkSupervisorId, setBulkSupervisorId] = useState("");
  const [bulkShiftAnchor, setBulkShiftAnchor] = useState("");
  const [applyingBulkAction, setApplyingBulkAction] = useState(false);

  const canRead = Boolean(user?.permissions.includes("management:read"));
  const canManage = Boolean(user?.permissions.includes("management:manage_structure"));
  const canReview = Boolean(user?.permissions.includes("management:review"));
  const canGenerate = Boolean(user?.permissions.includes("management:generate_cases"));
  const canJustify = Boolean(user?.permissions.includes("management:write_justification"));
  const canClaim = Boolean(user?.permissions.includes("management:claim_member"));
  const canAdminReasons = Boolean(user?.permissions.includes("management:admin"));
  const regionals = useMemo(() => Array.from(new Set((data?.members ?? []).map((item) => item.regional))).sort(), [data]);
  // "Regional de origem" (Collaborator.regional) - lista separada da regional operacional acima,
  // pra responder "quantos colaboradores temos na Regional X" sem contar quem só atendeu lá
  // ocasionalmente (ver visible_member_filters no backend).
  const originRegionals = useMemo(
    () => Array.from(new Set((data?.members ?? []).map((item) => item.collaborator_regional).filter((value): value is string => Boolean(value)))).sort(),
    [data]
  );

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const supervisorId = filters.supervisor_user_id ? Number(filters.supervisor_user_id) : undefined;
      const [nextData, nextOptions] = await Promise.all([
        api.managementDashboard({
          search: filters.search || undefined,
          regional: filters.regional || undefined,
          status: filters.status || undefined,
          supervisor_user_id: supervisorId,
          collaborator_regional: filters.collaborator_regional || undefined,
        }),
        api.managementOptions(),
      ]);
      setData(nextData);
      setOptions(nextOptions);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "Não foi possível carregar a gestão.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user && canRead) void load();
  }, [user, canRead]);

  async function refreshStructure() {
    setMessage(null);
    setError(null);
    setLoading(true);
    try {
      const result = await api.refreshManagementStructure();
      setMessage(`${result.created_candidates} novo(s) candidato(s) encontrados.`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar estrutura.");
    } finally {
      setLoading(false);
    }
  }

  async function updateMember(
    id: number,
    payload: {
      supervisor_user_id?: number | null;
      team_model_id?: number | null;
      status?: string;
      shift_pattern?: "standard" | "alternating" | null;
      shift_cycle_days_on?: number | null;
      shift_cycle_days_off?: number | null;
      shift_anchor_date?: string | null;
    }
  ) {
    setSavingId(id);
    setMessage(null);
    setError(null);
    try {
      await api.updateManagementMember(id, payload);
      await load();
      setMessage("Vínculo atualizado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar o vínculo.");
    } finally {
      setSavingId(null);
    }
  }

  async function claimMember(id: number) {
    setSavingId(id);
    setMessage(null);
    setError(null);
    try {
      await api.claimManagementMember(id);
      await load();
      setMessage("Colaborador adicionado à sua base.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível reivindicar este colaborador.");
    } finally {
      setSavingId(null);
    }
  }

  function toggleMemberSelected(id: number) {
    setSelectedMemberIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllVisibleMembers() {
    const visibleIds = (data?.members ?? []).map((item) => item.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedMemberIds.has(id));
    setSelectedMemberIds(allSelected ? new Set() : new Set(visibleIds));
  }

  function bulkActionIsReady() {
    if (!selectedMemberIds.size) return false;
    if (bulkAction === "team_model") return Boolean(bulkTeamModelId);
    if (bulkAction === "supervisor") return Boolean(bulkSupervisorId);
    return Boolean(bulkShiftAnchor);
  }

  async function applyBulkAction() {
    if (!bulkActionIsReady()) return;
    setApplyingBulkAction(true);
    setMessage(null);
    setError(null);
    try {
      const payload =
        bulkAction === "team_model"
          ? { team_model_id: Number(bulkTeamModelId) }
          : bulkAction === "supervisor"
            ? { supervisor_user_id: Number(bulkSupervisorId) }
            : { shift_pattern: "alternating" as const, shift_cycle_days_on: 1, shift_cycle_days_off: 1, shift_anchor_date: bulkShiftAnchor };
      await Promise.all(Array.from(selectedMemberIds).map((id) => api.updateManagementMember(id, payload)));
      const actionLabel = bulkAction === "team_model" ? "Modelo de equipe" : bulkAction === "supervisor" ? "Supervisor" : "Escala 12x36";
      setMessage(`${actionLabel} aplicado a ${selectedMemberIds.size} colaborador(es).`);
      setSelectedMemberIds(new Set());
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao aplicar a ação em lote.");
    } finally {
      setApplyingBulkAction(false);
    }
  }

  if (checking && !user) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando Gestão...</main>;
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />;

  if (!canRead) {
    return (
      <main className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <h1 className="text-xl font-semibold">Acesso de gestão necessário</h1>
          <p className="mt-2 text-sm">Seu usuário não possui permissão management:read.</p>
          <Link href="/" className="mt-4 inline-flex text-sm font-semibold text-amber-800">Voltar ao ecossistema</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <ManagementModuleSidebar
              activeTab={tab}
              canAdminReasons={canAdminReasons}
              openCasesCount={data?.summary.open_cases ?? 0}
              onChange={setTab}
            />
            <Link href="/" className="rounded-xl border border-slate-200 p-2 text-slate-500 hover:bg-slate-50">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">UNI Workspace</p>
              <h1 className="text-base font-semibold text-slate-950">Gestão Integrada</h1>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <Button type="button" variant="ghost" onClick={logout}><LogOut className="h-4 w-4" /> Sair</Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6">
        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-center">
          <div>
            <div className="flex items-center gap-2 text-blue-700">
              <BriefcaseBusiness className="h-5 w-5" />
              <p className="text-[10px] font-bold uppercase tracking-[0.22em]">Controle da matriz</p>
            </div>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">
              {tab === "structure" ? "Estrutura operacional e pendências" : "Casos de gestão e justificativas"}
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              {tab === "structure"
                ? "Valide quem pertence à Operação, vincule supervisor e modelo de equipe, e acompanhe riscos antes de cobrar metas ou justificativas."
                : "Acompanhe os desvios de meta abertos como caso formal, cobre a justificativa do supervisor e registre a decisão da matriz."}
            </p>
          </div>
          {canManage && tab === "structure" ? (
            <Button type="button" onClick={() => void refreshStructure()} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Atualizar estrutura
            </Button>
          ) : null}
        </div>

        <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />
        {loadError ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{loadError}</div> : null}

        {tab === "cases" ? (
          <ManagementCasesPanel
            options={options}
            canReview={canReview}
            canGenerate={canGenerate}
            canJustify={canJustify}
            canAdmin={canAdminReasons}
          />
        ) : null}

        {tab === "diagnostics" ? <ManagementCaseDiagnosticsPanel /> : null}

        {tab === "reasons" && canAdminReasons ? <ManagementReasonsPanel /> : null}

        {tab === "structure" ? (
          <div className="grid gap-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {metricCards(data).map(([label, value, hint]) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-medium text-slate-500">{label}</p>
              <p className="mt-2 text-3xl font-semibold text-slate-950">{value}</p>
              <p className="mt-1 text-xs text-slate-400">{hint}</p>
            </div>
          ))}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr_1fr_1fr_1fr_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
              <Input className="pl-9" placeholder="Buscar colaborador ou regional" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
            </div>
            <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={filters.regional} onChange={(event) => setFilters({ ...filters, regional: event.target.value })}>
              <option value="">Todas as regionais (operacional)</option>
              {regionals.map((regional) => <option key={regional} value={regional}>{regional}</option>)}
            </select>
            <select
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
              value={filters.collaborator_regional}
              onChange={(event) => setFilters({ ...filters, collaborator_regional: event.target.value })}
              title="Filtra pela regional de origem do colaborador (Collaborator.regional), não pela regional onde ele produziu"
            >
              <option value="">Todas as regionais (origem)</option>
              {originRegionals.map((regional) => <option key={regional} value={regional}>{regional}</option>)}
            </select>
            <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={filters.supervisor_user_id} onChange={(event) => setFilters({ ...filters, supervisor_user_id: event.target.value })}>
              <option value="">Todos os supervisores</option>
              {options.supervisors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
              <option value="">Todos os status</option>
              {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <Button type="button" variant="outline" onClick={() => void load()} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Filtrar
            </Button>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
            <div>
              <h3 className="text-base font-semibold text-slate-950">Estrutura operacional</h3>
              <p className="text-sm text-slate-500">{data?.members.length ?? 0} colaborador(es) no recorte atual.</p>
            </div>
            <Badge className="border-blue-200 bg-blue-50 text-blue-700"><ShieldAlert className="mr-1 h-3.5 w-3.5" /> Governanca</Badge>
          </div>
          {canManage && selectedMemberIds.size > 0 ? (
            <div className="flex flex-wrap items-center gap-2 border-b border-violet-200 bg-violet-50/60 px-4 py-2.5 text-sm">
              <span className="font-medium text-slate-700">{selectedMemberIds.size} colaborador(es) selecionado(s)</span>
              <select
                className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
                value={bulkAction}
                onChange={(event) => setBulkAction(event.target.value as typeof bulkAction)}
              >
                <option value="team_model">Aplicar modelo de equipe</option>
                <option value="supervisor">Aplicar supervisor</option>
                <option value="shift">Aplicar escala 12x36</option>
              </select>
              {bulkAction === "team_model" ? (
                <select
                  className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
                  value={bulkTeamModelId}
                  onChange={(event) => setBulkTeamModelId(event.target.value)}
                >
                  <option value="">Selecione o modelo</option>
                  {options.team_models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              ) : bulkAction === "supervisor" ? (
                <select
                  className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
                  value={bulkSupervisorId}
                  onChange={(event) => setBulkSupervisorId(event.target.value)}
                >
                  <option value="">Selecione o supervisor</option>
                  {options.supervisors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              ) : (
                <>
                  <span className="text-xs text-slate-500">1 dia sim, 1 não - todos com a MESMA data-âncora:</span>
                  <input
                    type="date"
                    className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
                    value={bulkShiftAnchor}
                    onChange={(event) => setBulkShiftAnchor(event.target.value)}
                  />
                </>
              )}
              <Button type="button" size="sm" disabled={applyingBulkAction || !bulkActionIsReady()} onClick={() => void applyBulkAction()}>
                {applyingBulkAction ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                Aplicar aos selecionados
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setSelectedMemberIds(new Set())}>
                Limpar seleção
              </Button>
            </div>
          ) : null}
          <div className="overflow-x-auto p-4">
            <Table>
              <TableHeader>
                <TableRow>
                  {canManage ? (
                    <TableHead className="w-8">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-slate-300"
                        aria-label="Selecionar todos os colaboradores visíveis"
                        checked={Boolean(data?.members.length) && data!.members.every((item) => selectedMemberIds.has(item.id))}
                        onChange={toggleSelectAllVisibleMembers}
                      />
                    </TableHead>
                  ) : null}
                  <TableHead>Colaborador</TableHead>
                  <TableHead>Regional</TableHead>
                  <TableHead>Supervisor</TableHead>
                  <TableHead>Modelo</TableHead>
                  <TableHead>Escala</TableHead>
                  <TableHead>Situação</TableHead>
                  <TableHead className="text-right">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.members ?? []).map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    options={options}
                    canManage={canManage}
                    canClaim={canClaim}
                    isSaving={savingId === member.id}
                    onUpdate={updateMember}
                    onClaim={claimMember}
                    selected={selectedMemberIds.has(member.id)}
                    onToggleSelected={toggleMemberSelected}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function MemberRow({
  member,
  options,
  canManage,
  canClaim,
  isSaving,
  onUpdate,
  onClaim,
  selected,
  onToggleSelected,
}: {
  member: ManagementOperationalMember;
  options: ManagementOptions;
  canManage: boolean;
  // Separado de canManage de propósito: reivindicar (management:claim_member) é uma ação bem
  // mais estreita que administrar a estrutura inteira (management:manage_structure) - pedido do
  // usuário em 2026-08-20, pra supervisor/gerente de base montar a própria base sem depender da
  // matriz, sem ganhar o poder de reatribuir qualquer colaborador de qualquer supervisor.
  canClaim: boolean;
  isSaving: boolean;
  // Seleção pra aplicar escala 12x36 em lote (ver applyShiftPatternToSelected) - pedido do
  // usuário em 2026-08-21, configurar um por um era lento pra um time inteiro.
  selected: boolean;
  onToggleSelected: (id: number) => void;
  onUpdate: (
    id: number,
    payload: {
      supervisor_user_id?: number | null;
      team_model_id?: number | null;
      status?: string;
      shift_pattern?: "standard" | "alternating" | null;
      shift_cycle_days_on?: number | null;
      shift_cycle_days_off?: number | null;
      shift_anchor_date?: string | null;
    }
  ) => Promise<void>;
  onClaim: (id: number) => Promise<void>;
}) {
  const situation = memberSituation(member);
  // Sugestão de escala 12x36 a partir da produção real - pedido do usuário em 2026-08-21
  // ("sistema sugere, supervisor confirma"): só preenche o formulário quando o supervisor clica em
  // "Aplicar sugestão"; buscar a sugestão nunca salva nada por conta própria.
  const [shiftSuggestion, setShiftSuggestion] = useState<ManagementShiftPatternSuggestion | null>(null);
  const [suggestingShift, setSuggestingShift] = useState(false);
  const [shiftSuggestionError, setShiftSuggestionError] = useState<string | null>(null);

  const requestShiftSuggestion = async () => {
    setSuggestingShift(true);
    setShiftSuggestionError(null);
    try {
      const result = await api.suggestManagementMemberShiftPattern(member.id);
      setShiftSuggestion(result);
    } catch (error) {
      setShiftSuggestionError(error instanceof Error ? error.message : "Não foi possível calcular a sugestão.");
    } finally {
      setSuggestingShift(false);
    }
  };

  const applyShiftSuggestion = async () => {
    if (!shiftSuggestion || shiftSuggestion.suggested_pattern !== "alternating") return;
    await onUpdate(member.id, {
      shift_pattern: "alternating",
      shift_cycle_days_on: shiftSuggestion.suggested_cycle_days_on,
      shift_cycle_days_off: shiftSuggestion.suggested_cycle_days_off,
      shift_anchor_date: shiftSuggestion.suggested_anchor_date,
    });
    setShiftSuggestion(null);
  };

  return (
    <TableRow>
      {canManage ? (
        <TableCell>
          <input
            type="checkbox"
            className="h-3.5 w-3.5 rounded border-slate-300"
            aria-label={`Selecionar ${member.responsible_name}`}
            checked={selected}
            onChange={() => onToggleSelected(member.id)}
          />
        </TableCell>
      ) : null}
      <TableCell className="min-w-64">
        <div className="font-medium text-slate-950">{member.responsible_name}</div>
        <div className="mt-1 text-xs text-slate-500">IXC {member.ixc_employee_id ?? "sem ID"}{member.last_order_at ? ` | ultima O.S. ${new Date(member.last_order_at).toLocaleDateString("pt-BR")}` : ""}</div>
      </TableCell>
      <TableCell className="min-w-40 text-sm text-slate-600">
        {member.regional}
        {member.collaborator_regional && member.collaborator_regional !== member.regional ? (
          <div className="mt-0.5 text-xs text-slate-400" title="Regional de origem do colaborador (Collaborator.regional) - diferente de onde ele produziu neste registro">
            Origem: {member.collaborator_regional}
          </div>
        ) : null}
      </TableCell>
      <TableCell className="min-w-52">
        {canManage ? (
          <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" value={member.supervisor_user_id ?? ""} disabled={isSaving} onChange={(event) => void onUpdate(member.id, { supervisor_user_id: event.target.value ? Number(event.target.value) : null })}>
            <option value="">Sem supervisor</option>
            {options.supervisors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        ) : canClaim && !member.supervisor_user_id ? (
          <Button type="button" size="sm" variant="outline" disabled={isSaving} onClick={() => void onClaim(member.id)}>
            {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            Reivindicar para minha base
          </Button>
        ) : (
          <span className="text-sm text-slate-600">{member.supervisor_name ?? "Sem supervisor"}</span>
        )}
      </TableCell>
      <TableCell className="min-w-52">
        {canManage ? (
          <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" value={member.team_model_id ?? ""} disabled={isSaving} onChange={(event) => void onUpdate(member.id, { team_model_id: event.target.value ? Number(event.target.value) : null })}>
            <option value="">Sem modelo</option>
            {options.team_models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        ) : <span className="text-sm text-slate-600">{member.team_model_name ?? "Sem modelo"}</span>}
      </TableCell>
      <TableCell className="min-w-48">
        {canManage ? (
          <div className="grid gap-1.5">
            <select
              className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm"
              value={member.shift_pattern === "alternating" ? "alternating" : "standard"}
              disabled={isSaving}
              onChange={(event) =>
                void onUpdate(member.id, {
                  shift_pattern: event.target.value === "alternating" ? "alternating" : null,
                  shift_cycle_days_on: event.target.value === "alternating" ? 1 : null,
                  shift_cycle_days_off: event.target.value === "alternating" ? 1 : null,
                  shift_anchor_date: event.target.value === "alternating" ? (member.shift_anchor_date ?? new Date().toISOString().slice(0, 10)) : null,
                })
              }
            >
              <option value="standard">Padrão (seg-sex/sáb/dom)</option>
              <option value="alternating">12x36 (dia sim, dia não)</option>
            </select>
            {member.shift_pattern === "alternating" ? (
              <input
                type="date"
                className="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs"
                title="Um dia CONHECIDO de trabalho - o sistema calcula o ciclo a partir daqui."
                value={member.shift_anchor_date ?? ""}
                disabled={isSaving}
                onChange={(event) => void onUpdate(member.id, { shift_anchor_date: event.target.value || null })}
              />
            ) : null}
            {member.team_model_name === ALTERNATING_ELIGIBLE_TEAM_MODEL_NAME ? (
              <div className="grid gap-1">
                <Button type="button" size="sm" variant="outline" className="h-7 text-xs" disabled={isSaving || suggestingShift} onClick={() => void requestShiftSuggestion()}>
                  {suggestingShift ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                  Sugerir escala
                </Button>
                {shiftSuggestionError ? <span className="text-xs text-red-600">{shiftSuggestionError}</span> : null}
                {shiftSuggestion ? (
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600">
                    <p>{shiftSuggestion.message}</p>
                    <div className="mt-1.5 flex gap-1.5">
                      {shiftSuggestion.suggested_pattern === "alternating" ? (
                        <Button type="button" size="sm" className="h-6 text-xs" disabled={isSaving} onClick={() => void applyShiftSuggestion()}>
                          Aplicar sugestão
                        </Button>
                      ) : null}
                      <Button type="button" size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setShiftSuggestion(null)}>
                        Descartar
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : member.shift_pattern === "alternating" ? (
          <span className="text-sm text-slate-600">12x36 · âncora {member.shift_anchor_date ?? "—"}</span>
        ) : (
          <span className="text-sm text-slate-400">Padrão</span>
        )}
      </TableCell>
      <TableCell className="min-w-56">
        <div className="grid gap-1.5">
          <div className="flex items-center gap-1.5" title={situation.detail.join(" · ") || undefined}>
            <Badge className={SITUATION_TONE_CLASS[situation.tone]}>
              {situation.tone === "emerald" ? <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> : null}
              {situation.label}
            </Badge>
            {situation.detail.length > 1 ? (
              <span className="text-xs text-slate-400">+{situation.detail.length - 1}</span>
            ) : null}
          </div>
          {canManage ? (
            <select
              className="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-600"
              value={member.status}
              disabled={isSaving}
              onChange={(event) => void onUpdate(member.id, { status: event.target.value })}
            >
              {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          ) : null}
          {member.collaborator_team_type ? (
            <span className="text-xs text-slate-500">{teamTypeLabels[member.collaborator_team_type] ?? member.collaborator_team_type}</span>
          ) : null}
        </div>
      </TableCell>
      <TableCell className="text-right">
        {situation.needsCorrection ? (
          <Button type="button" size="sm" variant="outline" asChild>
            <Link href={`/admin?tab=structure&person=${encodeURIComponent(member.collaborator_name || member.responsible_name)}`}>
              <ExternalLink className="h-3.5 w-3.5" /> Corrigir
            </Link>
          </Button>
        ) : (
          <span className="text-xs text-slate-300">—</span>
        )}
      </TableCell>
    </TableRow>
  );
}
