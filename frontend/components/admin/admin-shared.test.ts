import { describe, expect, it } from "vitest";

import { workspaceModules } from "@/lib/module-registry";

import { ADMIN_NAV_ITEMS, MODULE_PARAMETER_OWNERS, parameterModuleLinks, type VisibleModuleRow } from "./admin-shared";

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
