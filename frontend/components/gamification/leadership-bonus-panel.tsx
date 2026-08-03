"use client";

import {
  BadgeCheck,
  BriefcaseBusiness,
  Building2,
  CircleAlert,
  Layers3,
  PenLine,
  Plus,
  ShieldCheck,
  Trash2,
  Users2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RegionalMultiSelect, uniqueRegionals } from "@/components/gamification/config-ui";
import { normalizeRegional, regionalName } from "@/lib/regional";
import { cn } from "@/lib/utils";
import type { LeadershipAverageSource, LeadershipProfile, LeadershipRoleProfile, LeadershipRoleType } from "@/lib/types";

type DraftRoleProfile = {
  id?: number;
  name: string;
  scope_type: LeadershipRoleType;
  default_multiplier: number;
  active: boolean;
};

type DraftLeader = {
  id?: number;
  name: string;
  role_type: LeadershipRoleType;
  role_profile_id: number | null;
  use_custom_multiplier: boolean;
  custom_multiplier: number | null;
  multiplier: number;
  average_source: LeadershipAverageSource;
  active: boolean;
  collaborator_id: number | null;
  regional_names: string[];
};

type Props = {
  roleProfiles: LeadershipRoleProfile[];
  profiles: LeadershipProfile[];
  regionalOptions: string[];
  readOnly?: boolean;
  onCreateRoleProfile: (payload: DraftRoleProfile) => Promise<void>;
  onSaveRoleProfile: (payload: LeadershipRoleProfile) => Promise<void>;
  onDeleteRoleProfile: (payload: LeadershipRoleProfile) => Promise<void>;
  onCreate: (payload: DraftLeader) => Promise<void>;
  onSave: (profile: LeadershipProfile) => Promise<void>;
  onDelete: (profile: LeadershipProfile) => Promise<void>;
};

const ROLE_SCOPE_LABELS: Record<LeadershipRoleType, string> = {
  supervisor: "Supervisor",
  regional_manager: "Gerente da unidade",
  portfolio_manager: "Gerente de pasta",
};

const ROLE_SCOPE_HINTS: Record<LeadershipRoleType, string> = {
  supervisor: "Usa a média dos pontos finais dos técnicos da base vinculada.",
  regional_manager: "Usa a média dos pontos finais da unidade ou base vinculada.",
  portfolio_manager: "Usa a média geral dos pontos finais da operação no período.",
};

const AVERAGE_SOURCE_LABELS: Record<LeadershipAverageSource, string> = {
  collaborators: "Colaboradores",
  collaborators_and_leaders: "Colaboradores + líderes",
};

const AVERAGE_SOURCE_HINTS: Record<LeadershipAverageSource, string> = {
  collaborators: "Média formada somente pelos colaboradores das filiais vinculadas.",
  collaborators_and_leaders: "Média formada pelos colaboradores e líderes ativos no mesmo escopo.",
};

const DEFAULT_MULTIPLIERS: Record<LeadershipRoleType, number> = {
  supervisor: 1.5,
  regional_manager: 2,
  portfolio_manager: 3,
};

function buildRoleDraft(): DraftRoleProfile {
  return {
    name: "",
    scope_type: "supervisor",
    default_multiplier: DEFAULT_MULTIPLIERS.supervisor,
    active: true,
  };
}

function buildLeaderDraft(): DraftLeader {
  return {
    name: "",
    role_type: "supervisor",
    role_profile_id: null,
    use_custom_multiplier: false,
    custom_multiplier: null,
    multiplier: DEFAULT_MULTIPLIERS.supervisor,
    average_source: "collaborators",
    active: true,
    collaborator_id: null,
    regional_names: [],
  };
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value);
}

function roleStatusBadge(active: boolean) {
  return active ? (
    <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Ativo</Badge>
  ) : (
    <Badge className="border-slate-200 bg-slate-100 text-slate-600">Inativo</Badge>
  );
}

