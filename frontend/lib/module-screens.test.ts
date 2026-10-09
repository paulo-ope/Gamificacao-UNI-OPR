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

  it("a TV do Suporte aparece no menu do módulo com rota própria e abre em nova aba", () => {
    const tv = visibleModuleScreens("support", MapPin, ["support:read"]).find((screen) => screen.value === "tv");

    expect(tv?.label).toBe("TV Suporte Interno");
    expect(tv?.opensInNewTab).toBe(true);
    expect(moduleScreenHref("/suporte", tv!)).toBe("/suporte/tv");
  });

  it("a TV não vira aba da página do módulo (só existe no menu global)", () => {
    const tabs = moduleScreens("support", MapPin).filter((screen) => !screen.path);

    expect(tabs.some((screen) => screen.value === "tv")).toBe(false);
  });

  it("a aba Permissões da Administração exige admin:permissions:read", () => {
    const withRead = visibleModuleScreens("admin", MapPin, ["admin:permissions:read"]);
    const withoutRead = visibleModuleScreens("admin", MapPin, ["admin:users:read"]);

    expect(withRead.some((screen) => screen.value === "permissions")).toBe(true);
    expect(withoutRead.some((screen) => screen.value === "permissions")).toBe(false);
  });

  it("a Governança de IA da Administração é encontrável e exige admin:ai_governance:read", () => {
    const withRead = visibleModuleScreens("admin", MapPin, ["admin:ai_governance:read"]);
    const withoutRead = visibleModuleScreens("admin", MapPin, ["admin:permissions:read"]);

    expect(withRead.some((screen) => screen.value === "ai_governance")).toBe(true);
    expect(withoutRead.some((screen) => screen.value === "ai_governance")).toBe(false);
  });

  it("sub-abas da Gamificação viram link com ?tab=<aba>&sub=<sub-aba>", () => {
    const leadership = moduleScreens("gamification", MapPin).find((screen) => screen.value === "leadership");

    expect(leadership?.parentValue).toBe("config");
    expect(moduleScreenHref("/gamificacao", leadership!)).toBe("/gamificacao?tab=config&sub=leadership");
  });

  it("sub-abas de Configuração exigem a mesma permissão da aba; Usuários exige users:manage", () => {
    const sem = visibleModuleScreens("gamification", MapPin, []);
    const comScoring = visibleModuleScreens("gamification", MapPin, ["scoring:write"]);
    const comUsers = visibleModuleScreens("gamification", MapPin, ["users:manage"]);

    expect(sem.some((screen) => screen.value === "leadership")).toBe(false);
    expect(comScoring.some((screen) => screen.value === "leadership")).toBe(true);
    expect(comScoring.some((screen) => screen.value === "users")).toBe(false);
    expect(comUsers.some((screen) => screen.value === "users")).toBe(true);
    expect(sem.some((screen) => screen.value === "trail")).toBe(true);
  });

  it("sub-abas e Governança de IA são só da busca: o menu lateral filtra por searchOnly", () => {
    const all = visibleModuleScreens("gamification", MapPin, ["scoring:write", "users:manage"]);
    const sidebar = all.filter((screen) => !screen.searchOnly);

    expect(all.some((screen) => screen.parentValue)).toBe(true);
    expect(sidebar.some((screen) => screen.parentValue)).toBe(false);
    expect(sidebar.map((screen) => screen.value)).toEqual(
      ["closure", "ranking", "pending", "config", "audit", "balance", "history", "import"],
    );
    const admin = visibleModuleScreens("admin", MapPin, ["admin:ai_governance:read"]).filter((screen) => !screen.searchOnly);
    expect(admin.some((screen) => screen.value === "ai_governance")).toBe(false);
  });

  it("Pessoas não aparece no menu lateral da Administração, mas segue encontrável pela busca", () => {
    const all = visibleModuleScreens("admin", MapPin, []);

    expect(all.some((screen) => screen.value === "structure")).toBe(true);
    expect(all.filter((screen) => !screen.searchOnly).some((screen) => screen.value === "structure")).toBe(false);
    expect(moduleScreenHref("/admin", all.find((screen) => screen.value === "structure")!)).toBe("/admin?tab=structure");
  });
});
