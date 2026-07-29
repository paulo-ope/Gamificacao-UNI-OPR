"use client";

import Link from "next/link";
import { ArrowLeft, Loader2, LogOut, Plus, Save, ShieldCheck, Trash2, UserCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MultiSelect } from "@/components/ui/multi-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { api } from "@/lib/api";
import type { AccessProfile, AuthUser, EcosystemPermission, Permission } from "@/lib/types";

const LEGACY_ROLE_BY_PROFILE: Record<string, AuthUser["role"]> = {
  "Admin Ecossistema": "admin",
  "Operador Operacional": "operator",
  "Leitor Operacional": "viewer",
  "Colaborador Portal": "collaborator",
  "Gestor Regional Portal": "regional_manager_viewer",
};

type UserDraft = {
  id: number | "new";
  name: string;
  email: string;
  password: string;
  active: boolean;
  access_profile_ids: number[];
  managed_regionals: string[];
};

type ProfileDraft = {
  id: number | "new";
  name: string;
  description: string;
  active: boolean;
  permission_keys: Permission[];
};

function blankUserDraft(): UserDraft {
  return {
    id: "new",
    name: "",
    email: "",
    password: "",
    active: true,
    access_profile_ids: [],
    managed_regionals: [],
  };
}

function blankProfileDraft(): ProfileDraft {
  return {
    id: "new",
    name: "",
    description: "",
    active: true,
    permission_keys: [],
  };
}

function profileNames(user: AuthUser, profiles: AccessProfile[]) {
  const names = user.access_profile_ids
    .map((id) => profiles.find((profile) => profile.id === id)?.name)
    .filter(Boolean);
  return names.length ? names.join(", ") : user.role;
}

function permissionGroups(permissions: EcosystemPermission[]) {
  return permissions.reduce<Record<string, EcosystemPermission[]>>((groups, permission) => {
    groups[permission.module] = [...(groups[permission.module] || []), permission];
    return groups;
  }, {});
}

