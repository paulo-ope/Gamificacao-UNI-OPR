"use client";

import * as Popover from "@radix-ui/react-popover";
import { Bookmark, Check, ChevronDown, MoreHorizontal, Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AppRadio } from "@/components/ui/radio";
import type { SchedulingSavedFilter } from "@/lib/scheduling-api";

export function SchedulingSavedViewsPopover({
  savedFilters,
  selectedSavedFilterId,
  filterName,
  visibility,
  canManageViews,
  canCreateGlobalViews,
  onSelect,
  onNameChange,
  onVisibilityChange,
  onSave,
  onUpdate,
  onDelete,
}: {
  savedFilters: SchedulingSavedFilter[];
  selectedSavedFilterId: number | null;
  filterName: string;
  visibility: "personal" | "global";
  canManageViews: boolean;
  canCreateGlobalViews: boolean;
  onSelect: (id: number | null) => void;
  onNameChange: (value: string) => void;
  onVisibilityChange: (value: "personal" | "global") => void;
  onSave: () => void;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmUpdate, setConfirmUpdate] = useState(false);
  const active = savedFilters.find((item) => item.id === selectedSavedFilterId);
  const visible = savedFilters.filter((item) =>
    item.name.toLocaleLowerCase("pt-BR").includes(search.toLocaleLowerCase("pt-BR")),
  );
  const choose = (id: number) => {
    onSelect(id);
    setCreating(false);
    setRenaming(false);
    setConfirmDelete(false);
    setConfirmUpdate(false);
    setOpen(false);
  };
  const saveNew = () => {
    onSave();
    setCreating(false);
  };
  const update = () => {
    onUpdate();
    setRenaming(false);
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button type="button" variant="outline" className="h-10 shrink-0 whitespace-nowrap">
          <Bookmark className="h-4 w-4" />
          <span className="max-w-36 truncate">{active ? `Visão: ${active.name}` : "Visões"}</span>
          <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} className="z-50 w-[min(25rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-3 shadow-xl">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900">Visões salvas</p>
              <p className="text-[11px] text-slate-500">Combinações de filtros reutilizáveis.</p>
            </div>
            {active && canManageViews ? (
              <Popover.Root>
                <Popover.Trigger asChild>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Opções da visão">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content align="end" sideOffset={6} className="z-[60] w-44 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmUpdate(true);
                        setRenaming(false);
                        setConfirmDelete(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Atualizar visão
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRenaming(true);
                        setCreating(false);
                        setConfirmUpdate(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Renomear e atualizar
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmDelete(true);
                        setConfirmUpdate(false);
                      }}
                      className="flex w-full rounded-md px-2 py-2 text-left text-xs text-red-700 hover:bg-red-50"
                    >
                      Excluir visão
                    </button>
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            ) : null}
          </div>
          {active ? (
            <button
              type="button"
              onClick={() => {
                onSelect(null);
                onVisibilityChange("personal");
                setCreating(false);
                setRenaming(false);
                setConfirmDelete(false);
                setConfirmUpdate(false);
              }}
              className="mb-2 text-[11px] font-medium text-blue-700 hover:text-blue-900"
            >
              Retirar visão selecionada
            </button>
          ) : null}
          <label className="relative mb-2 block">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar visão" className="h-9 pl-8 text-xs" />
          </label>
          <div className="max-h-44 space-y-1 overflow-y-auto pr-1">
            {visible.length ? (
              visible.map((saved) => (
                <button
                  key={saved.id}
                  type="button"
                  onClick={() => choose(saved.id)}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs ${saved.id === selectedSavedFilterId ? "bg-blue-50 text-blue-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  <span className="min-w-0 truncate">
                    {saved.name}
                    <span className="ml-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase text-slate-500">
                      {saved.visibility === "global" ? "Global" : "Pessoal"}
                    </span>
                  </span>
                  {saved.id === selectedSavedFilterId ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
                </button>
              ))
            ) : (
              <p className="px-2 py-4 text-center text-xs text-slate-500">Nenhuma visão encontrada.</p>
            )}
          </div>
          {canManageViews ? (
            <div className="mt-3 border-t border-slate-100 pt-3">
              {creating || renaming ? (
                <div className="space-y-2">
                  <Input
                    value={filterName}
                    maxLength={120}
                    placeholder="Nome da visão"
                    onChange={(event) => onNameChange(event.target.value)}
                    className="h-9 text-xs"
                  />
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Tipo da visão</p>
                    <div className="grid gap-1.5 sm:grid-cols-2">
                      <label className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                        <AppRadio checked={visibility === "personal"} onSelect={() => onVisibilityChange("personal")} ariaLabel="Pessoal" />
                        Pessoal
                      </label>
                      {canCreateGlobalViews || active?.visibility === "global" ? (
                        <label className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                          <AppRadio
                            checked={visibility === "global"}
                            disabled={!canCreateGlobalViews && active?.visibility !== "global"}
                            onSelect={() => onVisibilityChange("global")}
                            ariaLabel="Global"
                          />
                          Global
                        </label>
                      ) : (
                        <div className="rounded-md bg-white px-2 py-1.5 text-xs text-slate-400">Global indisponível para seu perfil</div>
                      )}
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-8 text-xs"
                      onClick={() => {
                        setCreating(false);
                        setRenaming(false);
                        if (!active) onVisibilityChange("personal");
                      }}
                    >
                      Cancelar
                    </Button>
                    <Button type="button" size="sm" className="h-8 text-xs" disabled={!filterName.trim()} onClick={creating ? saveNew : update}>
                      {creating ? "Salvar visão" : "Atualizar visão"}
                    </Button>
                  </div>
                </div>
              ) : confirmDelete ? (
                <div className="flex items-center justify-between gap-2 rounded-lg bg-red-50 p-2">
                  <span className="text-[11px] text-red-800">Excluir "{active?.name}"?</span>
                  <div className="flex gap-1">
                    <Button type="button" size="sm" variant="ghost" className="h-7 text-[10px]" onClick={() => setConfirmDelete(false)}>
                      Cancelar
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 bg-red-600 text-[10px] hover:bg-red-700"
                      onClick={() => {
                        onDelete();
                        setConfirmDelete(false);
                        setOpen(false);
                      }}
                    >
                      Excluir
                    </Button>
                  </div>
                </div>
              ) : confirmUpdate ? (
                <div className="flex items-center justify-between gap-2 rounded-lg bg-blue-50 p-2">
                  <span className="text-[11px] text-blue-800">Atualizar "{active?.name}" com os filtros atuais?</span>
                  <div className="flex gap-1">
                    <Button type="button" size="sm" variant="ghost" className="h-7 text-[10px]" onClick={() => setConfirmUpdate(false)}>
                      Cancelar
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 text-[10px]"
                      onClick={() => {
                        onUpdate();
                        setConfirmUpdate(false);
                        setOpen(false);
                      }}
                    >
                      Atualizar
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8 flex-1 text-xs"
                    onClick={() => {
                      onSelect(null);
                      onVisibilityChange("personal");
                      setCreating(true);
                      setRenaming(false);
                    }}
                  >
                    Salvar como nova visão
                  </Button>
                </div>
              )}
            </div>
          ) : null}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
