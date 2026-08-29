"use client";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ModuleUserVisibilityEditor } from "@/components/workspace/module-user-visibility-editor";
import type { AuthUser } from "@/lib/types";

import type { VisibleModuleRow } from "./admin-shared";

type Props = {
  visibleModuleRows: VisibleModuleRow[];
  users: AuthUser[];
  saving: boolean;
  canWriteModules: boolean;
  onUpdateModuleVisibility: (moduleKey: string, profileId: number, visible: boolean) => void;
  onAddModuleUserOverride: (moduleKey: string, userId: number, visible: boolean) => void;
  onRemoveModuleUserOverride: (moduleKey: string, userId: number) => void;
};

export function ModulesPanel({
  visibleModuleRows,
  users,
  saving,
  canWriteModules,
  onUpdateModuleVisibility,
  onAddModuleUserOverride,
  onRemoveModuleUserOverride,
}: Props) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
        <h3 className="text-lg font-semibold text-slate-950">Módulos do ecossistema</h3>
        <Badge className="bg-emerald-50 text-emerald-700">{visibleModuleRows.filter((item) => item.status === "active").length} ativos</Badge>
      </div>
      <div className="overflow-x-auto p-5">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Módulo</TableHead>
              <TableHead>Rota</TableHead>
              <TableHead>Permissão mínima</TableHead>
              <TableHead>Visibilidade por perfil</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleModuleRows.map((module) => (
              <TableRow key={module.key}>
                <TableCell>
                  <div className="font-medium text-slate-950">{module.name}</div>
                  <div className="text-xs text-slate-500">{module.description}</div>
                </TableCell>
                <TableCell className="text-sm text-slate-600">{module.web_path}</TableCell>
                <TableCell className="text-xs text-slate-500">{module.required_permission}</TableCell>
                <TableCell className="min-w-[26rem]">
                  <div className="flex flex-wrap gap-2">
                    {module.profiles.map((profile) => (
                      <button
                        key={profile.profile_id}
                        type="button"
                        disabled={saving || !canWriteModules}
                        onClick={() => onUpdateModuleVisibility(module.key, profile.profile_id, !profile.visible)}
                        className={`rounded-xl border px-3 py-2 text-left text-xs transition ${
                          profile.visible
                            ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                            : "border-slate-200 bg-slate-100 text-slate-500"
                        } ${profile.has_required_permission ? "" : "opacity-60"}`}
                        title={profile.has_required_permission ? "Perfil tem a permissão mínima" : "Perfil não tem a permissão mínima"}
                      >
                        <span className="block font-semibold">{profile.profile_name}</span>
                        <span>{profile.visible ? "Visível" : "Oculto"} · {profile.has_required_permission ? "com permissão" : "sem permissão"}</span>
                      </button>
                    ))}
                  </div>
                  <ModuleUserVisibilityEditor
                    overrides={module.user_overrides}
                    users={users}
                    saving={saving}
                    disabled={saving || !canWriteModules}
                    onAdd={(userId, visible) => onAddModuleUserOverride(module.key, userId, visible)}
                    onRemove={(userId) => onRemoveModuleUserOverride(module.key, userId)}
                  />
                </TableCell>
                <TableCell>
                  <Badge className={module.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                    {module.status === "active" ? "Ativo" : module.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
