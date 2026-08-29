"use client";

import { Plus, ShieldCheck, UserCog } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AccessProfile } from "@/lib/types";

import { blankProfileDraft, type ProfileDraft } from "./admin-shared";

type Props = {
  profiles: AccessProfile[];
  canWriteProfiles: boolean;
  onOpenProfileEditor: (draft: ProfileDraft) => void;
};

export function ProfilesPanel({ profiles, canWriteProfiles, onOpenProfileEditor }: Props) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
        <div>
          <h3 className="text-lg font-semibold text-slate-950">Perfis de acesso</h3>
          <p className="text-sm text-slate-500">Monte grupos de permissões por módulo.</p>
        </div>
        {canWriteProfiles ? (
          <Button type="button" onClick={() => onOpenProfileEditor(blankProfileDraft())}>
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
              onOpenProfileEditor({
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
              <Badge className="border border-slate-200 bg-white text-slate-600">{profile.permission_keys.length} permissões</Badge>
              <Badge className="border border-slate-200 bg-white text-slate-600">{profile.user_count} usuários</Badge>
              <Badge className={profile.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                {profile.active ? "Ativo" : "Inativo"}
              </Badge>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
