"use client";

import { useEffect, useState } from "react";

import { api, peekSessionCache } from "@/lib/api";
import { workspaceModules } from "@/lib/module-registry";
import type { AuthUser, WorkspaceVisibleModule } from "@/lib/types";

/**
 * Módulos que este usuário pode abrir.
 *
 * Prefere a resposta do backend (`/workspace/modules`, que já aplica visibilidade por perfil e
 * por usuário) e cai no registro local do frontend só enquanto ela não chega ou falha - o mesmo
 * comportamento que a tela inicial já tinha antes de a navegação virar casca compartilhada. A
 * autorização efetiva continua no backend: isto é descoberta visual, não controle de acesso.
 */
export function useVisibleModules(user: AuthUser | null) {
  // Mesma razão do `useWorkspaceAuth`: sem semear do cache, a barra lateral desenhava primeiro o
  // fallback do registro local e depois trocava pela resposta do backend, a cada navegação.
  const [visibleModules, setVisibleModules] = useState<WorkspaceVisibleModule[] | null>(
    () => peekSessionCache<WorkspaceVisibleModule[]>("/workspace/modules"),
  );

  useEffect(() => {
    if (!user) {
      setVisibleModules(null);
      return;
    }
    let active = true;
    api
      .workspaceModules()
      .then((items) => {
        if (active) setVisibleModules(items);
      })
      .catch(() => {
        if (active) setVisibleModules(null);
      });
    return () => {
      active = false;
    };
  }, [user]);

  if (!user) return [];
  if (visibleModules) return visibleModules;
  return workspaceModules
    .filter((module) => module.status === "active" && user.permissions.includes(module.requiredPermission))
    .map((module) => ({
      key: module.key,
      name: module.name,
      description: module.description,
      web_path: module.webPath,
      api_prefix: module.apiPrefix,
      required_permission: module.requiredPermission,
      status: module.status,
    })) as WorkspaceVisibleModule[];
}
