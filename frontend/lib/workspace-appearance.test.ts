import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_SIDEBAR_THEME,
  SIDEBAR_THEME_STORAGE_KEY,
  parseSidebarTheme,
  readSidebarTheme,
  resetSidebarThemeMemory,
  saveSidebarTheme,
} from "./workspace-appearance";

function fakeStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => (data.has(key) ? (data.get(key) as string) : null),
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

const blockedStorage = {
  getItem: () => {
    throw new Error("bloqueado");
  },
  setItem: () => {
    throw new Error("bloqueado");
  },
};

describe("workspace-appearance", () => {
  beforeEach(() => resetSidebarThemeMemory());

  it("o padrão é a barra clara", () => {
    expect(DEFAULT_SIDEBAR_THEME).toBe("light");
    expect(readSidebarTheme(fakeStorage())).toBe("light");
    expect(readSidebarTheme(null)).toBe("light");
  });

  it("só aceita light e dark; qualquer outro valor vira o padrão", () => {
    expect(parseSidebarTheme("dark")).toBe("dark");
    expect(parseSidebarTheme("light")).toBe("light");
    expect(parseSidebarTheme("azul")).toBe("light");
    expect(parseSidebarTheme(null)).toBe("light");
    expect(parseSidebarTheme(undefined)).toBe("light");
  });

  it("grava e lê a escolha no armazenamento do navegador", () => {
    const storage = fakeStorage();
    saveSidebarTheme("dark", storage);
    expect(storage.data.get(SIDEBAR_THEME_STORAGE_KEY)).toBe("dark");
    expect(readSidebarTheme(storage)).toBe("dark");
    saveSidebarTheme("light", storage);
    expect(readSidebarTheme(storage)).toBe("light");
  });

  it("valor corrompido guardado no navegador não quebra: volta ao padrão", () => {
    expect(readSidebarTheme(fakeStorage({ [SIDEBAR_THEME_STORAGE_KEY]: "<script>" }))).toBe("light");
  });

  it("com o armazenamento bloqueado, a escolha vale em memória até fechar a página", () => {
    expect(readSidebarTheme(blockedStorage)).toBe("light");
    saveSidebarTheme("dark", blockedStorage);
    expect(readSidebarTheme(blockedStorage)).toBe("dark");
  });
});
