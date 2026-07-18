"use client";

import { KeyRound, Save, ShieldCheck, Trash2, UserCog, UserPlus, Users2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { AppCombobox, AppInput, AppModal, AppSwitch, RowActionMenu, StatusBadge } from "@/components/gamification/config-ui";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { AuthUser, CollaboratorRegistryItem } from "@/lib/types";

type UserPayload = { name: string; email: string; password?: string; role: string; active: boolean; collaborator_id: number | null };

type Props = {
  users: AuthUser[];
  collaborators?: CollaboratorRegistryItem[];
  onCreate: (payload: UserPayload & { password: string }) => Promise<void>;
  onSave: (id: number, payload: UserPayload) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
};

const roles = [
  { value: "viewer", label: "Viewer" },
  { value: "operator", label: "Operator" },
  { value: "admin", label: "Admin" },
  { value: "collaborator", label: "Colaborador (portal)" },
  { value: "regional_manager_viewer", label: "Gestor regional (portal)" },
];

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
      <div className={cn("mt-3 text-2xl font-semibold", accent === "highlight" ? "text-teal-700" : "text-slate-950")}>{value}</div>
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

export function UserManagementPanel({ users, collaborators = [], onCreate, onSave, onDelete }: Props) {
  const [rows, setRows] = useState(users);
  const [passwords, setPasswords] = useState<Record<number, string>>({});
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState<number | null>(null);
  const [draft, setDraft] = useState({ name: "", email: "", password: "", role: "viewer", active: true, collaborator_id: null as number | null });

  useEffect(() => {
    setRows(users);
    setPasswords({});
  }, [users]);

  const activeUsers = useMemo(() => rows.filter((item) => item.active), [rows]);
  const adminUsers = useMemo(() => rows.filter((item) => item.role === "admin"), [rows]);
  const pendingPasswordChanges = useMemo(
    () => Object.values(passwords).filter((value) => value.trim().length > 0).length,
    [passwords]
  );

  function patch(id: number, data: Partial<AuthUser>) {
    setRows((current) => current.map((item) => (item.id === id ? { ...item, ...data } : item)));
  }

  const linkedCollaboratorIds = useMemo(
    () => new Set(rows.map((item) => item.collaborator_id).filter((id): id is number => id != null)),
    [rows]
  );

  // Combobox de "colaborador vinculado": só oferece colaboradores sem usuário ainda, mais o que já
  // está vinculado a esta própria linha (senão ele desapareceria da lista ao editar outro campo).
  function collaboratorOptions(currentId: number | null) {
    const available = collaborators.filter((item) => !linkedCollaboratorIds.has(item.id) || item.id === currentId);
    return [
      { value: "", label: "Nenhum", description: "Sem vínculo com colaborador." },
      ...available.map((item) => ({ value: String(item.id), label: item.name, description: item.role || undefined })),
    ];
  }

  return (
    <section className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        <SummaryCard
          icon={<KeyRound className="h-4 w-4" />}
          label="Senhas em edição"
          value={String(pendingPasswordChanges)}
          hint="Alterações de senha preenchidas, aguardando salvar."
          accent={pendingPasswordChanges > 0 ? "highlight" : "default"}
        />
      </div>

      <div className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="border-b border-slate-200 px-5 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Usuários e permissões</h3>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                Gerencie acesso simples por perfil, revise rapidamente contas ativas e deixe a manutenção de credenciais mais clara na mesma superfície.
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-4 border-b border-slate-200 bg-slate-50/80 px-5 py-5 lg:grid-cols-[1fr_1fr_0.9fr_1fr_auto]">
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Nome</label>
            <AppInput className="h-11" placeholder="Nome" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">E-mail</label>
            <AppInput className="h-11" placeholder="E-mail" value={draft.email} onChange={(event) => setDraft((current) => ({ ...current, email: event.target.value }))} />
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Perfil</label>
            <AppCombobox
              value={draft.role}
              onChange={(value) => setDraft((current) => ({ ...current, role: value }))}
              placeholder="Selecionar perfil"
              ariaLabel="Perfil do novo usuário"
              options={roles.map((role) => ({ value: role.value, label: role.label }))}
            />
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Colaborador vinculado</label>
            <AppCombobox
              value={draft.collaborator_id != null ? String(draft.collaborator_id) : ""}
              onChange={(value) => setDraft((current) => ({ ...current, collaborator_id: value ? Number(value) : null }))}
              placeholder="Nenhum"
              ariaLabel="Colaborador vinculado ao novo usuário"
              options={collaboratorOptions(draft.collaborator_id)}
            />
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Senha inicial</label>
            <div className="flex gap-3">
              <AppInput
                className="h-11"
                placeholder="Senha inicial"
                type="password"
                value={draft.password}
                onChange={(event) => setDraft((current) => ({ ...current, password: event.target.value }))}
              />
              <Button
                className="h-11"
                onClick={async () => {
                  await onCreate(draft);
                  setDraft({ name: "", email: "", password: "", role: "viewer", active: true, collaborator_id: null });
                }}
                disabled={!draft.name.trim() || !draft.email.trim() || !draft.password.trim()}
              >
                <UserPlus className="h-4 w-4" />
                Criar
              </Button>
            </div>
          </div>
        </div>

        <div className="p-5">
          <div className="overflow-hidden rounded-2xl border border-slate-200">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50/80">
                  <TableHead>Nome</TableHead>
                  <TableHead>E-mail</TableHead>
                  <TableHead>Perfil</TableHead>
                  <TableHead>Colaborador vinculado</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Nova senha</TableHead>
                  <TableHead className="w-56">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell><AppInput value={user.name} onChange={(event) => patch(user.id, { name: event.target.value })} /></TableCell>
                    <TableCell><AppInput value={user.email} onChange={(event) => patch(user.id, { email: event.target.value })} /></TableCell>
                    <TableCell>
                      <AppCombobox
                        value={user.role}
                        onChange={(value) => patch(user.id, { role: value as AuthUser["role"] })}
                        placeholder="Selecionar perfil"
                        ariaLabel={`Perfil do usuário ${user.name}`}
                        options={roles.map((role) => ({ value: role.value, label: role.label }))}
                      />
                    </TableCell>
                    <TableCell>
                      <AppCombobox
                        value={user.collaborator_id != null ? String(user.collaborator_id) : ""}
                        onChange={(value) => patch(user.id, { collaborator_id: value ? Number(value) : null })}
                        placeholder="Nenhum"
                        ariaLabel={`Colaborador vinculado ao usuário ${user.name}`}
                        options={collaboratorOptions(user.collaborator_id)}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        {statusBadge(user.active)}
                        <AppSwitch checked={user.active} onCheckedChange={(checked) => patch(user.id, { active: checked })} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <AppInput type="password" placeholder="Manter atual" value={passwords[user.id] ?? ""} onChange={(event) => setPasswords((current) => ({ ...current, [user.id]: event.target.value }))} />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            onSave(user.id, {
                              name: user.name,
                              email: user.email,
                              role: user.role,
                              active: user.active,
                              collaborator_id: user.collaborator_id,
                              password: passwords[user.id] || undefined,
                            })
                          }
                        >
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                        <RowActionMenu
                          ariaLabel={`Ações do usuário ${user.name}`}
                          items={[
                            { label: "Excluir", onSelect: () => setPendingDeleteUserId(user.id), tone: "danger" },
                          ]}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">
                      Nenhum usuário cadastrado até o momento.
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
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
