import { describe, expect, it } from "vitest";

import { workspaceModules } from "@/lib/module-registry";

import type { AccessProfile, AuthUser } from "@/lib/types";

import { ADMIN_NAV_ITEMS, MODULE_PARAMETER_OWNERS, parameterModuleLinks, profileNames, type VisibleModuleRow } from "./admin-shared";

function row(overrides: Partial<VisibleModuleRow> & { key: string }): VisibleModuleRow {
  const registry = workspaceModules.find((module) => module.key === overrides.key);
  return {
    key: overrides.key,
    name: overrides.name ?? registry?.name ?? overrides.key,
    description: overrides.description ?? registry?.description ?? "",
    web_path: overrides.web_path ?? registry?.webPath ?? `/${overrides.key}`,
    api_prefix: registry?.apiPrefix ?? "/api",
    required_permission: registry?.requiredPermission ?? "operations:read",
    status: overrides.status ?? "active",
    default_name: registry?.name ?? overrides.key,
    default_description: registry?.description ?? "",
    default_status: "active",
    customized: false,
    sort_order: 0,
    profiles: [],
    user_overrides: [],
  };
}

/**
 * Achado real (2026-09-09): a "Central de parametrizações" era uma lista fixa de 6 módulos escritos
 * à mão, e o UNI Localiza - criado depois dela - não aparecia. Agora ela é derivada da lista de
 * módulos que a tela já carrega, e estes testes garantem que módulo novo nunca fique de fora.
 */
describe("parameterModuleLinks", () => {
  it("inclui todo módulo ativo, inclusive os criados depois da lista de textos", () => {
    const links = parameterModuleLinks(workspaceModules.map((module) => row({ key: module.key })));

    expect(links.map((link) => link.key)).toEqual(workspaceModules.map((module) => module.key));
    expect(links.some((link) => link.key === "localiza")).toBe(true);
  });

  it("módulo sem texto próprio entra com a descrição dele, nunca vazio", () => {
    const [link] = parameterModuleLinks([row({ key: "modulo_novo", description: "Descrição do módulo novo" })]);

    expect(MODULE_PARAMETER_OWNERS.modulo_novo).toBeUndefined();
    expect(link.owner).toBe("Descrição do módulo novo");
  });

  it("usa o nome e a rota efetivos do módulo, não os do código", () => {
    // É o que faz a renomeação feita na aba Módulos aparecer aqui também.
    const [link] = parameterModuleLinks([row({ key: "localiza", name: "UNI Localizador" })]);

    expect(link.module).toBe("UNI Localizador");
    expect(link.path).toBe("/localiza");
  });

  it("módulo desativado sai da central de parametrizações", () => {
    const links = parameterModuleLinks([row({ key: "localiza", status: "disabled" })]);

    expect(links).toEqual([]);
  });
});

function authUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 1,
    name: "Usuário Teste",
    email: "teste@souuni.com",
    role: "viewer",
    active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    permissions: [],
    access_profile_ids: [],
    access_profile_names: [],
    collaborator_id: null,
    collaborator_name: null,
    managed_regional: null,
    managed_regionals: [],
    portal_first_access_required: false,
    ...overrides,
  };
}

function accessProfile(overrides: Partial<AccessProfile> = {}): AccessProfile {
  return {
    id: 1,
    name: "Perfil Teste",
    description: null,
    legacy_role: null,
    active: true,
    is_system: false,
    permission_keys: [],
    user_count: 0,
    delete_blocked_reason: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/**
 * Bug confirmado na auditoria de frontend de 2026-09-14: um usuário criado sem nenhum perfil
 * vinculado mostrava o código interno bruto do `role` legado (ex.: "workspace_restricted") na
 * coluna "Perfis" da tabela de Administração - texto sem sentido para quem administra o
 * ecossistema. A correção troca apenas a apresentação, nunca o valor armazenado em `role`.
 */
describe("profileNames", () => {
  it("lista os nomes dos perfis vinculados", () => {
    const user = authUser({ access_profile_ids: [1, 2] });
    const profiles = [accessProfile({ id: 1, name: "Admin Ecossistema" }), accessProfile({ id: 2, name: "Operador Operacional" })];

    expect(profileNames(user, profiles)).toBe("Admin Ecossistema, Operador Operacional");
  });

  it("mostra um rótulo amigável quando não há nenhum perfil vinculado, nunca o código interno de role", () => {
    const user = authUser({ role: "viewer" as AuthUser["role"], access_profile_ids: [] });

    expect(profileNames(user, [])).toBe("Sem perfil definido");
  });

  it("mostra o rótulo amigável mesmo quando o role bruto é um valor desconhecido do backend", () => {
    // `workspace_restricted` não faz parte da união de `AuthUser["role"]" no frontend - é
    // exatamente o caso real que vazava cru na tela antes da correção.
    const user = authUser({ role: "workspace_restricted" as AuthUser["role"], access_profile_ids: [] });

    expect(profileNames(user, [])).toBe("Sem perfil definido");
  });

  it("ignora IDs de perfil que não existem mais na lista carregada", () => {
    const user = authUser({ access_profile_ids: [999] });

    expect(profileNames(user, [])).toBe("Sem perfil definido");
  });
});

describe("ADMIN_NAV_ITEMS", () => {
  it("tem a aba Permissões entre Perfis e Módulos", () => {
    const values = ADMIN_NAV_ITEMS.map((item) => item.value);

    expect(values.indexOf("permissions")).toBe(values.indexOf("profiles") + 1);
    expect(values.indexOf("modules")).toBe(values.indexOf("permissions") + 1);
  });

  it("mantém o valor 'structure', que a Gestão Integrada linka de fora", () => {
    expect(ADMIN_NAV_ITEMS.some((item) => item.value === "structure")).toBe(true);
  });
});
