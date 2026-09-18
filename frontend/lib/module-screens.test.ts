import { describe, expect, it } from "vitest";
import { MapPin } from "lucide-react";

import { workspaceModules } from "./module-registry";
import { moduleScreens, moduleScreenHref, visibleModuleScreens } from "./module-screens";

/**
 * Achado real (2026-09-09): o UNI Localiza era o único módulo ATIVO sem telas neste catálogo, então
 * o menu lateral do ecossistema não oferecia nenhum destino dentro dele - diferente de todos os
 * outros módulos. O teste abaixo cobre o caso e vira a trava para o próximo módulo novo.
 */
describe("module-screens", () => {
  it("todo módulo ativo do registro tem pelo menos uma tela no menu global", () => {
    const withoutScreens = workspaceModules
      .filter((module) => module.status === "active")
      .filter((module) => moduleScreens(module.key, MapPin).length === 0)
      .map((module) => module.key);

    expect(withoutScreens).toEqual([]);
  });

  it("as telas do UNI Localiza são as abas reais da página", () => {
    const screens = moduleScreens("localiza", MapPin);

    expect(screens.map((screen) => screen.value)).toEqual(["solicitacoes", "mapa"]);
  });

  it("as telas do Localiza exigem só a permissão do próprio módulo", () => {
    // `localiza:manage` controla ações dentro das telas (gerar/invalidar link), não o acesso a elas.
    const screens = visibleModuleScreens("localiza", MapPin, ["localiza:read"]);

    expect(screens).toHaveLength(2);
  });

  it("o link da tela usa a convenção ?tab= que a página lê na montagem", () => {
    const [first] = moduleScreens("localiza", MapPin);

    expect(moduleScreenHref("/localiza", first)).toBe("/localiza?tab=solicitacoes");
  });

  it("a aba Permissões da Administração exige admin:permissions:read", () => {
    const withRead = visibleModuleScreens("admin", MapPin, ["admin:permissions:read"]);
    const withoutRead = visibleModuleScreens("admin", MapPin, ["admin:users:read"]);

    expect(withRead.some((screen) => screen.value === "permissions")).toBe(true);
    expect(withoutRead.some((screen) => screen.value === "permissions")).toBe(false);
  });
});
