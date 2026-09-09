"use client";

import { Settings2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ModuleUserVisibilityEditor } from "@/components/workspace/module-user-visibility-editor";
import type { AuthUser } from "@/lib/types";

import type { VisibleModuleRow } from "./admin-shared";

const STATUS_LABELS: Record<string, string> = {
  active: "Ativo",
  planned: "Planejado",
  disabled: "Desativado",
};

const STATUS_BADGE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  planned: "bg-blue-50 text-blue-700",
  disabled: "bg-slate-100 text-slate-600",
};

type Props = {
  visibleModuleRows: VisibleModuleRow[];
  users: AuthUser[];
  saving: boolean;
  canWriteModules: boolean;
  onUpdateModuleVisibility: (moduleKey: string, profileId: number, visible: boolean) => void;
  onAddModuleUserOverride: (moduleKey: string, userId: number, visible: boolean) => void;
  onRemoveModuleUserOverride: (moduleKey: string, userId: number) => void;
  onOpenModuleSettings: (module: VisibleModuleRow) => void;
};

export function ModulesPanel({
  visibleModuleRows,
  users,
  saving,
  canWriteModules,
  onUpdateModuleVisibility,
  onAddModuleUserOverride,
  onRemoveModuleUserOverride,
  onOpenModuleSettings,
}: Props) {
  return (
    <div className="min-w-0 rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-2 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-950">Módulos do ecossistema</h3>
          <p className="mt-1 text-sm text-slate-500">
            Nome, descrição, status e ordem são parametrizáveis. Rota, prefixo de API e permissão mínima
            vêm do código — mudá-los aqui deixaria o módulo visível para quem as rotas dele recusam.
          </p>
        </div>
        <Badge className="shrink-0 bg-emerald-50 text-emerald-700">
          {visibleModuleRows.filter((item) => item.status === "active").length} ativos
        </Badge>
      </div>
      <div className="overflow-x-auto p-5">
        <Table className="min-w-[1000px]">
          <TableHeader>
            <TableRow>
              <TableHead>Módulo</TableHead>
              <TableHead>Rota</TableHead>
              <TableHead>Permissão mínima</TableHead>
              <TableHead>Visibilidade por perfil</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Parametrizar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleModuleRows.map((module) => (
              <TableRow key={module.key}>
                <TableCell>
                  <div className="flex items-center gap-1.5 font-medium text-slate-950">
                    {module.name}
                    {module.customized ? (
                      <span
                        className="rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700"
                        title={`Ajustado pela tela. Padrão do código: ${module.default_name}`}
                      >
                        Ajustado
                      </span>
                    ) : null}
                  </div>
                  <div className="text-xs text-slate-500">{module.description}</div>
                  <div className="mt-0.5 text-[11px] text-slate-400">
                    {module.key} · ordem {module.sort_order}
                  </div>
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
                  <Badge className={STATUS_BADGE[module.status] || "bg-slate-100 text-slate-600"}>
                    {STATUS_LABELS[module.status] || module.status}
                  </Badge>
                  {module.status !== module.default_status ? (
                    <div className="mt-1 text-[11px] text-slate-400">
                      padrão: {STATUS_LABELS[module.default_status] || module.default_status}
                    </div>
                  ) : null}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    {canWriteModules ? (
                      <Button type="button" size="sm" variant="outline" disabled={saving} onClick={() => onOpenModuleSettings(module)}>
                        <Settings2 className="h-3.5 w-3.5" /> Editar
                      </Button>
                    ) : (
                      <span className="text-xs text-slate-400">sem permissão</span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
