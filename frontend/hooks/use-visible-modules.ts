"use client";

import { useEffect, useState } from "react";

import { api, invalidateSessionCache, peekSessionCache } from "@/lib/api";
import { workspaceModules } from "@/lib/module-registry";
import type { AuthUser, WorkspaceVisibleModule } from "@/lib/types";

const MODULES_CHANGED_EVENT = "uni:workspace-modules-changed";

/**
 * Avisa a casca de navegação de que a lista de módulos mudou (nome, descrição, status ou ordem
 * ajustados na Administração).
 *
 * Sem isto, a tela que fez a mudança atualizava só a si mesma: a barra lateral seguia com o nome
 * antigo até o cache de 30s de `/workspace/modules` expirar, e a impressão era de que salvar não
 * tinha efeito (achado real na verificação ao vivo, 2026-09-09).
 */
export function notifyWorkspaceModulesChanged() {
  invalidateSessionCache("/workspace/modules");
  if (typeof window !== "undefined") window.dispatchEvent(new Event(MODULES_CHANGED_EVENT));
}

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
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    function onModulesChanged() {
      setReloadToken((current) => current + 1);
    }
    window.addEventListener(MODULES_CHANGED_EVENT, onModulesChanged);
    return () => window.removeEventListener(MODULES_CHANGED_EVENT, onModulesChanged);
  }, []);

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
  }, [user, reloadToken]);

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
