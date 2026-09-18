"use client";

import { useState } from "react";
import { Save, Search, Trash2, X } from "lucide-react";

import { AppCheckbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AccessProfile, EcosystemPermission } from "@/lib/types";

import type { ProfileDraft } from "./admin-shared";

type Props = {
  profileDraft: ProfileDraft;
  profiles: AccessProfile[];
  canWriteProfiles: boolean;
  saving: boolean;
  permissionSearch: string;
  groupedPermissions: Record<string, EcosystemPermission[]>;
  filteredPermissionGroups: Record<string, EcosystemPermission[]>;
  onChange: (patch: Partial<ProfileDraft>) => void;
  onPermissionSearchChange: (value: string) => void;
  onTogglePermission: (permission: ProfileDraft["permission_keys"][number]) => void;
  onSetModulePermissions: (modulePermissions: EcosystemPermission[], selected: boolean) => void;
  onClose: () => void;
  onSave: () => void;
  /** `reassignProfileId` é obrigatório quando o perfil tem pessoas vinculadas - ver
   *  `delete_access_profile` no backend: sem destino, elas cairiam no papel legado. */
  onDelete: (reassignProfileId: number | null) => void;
};

export function ProfileEditorDrawer({
  profileDraft,
  profiles,
  canWriteProfiles,
  saving,
  permissionSearch,
  groupedPermissions,
  filteredPermissionGroups,
  onChange,
  onPermissionSearchChange,
  onTogglePermission,
  onSetModulePermissions,
  onClose,
  onSave,
  onDelete,
}: Props) {
  const [reassignProfileId, setReassignProfileId] = useState<string>("");

  // Perfil do sistema passou a ser excluível (2026-09-09): o bloqueio existia porque a semeadura o
  // recriava no restart do backend, então "excluir" era uma ilusão. O que resta bloqueado (último
  // perfil que administra acesso) chega como texto do backend, e a tela EXPLICA em vez de esconder
  // o botão - "não consigo excluir e não sei por quê" era o pedido original.
  const currentProfile = profiles.find((profile) => profile.id === profileDraft.id);
  const canDeleteThisProfile = profileDraft.id !== "new" && canWriteProfiles;
  const deleteBlockedReason = currentProfile?.delete_blocked_reason || null;
  const linkedUsers = currentProfile?.user_count || 0;
  const reassignOptions = profiles.filter((profile) => profile.active && profile.id !== profileDraft.id);
  const needsReassign = linkedUsers > 0;
  const deleteDisabled = saving || Boolean(deleteBlockedReason) || (needsReassign && !reassignProfileId);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/35 sm:p-4" role="dialog" aria-modal="true" aria-labelledby="profile-editor-title">
      <div className="flex h-[100dvh] w-full flex-col overflow-hidden bg-white shadow-xl sm:h-[92vh] sm:max-w-5xl sm:rounded-2xl">
        <div className="shrink-0 border-b border-slate-200 bg-white px-4 py-4 sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 id="profile-editor-title" className="text-lg font-semibold text-slate-950">
                {profileDraft.id === "new" ? "Novo perfil de acesso" : `Editar perfil: ${profileDraft.name}`}
              </h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>{profileDraft.permission_keys.length} permissões selecionadas</span>
                <span aria-hidden="true">·</span>
                <span>{profileDraft.active ? "Perfil ativo" : "Perfil inativo"}</span>
              </div>
            </div>
            <Button type="button" size="icon" variant="ghost" aria-label="Fechar editor de perfil" title="Fechar" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
          <section aria-labelledby="profile-identification-title" className="rounded-lg border border-slate-200 p-4">
            <h4 id="profile-identification-title" className="font-semibold text-slate-950">Identificação do perfil</h4>
            <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
              <div className="grid gap-2">
                <Label>Nome do perfil</Label>
                <Input value={profileDraft.name} onChange={(event) => onChange({ name: event.target.value })} />
              </div>
              <label className="flex items-center gap-2 self-end rounded-md border border-slate-200 px-3 py-2.5 text-sm">
                <AppCheckbox
                  checked={profileDraft.active}
                  disabled={!canWriteProfiles}
                  onCheckedChange={(checked) => onChange({ active: checked })}
                  ariaLabel="Perfil ativo"
                />
                Perfil ativo
              </label>
              <div className="grid gap-2 md:col-span-2">
                <Label>Descrição</Label>
                <Input value={profileDraft.description} onChange={(event) => onChange({ description: event.target.value })} />
              </div>
            </div>
          </section>

          <section aria-labelledby="profile-permissions-title" className="mt-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <div>
                <h4 id="profile-permissions-title" className="font-semibold text-slate-950">Permissões por módulo</h4>
                <p className="mt-1 text-sm text-slate-500">Localize uma ação ou selecione o conjunto completo de um módulo.</p>
              </div>
              <div className="relative w-full md:max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={permissionSearch}
                  className="pl-9"
                  placeholder="Buscar módulo ou permissão"
                  aria-label="Buscar módulo ou permissão"
                  onChange={(event) => onPermissionSearchChange(event.target.value)}
                />
              </div>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {Object.entries(filteredPermissionGroups).map(([module, items]) => {
                const modulePermissions = groupedPermissions[module] || items;
                const bulkModulePermissions = modulePermissions.filter((permission) => !permission.sensitive);
                const selectedCount = modulePermissions.filter((permission) => profileDraft.permission_keys.includes(permission.key)).length;
                const bulkSelectedCount = bulkModulePermissions.filter((permission) => profileDraft.permission_keys.includes(permission.key)).length;
                const allBulkSelected = bulkModulePermissions.length > 0 && bulkSelectedCount === bulkModulePermissions.length;
                return (
                  <div key={module} className="overflow-hidden rounded-lg border border-slate-200">
                    <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-3 py-2.5">
                      <div className="min-w-0">
                        <h5 className="truncate text-sm font-semibold text-slate-950">{module}</h5>
                        <p className="text-xs text-slate-500">{selectedCount} de {modulePermissions.length} selecionadas</p>
                      </div>
                      {bulkModulePermissions.length > 0 ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={!canWriteProfiles}
                          onClick={() => onSetModulePermissions(modulePermissions, !allBulkSelected)}
                        >
                          {allBulkSelected ? "Limpar módulo" : "Selecionar módulo"}
                        </Button>
                      ) : null}
                    </div>
                    <div className="grid gap-1 p-2">
                      {items.map((permission) => (
                        <label key={permission.key} className="flex items-start gap-2 rounded-md p-2 text-sm hover:bg-slate-50">
                          <AppCheckbox
                            checked={profileDraft.permission_keys.includes(permission.key)}
                            disabled={!canWriteProfiles}
                            onCheckedChange={() => onTogglePermission(permission.key)}
                            ariaLabel={permission.label}
                          />
                          <span className="min-w-0">
                            <span className="flex flex-wrap items-center gap-1.5 font-medium text-slate-800">
                              {permission.label}
                              {permission.custom ? (
                                <span
                                  className="rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700"
                                  title="Permissão criada na aba Permissões, não declarada em código."
                                >
                                  Própria
                                </span>
                              ) : null}
                              {permission.sensitive ? (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                                  Sensível
                                </span>
                              ) : null}
                            </span>
                            <span className="block break-all text-[11px] text-slate-400">{permission.key}</span>
                            {permission.sensitive ? (
                              <span className="block text-[11px] text-amber-700">
                                Fora do "Selecionar módulo" - exige marcar aqui, individualmente.
                              </span>
                            ) : null}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            {Object.keys(filteredPermissionGroups).length === 0 ? (
              <div className="mt-4 rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-500">
                Nenhuma permissão encontrada para a busca informada.
              </div>
            ) : null}
          </section>
        </div>

        <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="grid gap-2">
              {canDeleteThisProfile ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    {needsReassign && !deleteBlockedReason ? (
                      <label className="flex items-center gap-2 text-xs text-slate-600">
                        <span>
                          Mover {linkedUsers} {linkedUsers === 1 ? "pessoa" : "pessoas"} para
                        </span>
                        <select
                          value={reassignProfileId}
                          aria-label="Perfil que recebe as pessoas deste perfil"
                          className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm"
                          onChange={(event) => setReassignProfileId(event.target.value)}
                        >
                          <option value="">Escolher perfil...</option>
                          {reassignOptions.map((profile) => (
                            <option key={profile.id} value={profile.id}>
                              {profile.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      className="text-red-600"
                      disabled={deleteDisabled}
                      title={deleteBlockedReason || undefined}
                      onClick={() => onDelete(reassignProfileId ? Number(reassignProfileId) : null)}
                    >
                      <Trash2 className="h-4 w-4" /> Excluir perfil
                    </Button>
                  </div>
                  {deleteBlockedReason ? (
                    <p className="max-w-xl text-xs text-amber-700">{deleteBlockedReason}</p>
                  ) : currentProfile?.is_system ? (
                    <p className="max-w-xl text-xs text-slate-500">
                      Perfil do sistema: excluir é permitido e não é desfeito no próximo restart, mas ele
                      não volta sozinho — só recriando à mão.
                    </p>
                  ) : null}
                </>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
              <Button type="button" onClick={onSave} disabled={saving || !canWriteProfiles}>
                <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar perfil"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
