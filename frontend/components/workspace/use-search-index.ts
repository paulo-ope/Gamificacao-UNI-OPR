"use client";

import {
  Boxes,
  Headphones,
  Inbox,
  KeyRound,
  Mail,
  Radar,
  ShieldCheck,
  Trophy,
  UserCog,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { intelligenceCockpitApi } from "@/lib/intelligence-cockpit-api";
import { operationsApi, type OperationTeamConfiguration } from "@/lib/operations-api";
import type {
  AccessProfile,
  AdminPersonStructure,
  AdminWorkspaceModule,
  AuthUser,
  EcosystemPermission,
  PortalAccessRequest,
  PortalInvite,
  SupportIxcN1Attendant,
  SupportOpaFilterOption,
} from "@/lib/types";

export type SearchEntry = {
  href: string;
  label: string;
  group: string;
  icon: LucideIcon;
  /** Texto que a busca considera mas a lista não mostra (descrição, chave, e-mail...). */
  extra?: string;
  /** Telas cheias (TV/cockpit) abrem em outra aba, sem a barra lateral. */
  newTab?: boolean;
};

/** Um lugar do sistema em que a pessoa aparece - cada um é uma função (aba) que ela exerce. */
export type PersonDestination = {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
};

export type PersonRecord = {
  key: string;
  name: string;
  /** Texto buscável que a lista não mostra (e-mail, cargo, regional). */
  extra: string;
  destinations: PersonDestination[];
};

export const normalizeSearch = (value: string) =>
  value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR").trim();

type Dynamic = {
  profiles: AccessProfile[];
  ecosystemPermissions: EcosystemPermission[];
  adminModules: AdminWorkspaceModule[];
  users: AuthUser[];
  people: AdminPersonStructure[];
  invites: PortalInvite[];
  accessRequests: PortalAccessRequest[];
  cockpitPanels: Array<{ key: string; name: string }>;
  opaAttendants: SupportOpaFilterOption[];
  ixcN1Attendants: SupportIxcN1Attendant[];
  operationMembers: OperationTeamConfiguration["members"];
};

const EMPTY: Dynamic = {
  profiles: [],
  ecosystemPermissions: [],
  adminModules: [],
  users: [],
  people: [],
  invites: [],
  accessRequests: [],
  cockpitPanels: [],
  opaAttendants: [],
  ixcN1Attendants: [],
  operationMembers: [],
};

/**
 * Destinos que são DADOS (perfis, pessoas, painéis...) e não abas fixas. Carregados uma única vez,
 * na primeira abertura da busca, e só os que a permissão do usuário já libera nas telas de origem -
 * a mesma que a Administração e o UNI Intelligence exigem para listá-los. Falha em uma lista não
 * derruba as outras: a busca só fica sem aquele grupo.
 */
export function useDynamicSearchEntries(
  open: boolean,
  permissions: readonly string[],
): { entries: SearchEntry[]; people: PersonRecord[] } {
  const [data, setData] = useState<Dynamic>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const has = (permission: string) => permissions.includes(permission);
  const canProfiles = has("admin:roles:read");
  const canPermissions = has("admin:permissions:read");
  const canModules = has("admin:modules:read");
  const canUsers = has("admin:users:read");
  const canCockpit = has("intelligence:manage");
  const canSupport = has("support:read");
  const canOperationMembers = has("operations:manage_team_models") || has("operations:manage_own_team_members");

  useEffect(() => {
    if (!open || loaded) return;
    setLoaded(true);
    const load = <K extends keyof Dynamic>(enabled: boolean, key: K, request: () => Promise<Dynamic[K]>) => {
      if (!enabled) return;
      request()
        .then((value) => setData((current) => ({ ...current, [key]: value })))
        .catch(() => undefined);
    };
    load(canProfiles, "profiles", () => api.accessProfiles());
    load(canPermissions, "ecosystemPermissions", () => api.ecosystemPermissions());
    load(canModules, "adminModules", () => api.adminModules());
    load(canUsers, "users", () => api.users());
    load(canUsers, "people", () => api.adminPeopleStructure().then((structure) => structure.people));
    load(canUsers, "invites", () => api.listInvites());
    load(canUsers, "accessRequests", () => api.listAccessRequests());
    load(canSupport, "opaAttendants", () => api.supportOpaFilters().then((filters) => filters.attendants));
    // Atendentes do N1 no ano corrente: a lista depende do período, então o ano todo cobre quem
    // atendeu em qualquer mês (a tela do N1 não filtra por pessoa, o link abre a aba).
    load(canSupport, "ixcN1Attendants", () => {
      const today = new Date();
      const pad = (value: number) => String(value).padStart(2, "0");
      return api
        .supportIxcN1Summary({
          date_from: `${today.getFullYear()}-01-01`,
          date_to: `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`,
        })
        .then((summary) => summary.attendants);
    });
    load(canOperationMembers, "operationMembers", () => operationsApi.teamConfiguration().then((config) => config.members));
    load(canCockpit, "cockpitPanels", () =>
      intelligenceCockpitApi.listProfiles().then((rows) => rows.map((row) => ({ key: row.key, name: row.name }))),
    );
  }, [open, loaded, canProfiles, canPermissions, canModules, canUsers, canCockpit, canSupport, canOperationMembers]);

  const entries = useMemo(
    (): SearchEntry[] => [
      ...data.cockpitPanels.map((panel) => ({
        href: `/cockpit/${encodeURIComponent(panel.key)}`,
        label: `TV: ${panel.name}`,
        group: "UNI Intelligence · Painéis",
        icon: Radar,
        extra: panel.key,
        newTab: true,
      })),
      ...data.profiles.map((profile) => ({
        href: `/admin?tab=profiles&profile=${profile.id}`,
        label: profile.name,
        group: "Administração · Perfis",
        icon: ShieldCheck,
        extra: profile.description ?? "",
      })),
      ...data.ecosystemPermissions.map((permission) => ({
        href: "/admin?tab=permissions",
        label: permission.label,
        group: `Administração · Permissões · ${permission.module}`,
        icon: KeyRound,
        extra: `${permission.key} ${permission.description ?? ""}`,
      })),
      ...data.adminModules.map((module) => ({
        href: "/admin?tab=modules",
        label: module.name,
        group: "Administração · Módulos",
        icon: Boxes,
        extra: module.description ?? "",
      })),
    ],
    [data],
  );

  const canRanking = has("dashboard:read");
  const people = useMemo((): PersonRecord[] => {
    const byName = new Map<string, PersonRecord>();
    const record = (name: string, extra: string, destination: PersonDestination) => {
      const key = normalizeSearch(name);
      if (!key) return;
      const current = byName.get(key) ?? { key, name: name.trim(), extra: "", destinations: [] };
      current.extra = `${current.extra} ${extra}`.trim();
      if (!current.destinations.some((item) => item.href === destination.href)) current.destinations.push(destination);
      byName.set(key, current);
    };
    for (const person of data.people) {
      record(person.name, `${person.role} ${person.regional}`, {
        href: `/admin?tab=structure&person=${encodeURIComponent(person.name)}`,
        label: "Administração · Pessoas",
        description: "Estrutura e liderança",
        icon: UserCog,
      });
      if (canRanking) {
        record(person.name, "", {
          href: `/gamificacao?tab=ranking&sub=collaborators&q=${encodeURIComponent(person.name)}`,
          label: "Gamificação · Ranking de colaboradores",
          description: "Resultado final no período",
          icon: Trophy,
        });
      }
    }
    for (const user of data.users) {
      const portal = Boolean(user.collaborator_id);
      record(user.name, user.email, {
        href: `/admin?tab=${portal ? "portal_accounts" : "internal_accounts"}&user=${user.id}`,
        label: `Administração · ${portal ? "Conta do Portal" : "Conta interna"}`,
        description: user.email,
        icon: portal ? UserRound : Users,
      });
    }
    for (const invite of data.invites) {
      record(invite.collaborator_name || invite.email, invite.email, {
        href: "/admin?tab=invites",
        label: "Administração · Convites",
        description: invite.email,
        icon: Mail,
      });
    }
    for (const request of data.accessRequests) {
      record(request.name, request.email, {
        href: "/admin?tab=access_requests",
        label: "Administração · Solicitações de acesso",
        description: request.email,
        icon: Inbox,
      });
    }
    for (const attendant of data.opaAttendants) {
      record(attendant.label, "", {
        href: `/suporte?tab=data&attendant_id=${encodeURIComponent(attendant.value)}`,
        label: "SGP Suporte · Atendimentos",
        description: "Atendimentos deste atendente no OPA Suite",
        icon: Headphones,
      });
    }
    for (const member of data.operationMembers) {
      record(member.responsible_name, member.regionals.join(" "), {
        href: `/operacao?tab=teams&sub=members&q=${encodeURIComponent(member.responsible_name)}`,
        label: "Operação Analítica · Config · Colaboradores e vínculos",
        description: member.regionals.length ? `Modelo de equipe · ${member.regionals.join(", ")}` : "Modelo de equipe aplicado ao responsável",
        icon: Users,
      });
    }
    for (const attendant of data.ixcN1Attendants) {
      record(attendant.name, "", {
        href: "/suporte?tab=ixc_n1",
        label: "SGP Suporte · Atendimento Suporte Interno N1",
        description: `${attendant.total} atendimentos no ano`,
        icon: Headphones,
      });
    }
    return Array.from(byName.values()).sort((left, right) => left.name.localeCompare(right.name, "pt-BR"));
  }, [data, canRanking]);

  return { entries, people };
}
