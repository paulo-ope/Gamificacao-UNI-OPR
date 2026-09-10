"use client";

import { useMemo, useState } from "react";
import { RotateCcw, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBlockQuery } from "@/hooks/use-block-query";
import { api } from "@/lib/api";
import type { EcosystemPermission, UserPermissionOverrideEffect } from "@/lib/types";

import { permissionGroups } from "./admin-shared";

type Props = {
  userId: number;
  userName: string;
  /** Catálogo já carregado pela página (perfis + permissões próprias) - evita buscar de novo. */
  catalog: EcosystemPermission[];
  canWrite: boolean;
  onClose: () => void;
  /** A página recarrega a lista de usuários: `AuthUser.permissions` (calculado no backend a
   *  partir de `permissions_for_user`) muda com cada exceção aplicada. */
  onChanged: () => void;
};

/**
 * Concede ou nega UMA permissão específica desta pessoa, sem mexer no perfil dela.
 *
 * Pedido do usuário (2026-09-09): dar acesso pontual sem precisar criar um perfil só pra uma
 * pessoa, nem mexer no perfil dela (compartilhado com outras pessoas). Negação individual sempre
 * vence o que o perfil concede; concessão individual soma ao que o perfil já dá - a mesma regra
 * que `permissions_for_user` aplica no backend, então todo o resto do sistema (login, cada rota,
 * MCP) já respeita a exceção sem precisar de nenhuma mudança própria.
 */
