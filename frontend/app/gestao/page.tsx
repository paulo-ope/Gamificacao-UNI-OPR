"use client";

import Link from "next/link";
import { ArrowLeft, BriefcaseBusiness, CheckCircle2, ExternalLink, Loader2, LogOut, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ManagementCasesPanel } from "@/components/management/management-cases-panel";
import { ManagementReasonsPanel } from "@/components/management/management-reasons-panel";
import { NotificationBell } from "@/components/workspace/notification-bell";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { api } from "@/lib/api";
import type { ManagementDashboard, ManagementOperationalMember, ManagementOptions } from "@/lib/types";

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

function statusTone(status: string) {
  if (status === "active_management" || status === "validated_operation") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "conflict") return "border-red-200 bg-red-50 text-red-700";
  if (status === "outside_operation" || status === "inactive") return "border-slate-200 bg-slate-100 text-slate-600";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

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
  const [filters, setFilters] = useState({ search: "", regional: "", status: "", supervisor_user_id: "" });
  const [tab, setTab] = useState("structure");

  const canRead = Boolean(user?.permissions.includes("management:read"));
  const canManage = Boolean(user?.permissions.includes("management:manage_structure"));
  const canReview = Boolean(user?.permissions.includes("management:review"));
  const canJustify = Boolean(user?.permissions.includes("management:write_justification"));
  const canAdminReasons = Boolean(user?.permissions.includes("management:admin"));
  const regionals = useMemo(() => Array.from(new Set((data?.members ?? []).map((item) => item.regional))).sort(), [data]);

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

  async function updateMember(id: number, payload: { supervisor_user_id?: number | null; team_model_id?: number | null; status?: string }) {
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

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="structure">Estrutura operacional</TabsTrigger>
            <TabsTrigger value="cases">
              Casos de gestão
              {data?.summary.open_cases ? (
                <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-700">
                  {data.summary.open_cases}
                </span>
              ) : null}
            </TabsTrigger>
            {canAdminReasons ? <TabsTrigger value="reasons">Motivos de justificativa</TabsTrigger> : null}
          </TabsList>

          <TabsContent value="cases">
            <ManagementCasesPanel options={options} canReview={canReview} canJustify={canJustify} />
          </TabsContent>

          {canAdminReasons ? (
            <TabsContent value="reasons">
              <ManagementReasonsPanel />
            </TabsContent>
          ) : null}

          <TabsContent value="structure" className="grid gap-5">
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
          <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr_1fr_1fr_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
              <Input className="pl-9" placeholder="Buscar colaborador ou regional" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
            </div>
            <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={filters.regional} onChange={(event) => setFilters({ ...filters, regional: event.target.value })}>
              <option value="">Todas as regionais</option>
              {regionals.map((regional) => <option key={regional} value={regional}>{regional}</option>)}
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
          <div className="overflow-x-auto p-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Colaborador</TableHead>
                  <TableHead>Regional</TableHead>
                  <TableHead>Supervisor</TableHead>
                  <TableHead>Modelo</TableHead>
                  <TableHead>Gamificação</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Alertas</TableHead>
                  <TableHead className="text-right">Administração</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.members ?? []).map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    options={options}
                    canManage={canManage}
                    isSaving={savingId === member.id}
                    onUpdate={updateMember}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
          </TabsContent>
        </Tabs>
      </section>
    </main>
  );
}

function MemberRow({
  member,
  options,
  canManage,
  isSaving,
  onUpdate,
}: {
  member: ManagementOperationalMember;
  options: ManagementOptions;
  canManage: boolean;
  isSaving: boolean;
  onUpdate: (id: number, payload: { supervisor_user_id?: number | null; team_model_id?: number | null; status?: string }) => Promise<void>;
}) {
  return (
    <TableRow>
      <TableCell className="min-w-64">
        <div className="font-medium text-slate-950">{member.responsible_name}</div>
        <div className="mt-1 text-xs text-slate-500">IXC {member.ixc_employee_id ?? "sem ID"}{member.last_order_at ? ` | ultima O.S. ${new Date(member.last_order_at).toLocaleDateString("pt-BR")}` : ""}</div>
      </TableCell>
      <TableCell className="min-w-40 text-sm text-slate-600">{member.regional}</TableCell>
      <TableCell className="min-w-52">
        {canManage ? (
          <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" value={member.supervisor_user_id ?? ""} disabled={isSaving} onChange={(event) => void onUpdate(member.id, { supervisor_user_id: event.target.value ? Number(event.target.value) : null })}>
            <option value="">Sem supervisor</option>
            {options.supervisors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        ) : <span className="text-sm text-slate-600">{member.supervisor_name ?? "Sem supervisor"}</span>}
      </TableCell>
      <TableCell className="min-w-52">
        {canManage ? (
          <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" value={member.team_model_id ?? ""} disabled={isSaving} onChange={(event) => void onUpdate(member.id, { team_model_id: event.target.value ? Number(event.target.value) : null })}>
            <option value="">Sem modelo</option>
            {options.team_models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        ) : <span className="text-sm text-slate-600">{member.team_model_name ?? "Sem modelo"}</span>}
      </TableCell>
      <TableCell>
        <div className="grid gap-1.5">
          <Badge className={member.gamification_status === "registered" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}>
            {gamificationLabels[member.gamification_status] ?? member.gamification_status}
          </Badge>
          {member.collaborator_team_type ? (
            <span className="text-xs text-slate-500">{teamTypeLabels[member.collaborator_team_type] ?? member.collaborator_team_type}</span>
          ) : null}
        </div>
      </TableCell>
      <TableCell>
        {canManage ? (
          <select className={`h-9 rounded-md border px-2 text-sm ${statusTone(member.status)}`} value={member.status} disabled={isSaving} onChange={(event) => void onUpdate(member.id, { status: event.target.value })}>
            {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        ) : <Badge className={statusTone(member.status)}>{statusLabels[member.status] ?? member.status}</Badge>}
      </TableCell>
      <TableCell className="min-w-72">
        <div className="flex flex-wrap gap-1.5">
          {member.collaborator_structure_status && member.collaborator_structure_status !== "validated" ? (
            <Badge className="border-blue-200 bg-blue-50 text-blue-700">
              {structureStatusLabels[member.collaborator_structure_status] ?? member.collaborator_structure_status}
            </Badge>
          ) : null}
          {member.alerts.length ? member.alerts.slice(0, 3).map((alert) => (
            <Badge key={alert} className="border-amber-200 bg-amber-50 text-amber-700">{alert}</Badge>
          )) : (
            <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700"><CheckCircle2 className="mr-1 h-3.5 w-3.5" /> OK</Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="text-right">
        <Button type="button" size="sm" variant="outline" asChild>
          <Link href={`/admin?tab=structure&person=${encodeURIComponent(member.collaborator_name || member.responsible_name)}`}>
            <ExternalLink className="h-3.5 w-3.5" /> Corrigir
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  );
}