function resolveRoleProfile(leader: LeadershipProfile, roleProfiles: LeadershipRoleProfile[]) {
  if (leader.role_profile_id) {
    return roleProfiles.find((item) => item.id === leader.role_profile_id) ?? null;
  }
  return roleProfiles.find((item) => item.scope_type === leader.role_type) ?? null;
}

function SummaryCard({
  icon,
  label,
  value,
  hint,
  accent = "default",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
  accent?: "default" | "highlight" | "warning";
}) {
  const accentClass =
    accent === "highlight"
      ? "text-uni-royal"
      : accent === "warning"
        ? "text-amber-700"
        : "text-slate-950";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        {icon}
        {label}
      </div>
      <div className={cn("mt-3 text-2xl font-semibold", accentClass)}>{value}</div>
      <div className="mt-1 text-sm text-slate-500">{hint}</div>
    </div>
  );
}

export function LeadershipBonusPanel({
  roleProfiles,
  profiles,
  regionalOptions,
  readOnly = false,
  onCreateRoleProfile,
  onSaveRoleProfile,
  onDeleteRoleProfile,
  onCreate,
  onSave,
  onDelete,
}: Props) {
  const [activeTab, setActiveTab] = useState("role-profiles");
  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
  const [leaderDrawerOpen, setLeaderDrawerOpen] = useState(false);
  const [roleDraft, setRoleDraft] = useState<DraftRoleProfile>(buildRoleDraft);
  const [leaderDraft, setLeaderDraft] = useState<DraftLeader>(buildLeaderDraft);
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);
  const [editingLeaderId, setEditingLeaderId] = useState<number | null>(null);

  const sortedRegionals = useMemo(
    () => uniqueRegionals(regionalOptions).sort((a, b) => regionalName(a).localeCompare(regionalName(b), "pt-BR")),
    [regionalOptions],
  );

  const activeLeaders = useMemo(() => profiles.filter((item) => item.active), [profiles]);
  // Gerente de pasta ignora as filiais vinculadas no cálculo (leadership_bonus.py:
  // validate_scope_regionals_required - "usa todos os colaboradores registrados"), então as
  // filiais que ele tem marcadas não representam cobertura real de liderança - contá-las aqui
  // fazia uma filial aparecer como "coberta" só porque um gerente de pasta (que já inclui todo
  // mundo de qualquer forma) tinha ela marcada, e mascarava filiais de fato sem responsável.
  const coveredRegionals = useMemo(
    () =>
      uniqueRegionals(
        activeLeaders.filter((item) => item.role_type !== "portfolio_manager").flatMap((item) => item.regional_names)
      ),
    [activeLeaders],
  );
  const uncoveredRegionals = useMemo(
    () => sortedRegionals.filter((regional) => !coveredRegionals.includes(regional)),
    [coveredRegionals, sortedRegionals],
  );
  const averageMultiplier = useMemo(() => {
    if (activeLeaders.length === 0) return 0;
    return activeLeaders.reduce((total, item) => total + item.multiplier, 0) / activeLeaders.length;
  }, [activeLeaders]);

  const branchCoverageRows = useMemo(
    () =>
      sortedRegionals.map((regional) => {
        // regional_names guarda o valor cru do banco (ex.: "UNI - SAO FRANCISCO DO GUAPORE"), sem
        // acento e sem a grafia bonita que regionalName() produz para regionais agrupadas (ex.:
        // "UNI - São Francisco do Guaporé") - comparar sem normalizar fazia essas filiais
        // aparecerem como "sem líder" mesmo com lideranca de fato vinculada.
        const owners = activeLeaders.filter((leader) =>
          leader.regional_names.some((name) => normalizeRegional(name) === regional)
        );
        return {
          regional,
          leaders: owners,
        };
      }),
    [activeLeaders, sortedRegionals],
  );

  const resetRoleDraft = () => {
    setRoleDraft(buildRoleDraft());
    setEditingRoleId(null);
  };

  const resetLeaderDraft = () => {
    setLeaderDraft(buildLeaderDraft());
    setEditingLeaderId(null);
  };

  const openRoleDrawer = (profile?: LeadershipRoleProfile) => {
    if (profile) {
      setRoleDraft({
        id: profile.id,
        name: profile.name,
        scope_type: profile.scope_type,
        default_multiplier: profile.default_multiplier,
        active: profile.active,
      });
      setEditingRoleId(profile.id);
    } else {
      resetRoleDraft();
    }
    setRoleDrawerOpen(true);
  };

  const openLeaderDrawer = (leader?: LeadershipProfile) => {
    if (leader) {
      setLeaderDraft({
        id: leader.id,
        name: leader.name,
        role_type: leader.role_type,
        role_profile_id: leader.role_profile_id ?? resolveRoleProfile(leader, roleProfiles)?.id ?? null,
        use_custom_multiplier: leader.use_custom_multiplier,
        custom_multiplier: leader.custom_multiplier,
        multiplier: leader.multiplier,
        average_source: leader.average_source ?? "collaborators",
        active: leader.active,
        collaborator_id: leader.collaborator_id,
        regional_names: uniqueRegionals(leader.regional_names),
      });
      setEditingLeaderId(leader.id);
    } else {
      resetLeaderDraft();
    }
    setLeaderDrawerOpen(true);
  };

  const selectedRoleProfile = useMemo(
    () => roleProfiles.find((item) => item.id === leaderDraft.role_profile_id) ?? null,
    [leaderDraft.role_profile_id, roleProfiles],
  );

  useEffect(() => {
    if (!selectedRoleProfile) return;
    setLeaderDraft((current) => ({
      ...current,
      role_type: selectedRoleProfile.scope_type,
      multiplier:
        current.use_custom_multiplier && current.custom_multiplier !== null
          ? current.custom_multiplier
          : selectedRoleProfile.default_multiplier,
    }));
  }, [selectedRoleProfile]);

  return (
    <section className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <SummaryCard
          icon={<Users2 className="h-4 w-4" />}
          label="Lideranças ativas"
          value={String(activeLeaders.length)}
          hint="Líderes habilitados no cálculo do período."
        />
        <SummaryCard
          icon={<BriefcaseBusiness className="h-4 w-4" />}
          label="Perfis configurados"
          value={String(roleProfiles.length)}
          hint="Perfis/cargos disponíveis para herança do multiplicador."
        />
        <SummaryCard
          icon={<Building2 className="h-4 w-4" />}
          label="Filiais cobertas"
          value={String(coveredRegionals.length)}
          hint="Filiais com pelo menos um líder ativo vinculado."
        />
        <SummaryCard
          icon={<CircleAlert className="h-4 w-4" />}
          label="Filiais sem líder"
          value={String(uncoveredRegionals.length)}
          hint="Bases sem responsável definido para liderança."
          accent={uncoveredRegionals.length > 0 ? "warning" : "default"}
        />
        <SummaryCard
          icon={<Layers3 className="h-4 w-4" />}
          label="Multiplicador médio"
          value={`${formatNumber(averageMultiplier)}x`}
          hint="Média efetiva entre líderes ativos."
          accent="highlight"
        />
      </div>

      {readOnly ? (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            Você pode consultar a estrutura da liderança, mas somente usuários com permissão de configuração podem criar, editar ou excluir perfis e líderes.
          </div>
        </div>
      ) : null}

      <div className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="border-b border-slate-200 px-5 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Configuração de lideranças</h3>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                Organize os multiplicadores por perfil, aplique exceções individuais somente quando necessário e confira rapidamente quais filiais ainda não possuem líder vinculado.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" onClick={() => openRoleDrawer()} disabled={readOnly}>
                <Plus className="h-4 w-4" />
                Novo perfil
              </Button>
              <Button type="button" onClick={() => openLeaderDrawer()} disabled={readOnly}>
                <Plus className="h-4 w-4" />
                Novo líder
              </Button>
            </div>
          </div>
        </div>

        <div className="p-5">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="grid gap-4">
            <TabsList className="grid h-auto grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-1 md:grid-cols-3">
              <TabsTrigger value="role-profiles" className="rounded-xl px-4 py-2.5">Perfis e multiplicadores</TabsTrigger>
              <TabsTrigger value="leaders" className="rounded-xl px-4 py-2.5">Líderes</TabsTrigger>
              <TabsTrigger value="branches" className="rounded-xl px-4 py-2.5">Filiais vinculadas</TabsTrigger>
            </TabsList>

            <TabsContent value="role-profiles" className="mt-0">
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                    <TableRow className="border-slate-700 hover:bg-slate-900">
                      <TableHead>Perfil / cargo</TableHead>
                      <TableHead>Escopo do cálculo</TableHead>
                      <TableHead>Multiplicador padrão</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Líderes vinculados</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {roleProfiles.map((profile) => (
                      <TableRow key={profile.id}>
                        <TableCell>
                          <div className="font-medium text-slate-900">{profile.name}</div>
                          <div className="mt-1 text-sm text-slate-500">{ROLE_SCOPE_HINTS[profile.scope_type]}</div>
                        </TableCell>
                        <TableCell>{ROLE_SCOPE_LABELS[profile.scope_type]}</TableCell>
                        <TableCell className="font-semibold text-uni-royal">{formatNumber(profile.default_multiplier)}x</TableCell>
                        <TableCell>{roleStatusBadge(profile.active)}</TableCell>
                        <TableCell>{profile.linked_leaders_count}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            <Button type="button" size="sm" variant="secondary" onClick={() => openRoleDrawer(profile)} disabled={readOnly}>
                              <PenLine className="h-4 w-4" />
                              Editar
                            </Button>
                            <Button type="button" size="sm" variant="destructive" onClick={() => void onDeleteRoleProfile(profile)} disabled={readOnly}>
                              <Trash2 className="h-4 w-4" />
                              Excluir
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                    {roleProfiles.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-10 text-center text-sm text-slate-500">
                          Nenhum perfil configurado até o momento.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            <TabsContent value="leaders" className="mt-0">
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                    <TableRow className="border-slate-700 hover:bg-slate-900">
                      <TableHead>Líder</TableHead>
                      <TableHead>Perfil / cargo</TableHead>
                      <TableHead>Filiais</TableHead>
                      <TableHead>Origem da média</TableHead>
                      <TableHead>Multiplicador</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {profiles.map((leader) => {
                      const roleProfile = resolveRoleProfile(leader, roleProfiles);
                      return (
                        <TableRow key={leader.id}>
                          <TableCell>
                            <div className="font-medium text-slate-900">{leader.name}</div>
                            <div className="mt-1 text-sm text-slate-500">{ROLE_SCOPE_LABELS[leader.role_type]}</div>
                          </TableCell>
                          <TableCell>
                            <div className="font-medium text-slate-900">{roleProfile?.name ?? "Sem perfil"}</div>
                            <div className="mt-1 text-sm text-slate-500">Escopo {ROLE_SCOPE_LABELS[leader.role_type].toLowerCase()}</div>
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1.5">
                              {leader.regional_names.slice(0, 3).map((regional) => (
                                <Badge key={`${leader.id}-${regional}`} className="border-slate-200 bg-slate-50 text-slate-700">
                                  {regionalName(regional)}
                                </Badge>
                              ))}
                              {leader.regional_names.length > 3 ? (
                                <Badge className="border-slate-200 bg-slate-50 text-slate-600">+{leader.regional_names.length - 3}</Badge>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="font-medium text-slate-900">{AVERAGE_SOURCE_LABELS[leader.average_source ?? "collaborators"]}</div>
                            <div className="mt-1 text-sm text-slate-500">{AVERAGE_SOURCE_HINTS[leader.average_source ?? "collaborators"]}</div>
                          </TableCell>
                          <TableCell>
                            <div className="font-semibold text-uni-royal">{formatNumber(leader.multiplier)}x</div>
                            <div className="mt-1 text-sm text-slate-500">
                              {leader.use_custom_multiplier ? "Personalizado" : "Herdado do perfil"}
                            </div>
                          </TableCell>
                          <TableCell>{roleStatusBadge(leader.active)}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-2">
                              <Button type="button" size="sm" variant="secondary" onClick={() => openLeaderDrawer(leader)} disabled={readOnly}>
                                <PenLine className="h-4 w-4" />
                                Editar
                              </Button>
                              <Button type="button" size="sm" variant="destructive" onClick={() => void onDelete(leader)} disabled={readOnly}>
                                <Trash2 className="h-4 w-4" />
                                Excluir
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                    {profiles.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">
                          Nenhum líder cadastrado até o momento.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            <TabsContent value="branches" className="mt-0">
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                    <TableRow className="border-slate-700 hover:bg-slate-900">
                      <TableHead>Filial</TableHead>
                      <TableHead>Líder responsável</TableHead>
                      <TableHead>Perfil</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {branchCoverageRows.map(({ regional, leaders }) => (
                      <TableRow key={regional}>
                        <TableCell className="font-medium text-slate-900">{regionalName(regional)}</TableCell>
                        <TableCell>
                          {leaders.length > 0 ? leaders.map((item) => item.name).join(", ") : "Sem líder vinculado"}
                        </TableCell>
                        <TableCell>
                          {leaders.length > 0
                            ? leaders
                                .map((item) => resolveRoleProfile(item, roleProfiles)?.name ?? ROLE_SCOPE_LABELS[item.role_type])
                                .join(", ")
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {leaders.length > 0 ? (
                            <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">
                              <BadgeCheck className="mr-1 h-3.5 w-3.5" />
                              Coberta
                            </Badge>
                          ) : (
                            <Badge className="border-amber-200 bg-amber-50 text-amber-700">
                              <CircleAlert className="mr-1 h-3.5 w-3.5" />
                              Sem líder
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <Sheet open={roleDrawerOpen} onOpenChange={setRoleDrawerOpen}>
        <SheetContent className="sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle>{editingRoleId ? "Editar perfil de liderança" : "Novo perfil de liderança"}</SheetTitle>
            <SheetDescription>
              Configure o perfil/cargo que servirá como referência para o multiplicador padrão dos líderes vinculados.
            </SheetDescription>
          </SheetHeader>

          <div className="grid gap-5 overflow-y-auto px-6 py-6">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="grid gap-2">
                <Label>Nome do perfil</Label>
                <Input
                  value={roleDraft.name}
                  onChange={(event) => setRoleDraft((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Ex.: Supervisor"
                  disabled={readOnly}
                />
              </div>
              <div className="grid gap-2">
                <Label>Escopo do cálculo</Label>
                <select
                  value={roleDraft.scope_type}
                  disabled={readOnly}
                  onChange={(event) => {
                    const scopeType = event.target.value as LeadershipRoleType;
                    setRoleDraft((current) => ({
                      ...current,
                      scope_type: scopeType,
                      default_multiplier: DEFAULT_MULTIPLIERS[scopeType],
                    }));
                  }}
                  className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm"
                >
                  {Object.entries(ROLE_SCOPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-slate-500">{ROLE_SCOPE_HINTS[roleDraft.scope_type]}</p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-[180px_1fr] md:items-end">
              <div className="grid gap-2">
                <Label>Multiplicador padrão</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={roleDraft.default_multiplier}
                  onChange={(event) =>
                    setRoleDraft((current) => ({ ...current, default_multiplier: Number(event.target.value) }))
                  }
                  disabled={readOnly}
                />
              </div>
              <label className="flex h-11 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-700">
                <AppCheckbox
                  checked={roleDraft.active}
                  onCheckedChange={(checked) => setRoleDraft((current) => ({ ...current, active: checked }))}
                  disabled={readOnly}
                  ariaLabel="Perfil ativo"
                />
                Perfil ativo para novos líderes e herança de multiplicador
              </label>
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setRoleDrawerOpen(false);
                  resetRoleDraft();
                }}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                disabled={readOnly || !roleDraft.name.trim()}
                onClick={() => {
                  if (editingRoleId) {
                    const current = roleProfiles.find((item) => item.id === editingRoleId);
                    if (!current) return;
                    void onSaveRoleProfile({
                      ...current,
                      name: roleDraft.name.trim(),
                      scope_type: roleDraft.scope_type,
                      default_multiplier: roleDraft.default_multiplier,
                      active: roleDraft.active,
                    }).then(() => {
                      setRoleDrawerOpen(false);
                      resetRoleDraft();
                    });
                    return;
                  }
                  void onCreateRoleProfile(roleDraft).then(() => {
                    setRoleDrawerOpen(false);
                    resetRoleDraft();
                  });
                }}
              >
                {editingRoleId ? "Salvar perfil" : "Criar perfil"}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={leaderDrawerOpen} onOpenChange={setLeaderDrawerOpen}>
        <SheetContent className="sm:max-w-3xl">
          <SheetHeader>
            <SheetTitle>{editingLeaderId ? "Editar líder" : "Novo líder"}</SheetTitle>
            <SheetDescription>
              Vincule o líder ao perfil de cálculo, defina as filiais atendidas e aplique exceção individual apenas quando o multiplicador não puder ser herdado.
            </SheetDescription>
          </SheetHeader>

          <div className="grid gap-5 overflow-y-auto px-6 py-6">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>Nome do líder</Label>
                <Input
                  value={leaderDraft.name}
                  onChange={(event) => setLeaderDraft((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Ex.: Maria Silva"
                  disabled={readOnly}
                />
              </div>
              <div className="grid gap-2">
                <Label>Perfil / cargo</Label>
                <select
                  value={leaderDraft.role_profile_id ?? ""}
                  disabled={readOnly}
                  onChange={(event) => {
                    const roleProfileId = event.target.value ? Number(event.target.value) : null;
                    const profile = roleProfiles.find((item) => item.id === roleProfileId) ?? null;
                    setLeaderDraft((current) => ({
                      ...current,
                      role_profile_id: roleProfileId,
                      role_type: profile?.scope_type ?? current.role_type,
                      multiplier:
                        current.use_custom_multiplier && current.custom_multiplier !== null
                          ? current.custom_multiplier
                          : (profile?.default_multiplier ?? current.multiplier),
                    }));
                  }}
                  className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm"
                >
                  <option value="">Selecionar perfil</option>
                  {roleProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name} ({ROLE_SCOPE_LABELS[profile.scope_type]})
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label>Média calculada por</Label>
                <select
                  value={leaderDraft.average_source}
                  disabled={readOnly}
                  onChange={(event) =>
                    setLeaderDraft((current) => ({
                      ...current,
                      average_source: event.target.value as LeadershipAverageSource,
                    }))
                  }
                  className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm"
                >
                  {Object.entries(AVERAGE_SOURCE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-slate-500">{AVERAGE_SOURCE_HINTS[leaderDraft.average_source]}</p>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <div className="text-sm font-medium text-slate-900">Multiplicador do líder</div>
                  <div className="mt-1 text-sm text-slate-500">
                    {leaderDraft.use_custom_multiplier
                      ? "Exceção individual aplicada para este líder."
                      : "O valor é herdado automaticamente do perfil selecionado."}
                  </div>
                </div>
                <label className="flex items-center gap-3 text-sm text-slate-700">
                  <AppCheckbox
                    checked={leaderDraft.use_custom_multiplier}
                    disabled={readOnly}
                    onCheckedChange={(checked) => {
                      setLeaderDraft((current) => ({
                        ...current,
                        use_custom_multiplier: checked,
                        custom_multiplier: checked ? current.custom_multiplier ?? current.multiplier : null,
                        multiplier: checked
                          ? current.custom_multiplier ?? current.multiplier
                          : (selectedRoleProfile?.default_multiplier ?? current.multiplier),
                      }));
                    }}
                    ariaLabel="Usar multiplicador personalizado"
                  />
                  Usar multiplicador personalizado
                </label>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="grid gap-2">
                  <Label>Origem</Label>
                  <div className="h-11 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700 shadow-sm">
                    {leaderDraft.use_custom_multiplier ? "Personalizado" : selectedRoleProfile?.name ?? "Perfil não definido"}
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label>Multiplicador efetivo</Label>
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    disabled={readOnly || !leaderDraft.use_custom_multiplier}
                    value={leaderDraft.use_custom_multiplier ? leaderDraft.custom_multiplier ?? leaderDraft.multiplier : leaderDraft.multiplier}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      setLeaderDraft((current) => ({
                        ...current,
                        custom_multiplier: value,
                        multiplier: value,
                      }));
                    }}
                  />
                </div>
              </div>
            </div>

            {leaderDraft.role_type === "portfolio_manager" ? (
              // Gerente de pasta ignora filiais no cálculo (usa a média de todos os colaboradores
              // registrados, ver leadership_bonus.py) - mostrar o seletor aqui daria a falsa
              // impressão de que dá pra restringir o escopo dele, quando na prática não muda nada.
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
                Gerente de pasta não usa filiais vinculadas - a bonificação considera a média de todos os colaboradores cadastrados,
                independente de filial.
              </div>
            ) : (
              <div className="grid gap-2">
                <Label>Filiais vinculadas</Label>
                <RegionalMultiSelect
                  options={sortedRegionals}
                  selected={leaderDraft.regional_names}
                  onChange={(values) => setLeaderDraft((current) => ({ ...current, regional_names: uniqueRegionals(values) }))}
                  disabled={readOnly}
                />
              </div>
            )}

            <label className="flex h-11 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm text-slate-700">
              <AppCheckbox
                checked={leaderDraft.active}
                onCheckedChange={(checked) => setLeaderDraft((current) => ({ ...current, active: checked }))}
                disabled={readOnly}
                ariaLabel="Líder ativo"
              />
              Líder ativo para cálculo e conferência das filiais vinculadas
            </label>

            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setLeaderDrawerOpen(false);
                  resetLeaderDraft();
                }}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                disabled={
                  readOnly ||
                  !leaderDraft.name.trim() ||
                  (leaderDraft.role_type !== "portfolio_manager" && leaderDraft.regional_names.length === 0) ||
                  !leaderDraft.role_profile_id
                }
                onClick={() => {
                  const payload: DraftLeader = {
                    ...leaderDraft,
                    name: leaderDraft.name.trim(),
                    multiplier:
                      leaderDraft.use_custom_multiplier
                        ? leaderDraft.custom_multiplier ?? leaderDraft.multiplier
                        : (selectedRoleProfile?.default_multiplier ?? leaderDraft.multiplier),
                  };
                  if (editingLeaderId) {
                    const current = profiles.find((item) => item.id === editingLeaderId);
                    if (!current) return;
                    void onSave({
                      ...current,
                      name: payload.name,
                      role_type: payload.role_type,
                      role_profile_id: payload.role_profile_id,
                      role_profile_name: selectedRoleProfile?.name ?? current.role_profile_name,
                      use_custom_multiplier: payload.use_custom_multiplier,
                      custom_multiplier: payload.use_custom_multiplier ? payload.custom_multiplier : null,
                      multiplier: payload.multiplier,
                      average_source: payload.average_source,
                      active: payload.active,
                      collaborator_id: payload.collaborator_id,
                      regional_names: payload.regional_names,
                    }).then(() => {
                      setLeaderDrawerOpen(false);
                      resetLeaderDraft();
                    });
                    return;
                  }
                  void onCreate(payload).then(() => {
                    setLeaderDrawerOpen(false);
                    resetLeaderDraft();
                  });
                }}
              >
                {editingLeaderId ? "Salvar líder" : "Criar líder"}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
