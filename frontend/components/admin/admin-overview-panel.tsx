"use client";

import Link from "next/link";
import { Boxes, ExternalLink, Inbox, KeyRound, Mail, PlugZap, Settings2, ShieldCheck, UserCog } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AccessProfile, AdminPeopleStructure, AuthUser, EcosystemPermission, PortalAccessRequest, PortalInvite } from "@/lib/types";

import { parameterModuleLinks, type AdminTab, type VisibleModuleRow } from "./admin-shared";

type Props = {
  users: AuthUser[];
  activeUsers: number;
  profiles: AccessProfile[];
  permissions: EcosystemPermission[];
  invites: PortalInvite[];
  accessRequests: PortalAccessRequest[];
  peopleStructure: AdminPeopleStructure | null;
  visibleModuleRows: VisibleModuleRow[];
  permissionModuleRows: Array<{ module: string; count: number; writeCount: number }>;
  onNavigate: (tab: AdminTab) => void;
};

export function AdminOverviewPanel({
  users,
  activeUsers,
  profiles,
  permissions,
  invites,
  accessRequests,
  peopleStructure,
  visibleModuleRows,
  permissionModuleRows,
  onNavigate,
}: Props) {
  const pendingInvites = invites.filter((item) => item.status === "pending").length;
  const pendingAccessRequests = accessRequests.filter((item) => item.status === "pending").length;
  const pendingStructureReview = peopleStructure?.summary.pending_review || 0;

  return (
    <div className="grid gap-5">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-600">Controle central</p>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950">Administração do ecossistema</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              Controle unificado para acesso, estrutura, módulos, parametrização e auditoria.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4">
            <div className="rounded-2xl bg-slate-50 px-4 py-3">
              <p className="text-lg font-bold text-slate-950">{users.length}</p>
              <p className="text-slate-500">Usuários</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-3">
              <p className="text-lg font-bold text-slate-950">{activeUsers}</p>
              <p className="text-slate-500">Ativos</p>
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

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-950">Pendências</h3>
        <p className="mt-1 text-sm text-slate-500">Atalhos para o que ainda depende de uma decisão do admin.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <button
            type="button"
            onClick={() => onNavigate("invites")}
            className="rounded-2xl border border-slate-200 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/40"
          >
            <div className="flex items-center justify-between gap-2">
              <Mail className="h-4 w-4 text-blue-600" />
              <Badge className={pendingInvites ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"}>{pendingInvites}</Badge>
            </div>
            <p className="mt-3 font-semibold text-slate-950">Convites pendentes</p>
            <p className="mt-1 text-xs text-slate-500">Aguardando aceite de quem foi convidado.</p>
          </button>
          <button
            type="button"
            onClick={() => onNavigate("access_requests")}
            className="rounded-2xl border border-slate-200 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/40"
          >
            <div className="flex items-center justify-between gap-2">
              <Inbox className="h-4 w-4 text-blue-600" />
              <Badge className={pendingAccessRequests ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"}>{pendingAccessRequests}</Badge>
            </div>
            <p className="mt-3 font-semibold text-slate-950">Solicitações de acesso</p>
            <p className="mt-1 text-xs text-slate-500">Aguardando aprovação ou rejeição.</p>
          </button>
          <button
            type="button"
            onClick={() => onNavigate("structure")}
            className="rounded-2xl border border-slate-200 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/40"
          >
            <div className="flex items-center justify-between gap-2">
              <UserCog className="h-4 w-4 text-blue-600" />
              <Badge className={pendingStructureReview ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"}>{pendingStructureReview}</Badge>
            </div>
            <p className="mt-3 font-semibold text-slate-950">Estrutura pendente</p>
            <p className="mt-1 text-xs text-slate-500">Pessoas sem revisão de estrutura completa.</p>
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-blue-600" />
              <h3 className="text-lg font-semibold text-slate-950">Central de parametrizações</h3>
            </div>
            <p className="mt-1 text-sm text-slate-500">Governança de módulos, acessos, integrações e regras operacionais.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => onNavigate("profiles")}>
              <ShieldCheck className="h-4 w-4" /> Perfis de acesso
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onNavigate("permissions")}>
              <KeyRound className="h-4 w-4" /> Permissões
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onNavigate("modules")}>
              <Boxes className="h-4 w-4" /> Módulos
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onNavigate("integrations")}>
              <PlugZap className="h-4 w-4" /> Integrações
            </Button>
          </div>
        </div>
        <div className="grid border-b border-slate-200 bg-slate-50 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Módulos ativos", value: visibleModuleRows.filter((item) => item.status === "active").length },
            { label: "Áreas de permissão", value: permissionModuleRows.length },
            { label: "Permissões catalogadas", value: permissions.length },
            { label: "Perfis configurados", value: profiles.length },
          ].map((item) => (
            <div key={item.label} className="border-b border-slate-200 px-5 py-4 last:border-b-0 sm:[&:nth-child(odd)]:border-r xl:border-b-0 xl:border-r xl:last:border-r-0">
              <p className="text-2xl font-semibold text-slate-950">{item.value}</p>
              <p className="text-xs text-slate-500">{item.label}</p>
            </div>
          ))}
        </div>
        <div className="p-5">
          <div className="mb-4">
            <h4 className="font-semibold text-slate-950">Regras por domínio</h4>
            <p className="mt-1 text-sm text-slate-500">Cada módulo mantém suas regras de negócio e validações no próprio contexto operacional.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {parameterModuleLinks(visibleModuleRows).map((item) => (
              <Link
                key={item.key}
                href={item.path}
                className="group rounded-lg border border-slate-200 p-4 transition hover:border-blue-300 hover:bg-blue-50/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <h4 className="font-semibold text-slate-950">{item.module}</h4>
                  <ExternalLink className="h-4 w-4 shrink-0 text-slate-400 transition group-hover:text-blue-600" />
                </div>
                <p className="mt-2 text-sm text-slate-600">{item.owner}</p>
                <Badge className="mt-3 border border-slate-200 bg-white text-slate-600">{item.path}</Badge>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
