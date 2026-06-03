"use client";

import { KeyRound, Save, ShieldCheck, Trash2, UserCog, UserPlus, Users2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { AuthUser } from "@/lib/types";

type Props = {
  users: AuthUser[];
  onCreate: (payload: { name: string; email: string; password: string; role: string; active: boolean }) => Promise<void>;
  onSave: (id: number, payload: { name: string; email: string; password?: string; role: string; active: boolean }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
};

const roles = [
  { value: "viewer", label: "Viewer" },
  { value: "operator", label: "Operator" },
  { value: "admin", label: "Admin" },
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
    <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Ativo</Badge>
  ) : (
    <Badge className="border-slate-200 bg-slate-100 text-slate-700">Inativo</Badge>
  );
}

export function UserManagementPanel({ users, onCreate, onSave, onDelete }: Props) {
  const [rows, setRows] = useState(users);
  const [passwords, setPasswords] = useState<Record<number, string>>({});
  const [draft, setDraft] = useState({ name: "", email: "", password: "", role: "viewer", active: true });

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

        <div className="grid gap-4 border-b border-slate-200 bg-slate-50/80 px-5 py-5 lg:grid-cols-[1fr_1fr_0.9fr_auto]">
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Nome</label>
            <Input className="h-11" placeholder="Nome" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">E-mail</label>
            <Input className="h-11" placeholder="E-mail" value={draft.email} onChange={(event) => setDraft((current) => ({ ...current, email: event.target.value }))} />
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Perfil</label>
            <select
              className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm"
              value={draft.role}
              onChange={(event) => setDraft((current) => ({ ...current, role: event.target.value }))}
            >
              {roles.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Senha inicial</label>
            <div className="flex gap-3">
              <Input
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
                  setDraft({ name: "", email: "", password: "", role: "viewer", active: true });
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
                  <TableHead>Status</TableHead>
                  <TableHead>Nova senha</TableHead>
                  <TableHead className="w-56">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell><Input value={user.name} onChange={(event) => patch(user.id, { name: event.target.value })} /></TableCell>
                    <TableCell><Input value={user.email} onChange={(event) => patch(user.id, { email: event.target.value })} /></TableCell>
                    <TableCell>
                      <select
                        className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm"
                        value={user.role}
                        onChange={(event) => patch(user.id, { role: event.target.value as AuthUser["role"] })}
                      >
                        {roles.map((role) => (
                          <option key={role.value} value={role.value}>
                            {role.label}
                          </option>
                        ))}
                      </select>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        {statusBadge(user.active)}
                        <label className="flex items-center gap-2 text-sm text-slate-600">
                          <input type="checkbox" checked={user.active} onChange={(event) => patch(user.id, { active: event.currentTarget.checked })} />
                          Ativo
                        </label>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Input type="password" placeholder="Manter atual" value={passwords[user.id] ?? ""} onChange={(event) => setPasswords((current) => ({ ...current, [user.id]: event.target.value }))} />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" onClick={() => onSave(user.id, { name: user.name, email: user.email, role: user.role, active: user.active, password: passwords[user.id] || undefined })}>
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-red-200 text-red-700 hover:bg-red-50"
                          onClick={() => {
                            if (window.confirm(`Excluir o usuário ${user.name}? Esta ação remove o acesso definitivamente.`)) {
                              void onDelete(user.id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                          Excluir
                        </Button>
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
    </section>
  );
}
