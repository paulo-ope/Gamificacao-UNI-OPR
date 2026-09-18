"use client";

import { KeyRound, Save } from "lucide-react";

import { AppCheckbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MultiSelect } from "@/components/ui/multi-select";
import type { AccessProfile } from "@/lib/types";

import type { UserDraft } from "./admin-shared";

type Props = {
  userDraft: UserDraft;
  profiles: AccessProfile[];
  operationRegionals: string[];
  saving: boolean;
  onChange: (patch: Partial<UserDraft>) => void;
  onCancel: () => void;
  onSave: () => void;
  /** Ausente (ou usuário ainda não salvo) esconde o botão - exceção individual precisa de um
   *  usuário já existente para ter um `id` de destino. */
  onOpenPermissionOverrides?: () => void;
};

export function UserEditorDrawer({
  userDraft,
  profiles,
  operationRegionals,
  saving,
  onChange,
  onCancel,
  onSave,
  onOpenPermissionOverrides,
}: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-4">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-5 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-semibold text-slate-950">{userDraft.id === "new" ? "Novo usuário" : "Editar usuário"}</h3>
          {userDraft.id !== "new" && onOpenPermissionOverrides ? (
            <Button type="button" size="sm" variant="outline" onClick={onOpenPermissionOverrides}>
              <KeyRound className="h-3.5 w-3.5" /> Permissões individuais
            </Button>
          ) : null}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="grid gap-2 md:col-span-2">
            <Label>Nome</Label>
            <Input value={userDraft.name} onChange={(event) => onChange({ name: event.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>E-mail</Label>
            <Input type="email" value={userDraft.email} onChange={(event) => onChange({ email: event.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>{userDraft.id === "new" ? "Senha inicial" : "Nova senha"}</Label>
            <Input
              type="password"
              value={userDraft.password}
              placeholder={userDraft.id === "new" ? "Obrigatória" : "Em branco mantém a atual"}
              onChange={(event) => onChange({ password: event.target.value })}
            />
          </div>
          <div className="grid gap-2 md:col-span-2">
            <Label>Regionais permitidas</Label>
            <MultiSelect
              values={userDraft.managed_regionals}
              options={Array.from(new Set([...operationRegionals, ...userDraft.managed_regionals])).sort((left, right) => left.localeCompare(right, "pt-BR"))}
              placeholder="Sem restrição regional"
              ariaLabel="Selecionar regionais permitidas"
              onChange={(managed_regionals) => onChange({ managed_regionals })}
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
                      onChange({
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
            <AppCheckbox checked={userDraft.active} onCheckedChange={(checked) => onChange({ active: checked })} ariaLabel="Usuário ativo" />
            Usuário ativo
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>Cancelar</Button>
          <Button type="button" onClick={onSave} disabled={saving}>
            <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar"}
          </Button>
        </div>
      </div>
    </div>
  );
}
