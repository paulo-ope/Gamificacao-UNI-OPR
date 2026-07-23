"use client";

import { Save, ShieldCheck, UserCog, UserPlus, Users2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  AppCombobox,
  AppDrawer,
  AppInput,
  AppModal,
  AppSwitch,
  RegionalMultiSelect,
  RowActionMenu,
  StatusBadge,
  uniqueRegionals,
} from "@/components/gamification/config-ui";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { normalizeRegional, regionalName } from "@/lib/regional";
import { cn } from "@/lib/utils";
import type { AuthUser, CollaboratorRegistryItem } from "@/lib/types";

type UserPayload = {
  name: string;
  email: string;
  password?: string;
  role: string;
  active: boolean;
  collaborator_id: number | null;
  managed_regionals: string[];
};

type Props = {
  users: AuthUser[];
  collaborators?: CollaboratorRegistryItem[];
  regionalOptions?: string[];
  onCreate: (payload: UserPayload & { password: string }) => Promise<void>;
  onSave: (id: number, payload: UserPayload) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
};

type EditDraft = {
  name: string;
  email: string;
  password: string;
  role: string;
  active: boolean;
  collaborator_id: number | null;
  managed_regionals: string[];
};

const BLANK_DRAFT: EditDraft = {
  name: "",
  email: "",
  password: "",
  role: "viewer",
  active: true,
  collaborator_id: null,
  managed_regionals: [],
};

function draftFromUser(user: AuthUser): EditDraft {
  return {
    name: user.name,
    email: user.email,
    password: "",
    role: user.role,
    active: user.active,
    collaborator_id: user.collaborator_id,
    managed_regionals: user.managed_regionals,
  };
}

const roles = [
  { value: "viewer", label: "Viewer" },
  { value: "operator", label: "Operator" },
  { value: "admin", label: "Admin" },
  { value: "collaborator", label: "Colaborador (portal)" },
  { value: "regional_manager_viewer", label: "Gestor regional (portal)" },
];

function roleLabel(role: string) {
  return roles.find((item) => item.value === role)?.label ?? role;
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
  accent?: "default" | "highlight";
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        {icon}
        {label}
      </div>
      <div className={cn("mt-3 text-2xl font-semibold", accent === "highlight" ? "text-blue-700" : "text-slate-950")}>{value}</div>
      <div className="mt-1 text-sm text-slate-500">{hint}</div>
    </div>
  );
}

function statusBadge(active: boolean) {
  return active ? (
    <StatusBadge tone="success">Ativo</StatusBadge>
  ) : (
    <StatusBadge>Inativo</StatusBadge>
  );
}

