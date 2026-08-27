"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight, ChevronUp, ChevronDown, Pin, PinOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { getWorkspaceModule, workspaceModules } from "@/lib/module-registry";
import type { WorkspaceVisibleModule } from "@/lib/types";

const COLLAPSED_STORAGE_KEY = "uni_sidebar_collapsed";

// Fixado primeiro (ordem própria entre os fixados), depois o resto na ordem do registro - achado
// de design da modernização (2026-08-27): reordenar entre os NÃO fixados não agrega tanto valor
// quanto poder priorizar os poucos módulos fixados, então só os fixados ganham controle de posição.
function sortModules(modules: WorkspaceVisibleModule[]): WorkspaceVisibleModule[] {
  const pinned = modules
    .filter((module) => module.pinned)
    .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
  const rest = modules.filter((module) => !module.pinned);
  return [...pinned, ...rest];
}

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const [modules, setModules] = useState<WorkspaceVisibleModule[] | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(COLLAPSED_STORAGE_KEY);
    if (stored === "1") setCollapsed(true);
  }, []);

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(COLLAPSED_STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

  useEffect(() => {
    let active = true;
    api
      .workspaceModules()
      .then((result) => {
        if (active) setModules(sortModules(result));
      })
      .catch(() => {
        if (active) setModules(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const fallbackModules = useMemo<WorkspaceVisibleModule[]>(
    () =>
      workspaceModules
        .filter((module) => module.status === "active")
        .map((module) => ({
          key: module.key,
          name: module.name,
          description: module.description,
          web_path: module.webPath,
          api_prefix: module.apiPrefix,
          required_permission: module.requiredPermission,
          status: module.status,
          pinned: false,
          order_index: null,
        })),
    [],
  );
  const items = modules ?? fallbackModules;
  const pinnedItems = items.filter((item) => item.pinned);

  async function togglePin(module: WorkspaceVisibleModule) {
    if (!modules) return;
    const nextPinned = !module.pinned;
    const nextOrderIndex = nextPinned ? pinnedItems.length : null;
    const updated = await api.updateModulePreference(module.key, {
      pinned: nextPinned,
      ...(nextOrderIndex !== null ? { order_index: nextOrderIndex } : {}),
    });
    setModules((current) =>
      sortModules((current ?? []).map((item) => (item.key === module.key ? { ...item, ...updated } : item))),
    );
  }

  async function movePinned(module: WorkspaceVisibleModule, direction: -1 | 1) {
    if (!modules) return;
    const ordered = pinnedItems;
    const index = ordered.findIndex((item) => item.key === module.key);
    const swapIndex = index + direction;
    if (index === -1 || swapIndex < 0 || swapIndex >= ordered.length) return;
    const a = ordered[index];
    const b = ordered[swapIndex];
    const [updatedA, updatedB] = await Promise.all([
      api.updateModulePreference(a.key, { order_index: swapIndex }),
      api.updateModulePreference(b.key, { order_index: index }),
    ]);
    setModules((current) =>
      sortModules(
        (current ?? []).map((item) => {
          if (item.key === updatedA.key) return { ...item, ...updatedA };
          if (item.key === updatedB.key) return { ...item, ...updatedB };
          return item;
        }),
      ),
    );
  }

  return (
    <aside
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r border-slate-200 bg-white transition-[width] duration-150",
        collapsed ? "w-[68px]" : "w-64",
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-3">
        {!collapsed ? (
          <Link href="/" className="flex min-w-0 items-center gap-2">
            <img src="/brand/uni-logo.png" alt="UNI Internet" className="h-7 w-auto shrink-0" />
            <span className="truncate text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">
              UNI Workspace
            </span>
          </Link>
        ) : (
          <img src="/brand/uni-logo.png" alt="UNI Internet" className="mx-auto h-7 w-auto" />
        )}
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
          className="shrink-0 rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700"
        >
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-1">
          {items.map((module) => {
            const definition = getWorkspaceModule(module.key);
            const Icon = definition?.icon;
            const active = pathname === module.web_path || pathname?.startsWith(`${module.web_path}/`);
            const pinnedIndex = pinnedItems.findIndex((item) => item.key === module.key);
            return (
              <li key={module.key} className="group/item">
                <div
                  className={cn(
                    "flex items-center gap-2 rounded-xl px-2.5 py-2 text-sm transition",
                    active ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                  )}
                >
                  <Link
                    href={module.web_path}
                    title={module.name}
                    className="flex min-w-0 flex-1 items-center gap-2.5"
                  >
                    {Icon ? <Icon className={cn("h-4 w-4 shrink-0", active ? "text-blue-700" : "text-slate-500")} /> : null}
                    {!collapsed ? <span className="truncate font-medium">{module.name}</span> : null}
                  </Link>
                  {!collapsed ? (
                    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition group-hover/item:opacity-100">
                      {module.pinned && pinnedIndex > 0 ? (
                        <button
                          type="button"
                          onClick={() => void movePinned(module, -1)}
                          aria-label={`Mover ${module.name} para cima`}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        >
                          <ChevronUp className="h-3.5 w-3.5" />
                        </button>
                      ) : null}
                      {module.pinned && pinnedIndex < pinnedItems.length - 1 ? (
                        <button
                          type="button"
                          onClick={() => void movePinned(module, 1)}
                          aria-label={`Mover ${module.name} para baixo`}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        >
                          <ChevronDown className="h-3.5 w-3.5" />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void togglePin(module)}
                        aria-label={module.pinned ? `Desafixar ${module.name}` : `Fixar ${module.name}`}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      >
                        {module.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