export function UserPermissionOverridesDrawer({ userId, userName, catalog, canWrite, onClose, onChanged }: Props) {
  const [reloadToken, setReloadToken] = useState(0);
  const [search, setSearch] = useState("");
  const [busyPermission, setBusyPermission] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const overview = useBlockQuery(() => api.getUserPermissionOverview(userId), [userId, reloadToken]);

  const overridesByPermission = useMemo(() => {
    const map = new Map<string, NonNullable<typeof overview.data>["overrides"][number]>();
    (overview.data?.overrides ?? []).forEach((item) => map.set(item.permission, item));
    return map;
  }, [overview.data]);

  const groups = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    const filtered = term
      ? catalog.filter((item) => `${item.module} ${item.label} ${item.key}`.toLocaleLowerCase("pt-BR").includes(term))
      : catalog;
    return permissionGroups(filtered);
  }, [catalog, search]);

  async function apply(permission: string, effect: UserPermissionOverrideEffect) {
    setBusyPermission(permission);
    setActionError(null);
    try {
      const currentReason = overridesByPermission.get(permission)?.reason ?? null;
      await api.setUserPermissionOverride(userId, permission, { effect, reason: currentReason });
      setReloadToken((current) => current + 1);
      onChanged();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Não foi possível aplicar a exceção.");
    } finally {
      setBusyPermission(null);
    }
  }

  async function revert(permission: string) {
    setBusyPermission(permission);
    setActionError(null);
    try {
      await api.deleteUserPermissionOverride(userId, permission);
      setReloadToken((current) => current + 1);
      onChanged();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Não foi possível remover a exceção.");
    } finally {
      setBusyPermission(null);
    }
  }

  async function saveReason(permission: string, effect: UserPermissionOverrideEffect, reason: string) {
    setBusyPermission(permission);
    setActionError(null);
    try {
      await api.setUserPermissionOverride(userId, permission, { effect, reason: reason || null });
      setReloadToken((current) => current + 1);
    } catch (reason_) {
      setActionError(reason_ instanceof Error ? reason_.message : "Não foi possível salvar o motivo.");
    } finally {
      setBusyPermission(null);
    }
  }

  const overrideCount = overview.data?.overrides.length ?? 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/35 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="user-permission-overrides-title"
    >
      <div className="flex h-[100dvh] w-full flex-col overflow-hidden bg-white shadow-xl sm:h-[92vh] sm:max-w-4xl sm:rounded-2xl">
        <div className="shrink-0 border-b border-slate-200 bg-white px-4 py-4 sm:px-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 id="user-permission-overrides-title" className="text-lg font-semibold text-slate-950">
                Permissões individuais: {userName}
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                {overview.loading ? "Carregando..." : `${overrideCount} exceção(ões) sobre o que o perfil já concede`}
              </p>
            </div>
            <Button type="button" size="icon" variant="ghost" aria-label="Fechar permissões individuais" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
          <p className="mt-3 max-w-2xl text-xs text-slate-500">
            Conceda ou negue uma permissão específica desta pessoa sem mexer no perfil dela (que pode
            ser compartilhado com outras). Negação individual sempre vence o que o perfil dá;
            concessão individual soma ao que o perfil já dá.
          </p>
        </div>

        <div className="border-b border-slate-200 px-4 py-3 sm:px-5">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={search}
              className="pl-9"
              placeholder="Buscar módulo ou permissão"
              aria-label="Buscar permissão"
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        {actionError ? (
          <p className="mx-4 mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 sm:mx-5" role="alert">
            {actionError}
          </p>
        ) : null}
        {overview.error ? (
          <p className="mx-4 mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 sm:mx-5" role="alert">
            {overview.error}
          </p>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          {overview.loading ? (
            <p className="py-16 text-center text-sm text-slate-500" aria-busy="true">
              Carregando permissões...
            </p>
          ) : (
            <div className="grid gap-4">
              {Object.entries(groups).map(([module, items]) => (
                <section key={module} aria-labelledby={`user-permission-group-${module}`}>
                  <h4 id={`user-permission-group-${module}`} className="text-sm font-semibold text-slate-950">
                    {module}
                  </h4>
                  <div className="mt-2 grid gap-1.5">
                    {items.map((permission) => {
                      const override = overridesByPermission.get(permission.key);
                      const hasProfile = overview.data?.profile_permissions.includes(permission.key) ?? false;
                      const effective = overview.data?.effective_permissions.includes(permission.key) ?? false;
                      const busy = busyPermission === permission.key;
                      return (
                        <div key={permission.key} className="rounded-lg border border-slate-200 p-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="font-medium text-slate-800">{permission.label}</span>
                                {effective ? (
                                  <Badge className="bg-emerald-50 text-emerald-700">Tem acesso</Badge>
                                ) : (
                                  <Badge className="border border-slate-200 bg-white text-slate-500">Sem acesso</Badge>
                                )}
                                {hasProfile ? <span className="text-[11px] text-slate-400">perfil concede</span> : null}
                              </div>
                              <span className="block break-all text-[11px] text-slate-400">{permission.key}</span>
                            </div>
                            {canWrite ? (
                              <div className="flex shrink-0 gap-1.5">
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={override?.effect === "grant" ? "default" : "outline"}
                                  disabled={busy}
                                  onClick={() => apply(permission.key, "grant")}
                                >
                                  Conceder
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={override?.effect === "deny" ? "destructive" : "outline"}
                                  disabled={busy}
                                  onClick={() => apply(permission.key, "deny")}
                                >
                                  Negar
                                </Button>
                                {override ? (
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    disabled={busy}
                                    title="Voltar ao que o perfil concede"
                                    aria-label={`Remover exceção de ${permission.label}`}
                                    onClick={() => revert(permission.key)}
                                  >
                                    <RotateCcw className="h-3.5 w-3.5" />
                                  </Button>
                                ) : null}
                              </div>
                            ) : override ? (
                              <Badge className={override.effect === "grant" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}>
                                {override.effect === "grant" ? "Concedida individualmente" : "Negada individualmente"}
                              </Badge>
                            ) : null}
                          </div>
                          {override && canWrite ? (
                            <Input
                              key={`${permission.key}-${override.updated_at}`}
                              defaultValue={override.reason ?? ""}
                              placeholder="Motivo (opcional)"
                              className="mt-2 h-8 text-xs"
                              aria-label={`Motivo da exceção em ${permission.label}`}
                              onBlur={(event) => {
                                const value = event.target.value.trim();
                                if (value !== (override.reason ?? "")) saveReason(permission.key, override.effect, value);
                              }}
                            />
                          ) : override?.reason ? (
                            <p className="mt-1 text-xs text-slate-500">Motivo: {override.reason}</p>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </section>
              ))}
              {Object.keys(groups).length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-500">
                  Nenhuma permissão encontrada para a busca informada.
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