export function UserManagementPanel({ users, collaborators = [], regionalOptions = [], onCreate, onSave, onDelete }: Props) {
  const [rows, setRows] = useState(users);
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState<number | null>(null);
  const [savingId, setSavingId] = useState<number | "new" | null>(null);

  // Drawer único de criar/editar - a tabela deixa de ter cada campo editável espremido na linha
  // (achado do usuário: muito campo exprimido, sem espaço) e vira só leitura + botão "Editar", mesmo
  // padrão já usado em Colaboradores.
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<EditDraft>(BLANK_DRAFT);

  const sortedRegionalOptions = useMemo(
    () =>
      Array.from(new Set(regionalOptions.map((regional) => normalizeRegional(regional)).filter(Boolean))).sort((a, b) =>
        regionalName(a).localeCompare(regionalName(b), "pt-BR")
      ),
    [regionalOptions]
  );

  useEffect(() => {
    setRows(users);
  }, [users]);

  const activeUsers = useMemo(() => rows.filter((item) => item.active), [rows]);
  const adminUsers = useMemo(() => rows.filter((item) => item.role === "admin"), [rows]);

  const linkedCollaboratorIds = useMemo(
    () => new Set(rows.map((item) => item.collaborator_id).filter((id): id is number => id != null)),
    [rows]
  );

  const editingUser = typeof editingId === "number" ? rows.find((item) => item.id === editingId) ?? null : null;
  const drawerOpen = editingId !== null;

  // Combobox de "colaborador vinculado": só oferece colaboradores sem usuário ainda, mais o que já
  // está vinculado a esta própria linha (senão ele desapareceria da lista ao editar outro campo).
  function collaboratorOptions(currentId: number | null) {
    const available = collaborators.filter((item) => !linkedCollaboratorIds.has(item.id) || item.id === currentId);
    return [
      { value: "", label: "Nenhum", description: "Sem vínculo com colaborador." },
      ...available.map((item) => ({ value: String(item.id), label: item.name, description: item.role || undefined })),
    ];
  }

  // Vínculo com o portal só faz sentido pros dois perfis de portal - Admin/Operator/Viewer não têm
  // conceito de "colaborador vinculado" nem "regional gerenciada", então o controle some pra eles em
  // vez de mostrar algo sem efeito nenhum.
  function vinculoField(role: string, collaboratorId: number | null, managedRegionals: string[]) {
    if (role === "collaborator") {
      return (
        <AppCombobox
          value={collaboratorId != null ? String(collaboratorId) : ""}
          onChange={(value) => updateDraft({ collaborator_id: value ? Number(value) : null })}
          placeholder="Nenhum"
          ariaLabel="Colaborador vinculado"
          options={collaboratorOptions(collaboratorId)}
        />
      );
    }
    if (role === "regional_manager_viewer") {
      // Um gestor regional pode acompanhar várias filiais ao mesmo tempo - mesmo padrão de
      // seleção múltipla já usado pra "Filiais vinculadas" em Liderança.
      return (
        <RegionalMultiSelect
          options={sortedRegionalOptions}
          selected={managedRegionals}
          onChange={(values) => updateDraft({ managed_regionals: uniqueRegionals(values) })}
        />
      );
    }
    return <div className="flex h-11 items-center text-sm text-slate-400">Não aplicável a este perfil.</div>;
  }

  function vinculoSummary(user: AuthUser) {
    if (user.role === "collaborator") {
      if (user.collaborator_id == null) return "Sem colaborador vinculado";
      const collaborator = collaborators.find((item) => item.id === user.collaborator_id);
      return collaborator ? collaborator.name : `Colaborador #${user.collaborator_id}`;
    }
    if (user.role === "regional_manager_viewer") {
      return user.managed_regionals.length > 0
        ? user.managed_regionals.map((regional) => regionalName(regional)).join(", ")
        : "Sem regional vinculada";
    }
    return "—";
  }

  function openCreateDrawer() {
    setDraft(BLANK_DRAFT);
    setEditingId("new");
  }

  function openEditDrawer(user: AuthUser) {
    setDraft(draftFromUser(user));
    setEditingId(user.id);
  }

  function closeDrawer() {
    setEditingId(null);
    setDraft(BLANK_DRAFT);
  }

  function updateDraft(patch: Partial<EditDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  async function saveDraft() {
    if (!draft.name.trim() || !draft.email.trim()) return;
    setSavingId(editingId);
    try {
      if (editingId === "new") {
        if (!draft.password.trim()) return;
        await onCreate({
          name: draft.name.trim(),
          email: draft.email.trim(),
          password: draft.password,
          role: draft.role,
          active: draft.active,
          collaborator_id: draft.collaborator_id,
          managed_regionals: draft.managed_regionals,
        });
      } else if (editingUser) {
        await onSave(editingUser.id, {
          name: draft.name.trim(),
          email: draft.email.trim(),
          password: draft.password.trim() || undefined,
          role: draft.role,
          active: draft.active,
          collaborator_id: draft.collaborator_id,
          managed_regionals: draft.managed_regionals,
        });
      }
      closeDrawer();
    } finally {
      setSavingId(null);
    }
  }

  return (
    <section className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <SummaryCard
          icon={<Users2 className="h-4 w-4" />}
          label="Usuários"
          value={String(rows.length)}
          hint="Total de contas disponíveis no ambiente."
        />
        <SummaryCard
          icon={<ShieldCheck className="h-4 w-4" />}
          label="Admins"
          value={String(adminUsers.length)}
          hint="Perfis com permissão administrativa."
          accent={adminUsers.length > 0 ? "highlight" : "default"}
        />
        <SummaryCard
          icon={<UserCog className="h-4 w-4" />}
          label="Ativos"
          value={String(activeUsers.length)}
          hint="Contas habilitadas para acesso imediato."
        />
      </div>

      <div className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="border-b border-slate-200 px-5 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Usuários e permissões</h3>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                Gerencie acesso por perfil e revise rapidamente contas ativas. Use "Editar" para abrir o cadastro completo.
              </p>
            </div>
            <Button type="button" onClick={openCreateDrawer}>
              <UserPlus className="h-4 w-4" />
              Cadastrar usuário
            </Button>
          </div>
        </div>

        <div className="p-5">
          <div className="overflow-hidden rounded-2xl border border-slate-200">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                <TableRow className="border-slate-700 hover:bg-slate-900">
                  <TableHead>Nome</TableHead>
                  <TableHead>E-mail</TableHead>
                  <TableHead>Perfil</TableHead>
                  <TableHead>Vínculo (portal)</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-32">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium text-slate-950">{user.name}</TableCell>
                    <TableCell className="text-sm text-slate-600">{user.email}</TableCell>
                    <TableCell className="text-sm text-slate-700">{roleLabel(user.role)}</TableCell>
                    <TableCell className="text-sm text-slate-600">{vinculoSummary(user)}</TableCell>
                    <TableCell>{statusBadge(user.active)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" variant="outline" onClick={() => openEditDrawer(user)}>
                          Editar
                        </Button>
                        <RowActionMenu
                          ariaLabel={`Ações do usuário ${user.name}`}
                          items={[{ label: "Excluir", onSelect: () => setPendingDeleteUserId(user.id), tone: "danger" }]}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="py-10 text-center text-sm text-slate-500">
                      Nenhum usuário cadastrado até o momento.
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>

      <AppDrawer
        open={drawerOpen}
        onOpenChange={(open) => !open && closeDrawer()}
        title={editingId === "new" ? "Cadastrar usuário" : `Editar ${editingUser?.name ?? "usuário"}`}
        description="Nome, e-mail e perfil são obrigatórios. O vínculo com o portal depende do perfil escolhido."
      >
        <div className="grid gap-5">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2 md:col-span-2">
              <Label>Nome completo</Label>
              <AppInput value={draft.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="Nome do usuário" />
            </div>
            <div className="grid gap-2">
              <Label>E-mail</Label>
              <AppInput type="email" value={draft.email} onChange={(event) => updateDraft({ email: event.target.value })} placeholder="nome@exemplo.com" />
            </div>
            <div className="grid gap-2">
              <Label>Perfil</Label>
              <AppCombobox
                value={draft.role}
                onChange={(value) => updateDraft({ role: value })}
                placeholder="Selecionar perfil"
                ariaLabel="Perfil do usuário"
                options={roles.map((role) => ({ value: role.value, label: role.label }))}
              />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label>Vínculo (portal)</Label>
              {vinculoField(draft.role, draft.collaborator_id, draft.managed_regionals)}
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label>{editingId === "new" ? "Senha inicial" : "Nova senha"}</Label>
              <AppInput
                type="password"
                value={draft.password}
                onChange={(event) => updateDraft({ password: event.target.value })}
                placeholder={editingId === "new" ? "Senha inicial" : "Deixe em branco para manter a atual"}
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
            <div>
              <div className="text-sm font-medium text-slate-900">Ativo</div>
              <div className="text-xs text-slate-500">Desligado bloqueia o acesso imediatamente.</div>
            </div>
            <AppSwitch checked={draft.active} onCheckedChange={(checked) => updateDraft({ active: checked })} />
          </div>

          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={closeDrawer}>
              Cancelar
            </Button>
            <Button
              type="button"
              onClick={() => void saveDraft()}
              disabled={
                !draft.name.trim() ||
                !draft.email.trim() ||
                savingId !== null ||
                (editingId === "new" && !draft.password.trim())
              }
            >
              <Save className="h-4 w-4" />
              {savingId !== null ? "Salvando..." : editingId === "new" ? "Cadastrar" : "Salvar"}
            </Button>
          </div>
        </div>
      </AppDrawer>

      <AppModal
        open={pendingDeleteUserId != null}
        onOpenChange={(open) => setPendingDeleteUserId(open ? pendingDeleteUserId : null)}
        title="Excluir usuário?"
        description={pendingDeleteUserId != null ? `Esta ação remove o acesso definitivamente para ${rows.find((user) => user.id === pendingDeleteUserId)?.name ?? "este usuário"}.` : undefined}
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setPendingDeleteUserId(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => {
                if (pendingDeleteUserId == null) return;
                void onDelete(pendingDeleteUserId);
                setPendingDeleteUserId(null);
              }}
            >
              Excluir
            </Button>
          </>
        }
      >
        <div className="text-sm text-slate-600">A conta deixa de ficar disponível no painel e o acesso é removido desta base.</div>
      </AppModal>
    </section>
  );
}