export default function AdminPage() {
  const { user, checking, error, login, logout } = useWorkspaceAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [profiles, setProfiles] = useState<AccessProfile[]>([]);
  const [permissions, setPermissions] = useState<EcosystemPermission[]>([]);
  const [operationRegionals, setOperationRegionals] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [userDraft, setUserDraft] = useState<UserDraft | null>(null);
  const [profileDraft, setProfileDraft] = useState<ProfileDraft | null>(null);

  const canAdmin = Boolean(user?.permissions.includes("admin:users:read"));
  const canWriteUsers = Boolean(user?.permissions.includes("admin:users:write"));
  const canDeleteUsers = Boolean(user?.permissions.includes("admin:users:delete"));
  const canWriteProfiles = Boolean(user?.permissions.includes("admin:roles:write"));
  const groupedPermissions = useMemo(() => permissionGroups(permissions), [permissions]);

  async function loadAdminData() {
    setLoading(true);
    setLoadError(null);
    try {
      const [nextUsers, nextProfiles, nextPermissions, nextOperationRegionals] = await Promise.all([
        api.users(),
        api.accessProfiles(),
        api.ecosystemPermissions(),
        api.operationRegionals(),
      ]);
      setUsers(nextUsers);
      setProfiles(nextProfiles);
      setPermissions(nextPermissions);
      setOperationRegionals(nextOperationRegionals);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "Não foi possível carregar a administração.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user && canAdmin) void loadAdminData();
  }, [user, canAdmin]);

  if (checking && !user) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Carregando Administração...
      </main>
    );
  }
  if (!user) return <WorkspaceLogin isLoading={checking} error={error} onLogin={login} />;

  if (!canAdmin) {
    return (
      <main className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-3xl rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <h1 className="text-xl font-semibold">Acesso administrativo necessário</h1>
          <p className="mt-2 text-sm">Seu usuário não possui permissão para administrar o ecossistema.</p>
          <Link href="/" className="mt-4 inline-flex text-sm font-semibold text-amber-800">
            Voltar ao ecossistema
          </Link>
        </div>
      </main>
    );
  }

  async function saveUserDraft() {
    if (!userDraft || !userDraft.name.trim() || !userDraft.email.trim()) return;
    if (userDraft.id === "new" && !userDraft.password.trim()) return;
    setSaving(true);
    setMessage(null);
    try {
      const selectedProfiles = profiles.filter((profile) => userDraft.access_profile_ids.includes(profile.id));
      const legacyRole = selectedProfiles.find((profile) => profile.legacy_role)?.legacy_role;
      const fallbackRole = LEGACY_ROLE_BY_PROFILE[selectedProfiles[0]?.name || ""] || "viewer";
      const payload = {
        name: userDraft.name.trim(),
        email: userDraft.email.trim(),
        password: userDraft.password.trim() || undefined,
        active: userDraft.active,
        role: (legacyRole || fallbackRole) as AuthUser["role"],
        access_profile_ids: userDraft.access_profile_ids,
        managed_regionals: Array.from(new Set(userDraft.managed_regionals)),
      };
      if (userDraft.id === "new") {
        await api.createUser({ ...payload, password: userDraft.password });
      } else {
        await api.updateUser(userDraft.id, payload);
      }
      setUserDraft(null);
      setMessage("Usuário salvo.");
      await loadAdminData();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Não foi possível salvar o usuário.");
    } finally {
      setSaving(false);
    }
  }

  async function saveProfileDraft() {
    if (!profileDraft || !profileDraft.name.trim()) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        name: profileDraft.name.trim(),
        description: profileDraft.description.trim() || null,
        active: profileDraft.active,
        permission_keys: profileDraft.permission_keys,
      };
      if (profileDraft.id === "new") {
        await api.createAccessProfile(payload);
      } else {
        await api.updateAccessProfile(profileDraft.id, payload);
      }
      setProfileDraft(null);
      setMessage("Perfil salvo.");
      await loadAdminData();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Não foi possível salvar o perfil.");
    } finally {
      setSaving(false);
    }
  }

  function toggleProfilePermission(permission: Permission) {
    setProfileDraft((current) => {
      if (!current) return current;
      const exists = current.permission_keys.includes(permission);
      return {
        ...current,
        permission_keys: exists
          ? current.permission_keys.filter((item) => item !== permission)
          : [...current.permission_keys, permission].sort(),
      };
    });
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
              <h1 className="text-base font-semibold text-slate-950">Administração do Ecossistema</h1>
            </div>
          </div>
          <Button type="button" variant="ghost" onClick={logout}>
            <LogOut className="h-4 w-4" /> Sair
          </Button>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-600">Controle central</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">Usuários, perfis e permissões</h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                Este controle pertence ao ecossistema. A Gamificação e a Operação passam a consumir os mesmos usuários e permissões.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{users.length}</p>
                <p className="text-slate-500">Usuários</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{profiles.length}</p>
                <p className="text-slate-500">Perfis</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-lg font-bold text-slate-950">{permissions.length}</p>
                <p className="text-slate-500">Permissões</p>
              </div>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-8 text-sm text-slate-500">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
            Carregando dados administrativos...
          </div>
        ) : null}
        {loadError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{loadError}</div>
        ) : null}
        {message ? (
          <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-800">{message}</div>
        ) : null}

        <Tabs defaultValue="users">
          <TabsList className="bg-white">
            <TabsTrigger value="users">Usuários</TabsTrigger>
            <TabsTrigger value="profiles">Perfis de acesso</TabsTrigger>
          </TabsList>

          <TabsContent value="users" className="mt-4">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
                <div>
                  <h3 className="text-lg font-semibold text-slate-950">Usuários do ecossistema</h3>
                  <p className="text-sm text-slate-500">Controle acesso, perfis e escopo regional.</p>
                </div>
                {canWriteUsers ? (
                  <Button type="button" onClick={() => setUserDraft(blankUserDraft())}>
                    <Plus className="h-4 w-4" /> Novo usuário
                  </Button>
                ) : null}
              </div>
              <div className="overflow-x-auto p-5">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nome</TableHead>
                      <TableHead>E-mail</TableHead>
                      <TableHead>Perfis</TableHead>
                      <TableHead>Regionais</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className="font-medium text-slate-950">{row.name}</TableCell>
                        <TableCell className="text-sm text-slate-600">{row.email}</TableCell>
                        <TableCell className="max-w-xs text-sm text-slate-600">{profileNames(row, profiles)}</TableCell>
                        <TableCell className="text-sm text-slate-600">{row.managed_regionals.join(", ") || "—"}</TableCell>
                        <TableCell>
                          <Badge className={row.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                            {row.active ? "Ativo" : "Inativo"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            {canWriteUsers ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  setUserDraft({
                                    id: row.id,
                                    name: row.name,
                                    email: row.email,
                                    password: "",
                                    active: row.active,
                                    access_profile_ids: row.access_profile_ids,
                                    managed_regionals: row.managed_regionals,
                                  })
                                }
                              >
                                Editar
                              </Button>
                            ) : null}
                            {canDeleteUsers ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="text-red-600"
                                onClick={async () => {
                                  if (!confirm(`Excluir acesso de ${row.name}?`)) return;
                                  await api.deleteUser(row.id);
                                  await loadAdminData();
                                }}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="profiles" className="mt-4">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
                <div>
                  <h3 className="text-lg font-semibold text-slate-950">Perfis de acesso</h3>
                  <p className="text-sm text-slate-500">Monte grupos de permissões por módulo.</p>
                </div>
                {canWriteProfiles ? (
                  <Button type="button" onClick={() => setProfileDraft(blankProfileDraft())}>
                    <Plus className="h-4 w-4" /> Novo perfil
                  </Button>
                ) : null}
              </div>
              <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
                {profiles.map((profile) => (
                  <button
                    key={profile.id}
                    type="button"
                    className="rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-blue-300 hover:shadow"
                    onClick={() =>
                      setProfileDraft({
                        id: profile.id,
                        name: profile.name,
                        description: profile.description || "",
                        active: profile.active,
                        permission_keys: profile.permission_keys,
                      })
                    }
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="font-semibold text-slate-950">{profile.name}</h4>
                        <p className="mt-1 line-clamp-2 text-sm text-slate-500">{profile.description || "Sem descrição."}</p>
                      </div>
                      {profile.is_system ? <ShieldCheck className="h-4 w-4 text-blue-600" /> : <UserCog className="h-4 w-4 text-slate-400" />}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
                      <Badge className="border border-slate-200 bg-white text-slate-600">
                        {profile.permission_keys.length} permissões
                      </Badge>
                      <Badge className="border border-slate-200 bg-white text-slate-600">
                        {profile.user_count} usuários
                      </Badge>
                      <Badge className={profile.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                        {profile.active ? "Ativo" : "Inativo"}
                      </Badge>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </section>

      {userDraft ? (
        <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-4">
          <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-950">{userDraft.id === "new" ? "Novo usuário" : "Editar usuário"}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="grid gap-2 md:col-span-2">
                <Label>Nome</Label>
                <Input value={userDraft.name} onChange={(event) => setUserDraft({ ...userDraft, name: event.target.value })} />
              </div>
              <div className="grid gap-2">
                <Label>E-mail</Label>
                <Input type="email" value={userDraft.email} onChange={(event) => setUserDraft({ ...userDraft, email: event.target.value })} />
              </div>
              <div className="grid gap-2">
                <Label>{userDraft.id === "new" ? "Senha inicial" : "Nova senha"}</Label>
                <Input
                  type="password"
                  value={userDraft.password}
                  placeholder={userDraft.id === "new" ? "Obrigatória" : "Em branco mantém a atual"}
                  onChange={(event) => setUserDraft({ ...userDraft, password: event.target.value })}
                />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>Regionais permitidas</Label>
                <MultiSelect
                  values={userDraft.managed_regionals}
                  options={Array.from(new Set([...operationRegionals, ...userDraft.managed_regionals])).sort((left, right) => left.localeCompare(right, "pt-BR"))}
                  placeholder="Sem restrição regional"
                  ariaLabel="Selecionar regionais permitidas"
                  onChange={(managed_regionals) => setUserDraft({ ...userDraft, managed_regionals })}
                />
                <p className="text-xs text-slate-500">
                  Selecione uma ou mais regionais. A lista remove duplicidades automaticamente; vazio significa sem restrição regional para este usuário.
                </p>
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>Perfis de acesso</Label>
                <div className="grid gap-2 rounded-2xl border border-slate-200 p-3 sm:grid-cols-2">
                  {profiles.map((profile) => (
                    <label key={profile.id} className="flex items-start gap-2 rounded-xl p-2 text-sm hover:bg-slate-50">
                      <AppCheckbox
                        checked={userDraft.access_profile_ids.includes(profile.id)}
                        onCheckedChange={(checked) =>
                          setUserDraft({
                            ...userDraft,
                            access_profile_ids: checked
                              ? [...userDraft.access_profile_ids, profile.id]
                              : userDraft.access_profile_ids.filter((id) => id !== profile.id),
                          })
                        }
                        ariaLabel={profile.name}
                      />
                      <span>
                        <span className="font-medium text-slate-800">{profile.name}</span>
                        <span className="block text-xs text-slate-500">{profile.permission_keys.length} permissões</span>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-slate-500">
                  Remover todos os perfis bloqueia o acesso ao ecossistema para este usuário. Perfis inativos não podem ser vinculados.
                </p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <AppCheckbox checked={userDraft.active} onCheckedChange={(checked) => setUserDraft({ ...userDraft, active: checked })} ariaLabel="Usuário ativo" />
                Usuário ativo
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setUserDraft(null)}>Cancelar</Button>
              <Button type="button" onClick={() => void saveUserDraft()} disabled={saving}>
                <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {profileDraft ? (
        <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-4">
          <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-3xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-950">{profileDraft.id === "new" ? "Novo perfil" : "Editar perfil"}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>Nome do perfil</Label>
                <Input value={profileDraft.name} onChange={(event) => setProfileDraft({ ...profileDraft, name: event.target.value })} />
              </div>
              <label className="mt-7 flex items-center gap-2 text-sm">
                <AppCheckbox checked={profileDraft.active} onCheckedChange={(checked) => setProfileDraft({ ...profileDraft, active: checked })} ariaLabel="Perfil ativo" />
                Perfil ativo
              </label>
              <div className="grid gap-2 md:col-span-2">
                <Label>Descrição</Label>
                <Input value={profileDraft.description} onChange={(event) => setProfileDraft({ ...profileDraft, description: event.target.value })} />
              </div>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              {Object.entries(groupedPermissions).map(([module, items]) => (
                <div key={module} className="rounded-2xl border border-slate-200 p-3">
                  <h4 className="font-semibold text-slate-950">{module}</h4>
                  <div className="mt-2 grid gap-2">
                    {items.map((permission) => (
                      <label key={permission.key} className="flex items-start gap-2 rounded-xl p-2 text-sm hover:bg-slate-50">
                        <AppCheckbox
                          checked={profileDraft.permission_keys.includes(permission.key)}
                          onCheckedChange={() => toggleProfilePermission(permission.key)}
                          ariaLabel={permission.label}
                        />
                        <span>
                          <span className="font-medium text-slate-800">{permission.label}</span>
                          <span className="block text-[10px] text-slate-400">{permission.key}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap justify-between gap-2">
              <div>
                {profileDraft.id !== "new" && !profiles.find((profile) => profile.id === profileDraft.id)?.is_system && canWriteProfiles ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="text-red-600"
                    onClick={async () => {
                      if (profileDraft.id === "new" || !confirm("Excluir este perfil?")) return;
                      await api.deleteAccessProfile(profileDraft.id);
                      setProfileDraft(null);
                      await loadAdminData();
                    }}
                  >
                    <Trash2 className="h-4 w-4" /> Excluir perfil
                  </Button>
                ) : null}
              </div>
              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={() => setProfileDraft(null)}>Cancelar</Button>
                <Button type="button" onClick={() => void saveProfileDraft()} disabled={saving || !canWriteProfiles}>
                  <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar perfil"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
