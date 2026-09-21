"use client";

import { useEffect, useState } from "react";

/**
 * Estado de "recolher/expandir" de uma barra de filtros, com persistência opcional em
 * localStorage (por navegador, não por conta) - mesmo padrão que já existia duplicado em
 * `OverviewFilterBar` (com persistência) e `SchedulingFiltersBar`/`IxcTicketFiltersBar` (sem
 * persistência, sempre recolhida no primeiro carregamento). Extraído em 2026-09-18 ao padronizar
 * o formato de filtro recolhível pros módulos que ainda não tinham (pedido do usuário).
 */
export function useCollapsibleFilters(options?: { persistKey?: string; defaultExpanded?: boolean }) {
  const { persistKey, defaultExpanded = false } = options ?? {};
  const [expanded, setExpandedState] = useState(defaultExpanded);

  useEffect(() => {
    if (!persistKey) return;
    try {
      const stored = window.localStorage.getItem(persistKey);
      if (stored !== null) setExpandedState(stored === "true");
    } catch {
      // Sem preferência acessível: segue no valor padrão.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setExpanded(next: boolean) {
    setExpandedState(next);
    if (!persistKey) return;
    try {
      window.localStorage.setItem(persistKey, String(next));
    } catch {
      // Preferência é conveniência: não impedir a interação se o armazenamento falhar.
    }
  }

  function toggle() {
    setExpanded(!expanded);
  }

  return { expanded, setExpanded, toggle };
}
