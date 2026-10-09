"use client";

import Link from "next/link";
import { ArrowLeft, ArrowUpRight, ChevronRight, Search, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { moduleScreenHref, visibleModuleScreens } from "@/lib/module-screens";
import { moduleIcon, visibleWorkspaceScreens } from "@/lib/workspace-navigation";
import {
  normalizeSearch,
  useDynamicSearchEntries,
  type PersonRecord,
  type SearchEntry,
} from "@/components/workspace/use-search-index";
import type { WorkspaceVisibleModule } from "@/lib/types";

export function NavigationSearch({ modules, permissions }: { modules: WorkspaceVisibleModule[]; permissions: readonly string[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"screens" | "people">("screens");
  // Pessoa aberta: a busca troca a lista pela relação de lugares em que ela aparece.
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  const { entries: dynamicEntries, people } = useDynamicSearchEntries(open, permissions);
  const entries = useMemo((): SearchEntry[] => [
    ...visibleWorkspaceScreens(permissions).map((screen) => ({ href: screen.path, label: screen.name, group: "Workspace", icon: screen.icon })),
    ...modules.flatMap((module) => [
      { href: module.web_path, label: module.name, group: "Módulos", icon: moduleIcon(module.key) },
      ...visibleModuleScreens(module.key, moduleIcon(module.key), permissions).map((screen) => ({
        href: moduleScreenHref(module.web_path, screen), label: screen.label, icon: screen.icon,
        group: screen.parentLabel ? `${module.name} · ${screen.parentLabel}` : module.name,
        newTab: screen.opensInNewTab,
      })),
    ]),
    ...dynamicEntries,
  ].filter((entry, index, all) => all.findIndex((other) => other.href === entry.href && other.label === entry.label && other.group === entry.group) === index),
  [modules, permissions, dynamicEntries]);
  const needle = normalizeSearch(query);
  const screenResults = entries.filter((entry) => normalizeSearch(`${entry.group} ${entry.label} ${entry.extra ?? ""}`).includes(needle));
  const peopleResults = people.filter((person) => normalizeSearch(`${person.name} ${person.extra}`).includes(needle));
  const selected = selectedKey ? people.find((person) => person.key === selectedKey) ?? null : null;
  const resultCount = mode === "people" ? peopleResults.length : screenResults.length;
  const close = () => { setOpen(false); setQuery(""); setSelectedKey(null); setMode("screens"); };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (next) setOpen(true); else close(); }}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 gap-2 px-2 sm:px-3" aria-label="Buscar telas e módulos">
          <Search className="h-4 w-4" /><span className="hidden xl:inline">Buscar telas</span><kbd className="hidden rounded border bg-slate-50 px-1 text-[10px] text-slate-500 xl:inline">Ctrl K</kbd>
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>Ir para uma tela</DialogTitle><DialogDescription>Encontre módulos, funcionalidades e pessoas disponíveis para seu perfil.</DialogDescription></DialogHeader>
        {selected ? <PersonDestinations person={selected} onBack={() => setSelectedKey(null)} onNavigate={close} /> : <>
          <div role="group" aria-label="Tipo de busca" className="grid grid-cols-2 gap-1 rounded-xl bg-secondary p-1">
            {([["screens", "Telas"], ["people", "Pessoas"]] as const).map(([value, label]) => (
              <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)}
                className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors ${mode === value ? "bg-white text-primary shadow-sm" : "text-slate-600 hover:text-slate-900"}`}>
                {label}{mode === value ? <span className="ml-1.5 text-xs font-normal text-slate-500">{resultCount}</span> : null}
              </button>
            ))}
          </div>
          <Input aria-label="Pesquisar telas" placeholder={mode === "people" ? "Digite o nome ou e-mail de uma pessoa..." : "Digite o nome de uma tela ou módulo..."} value={query} onChange={(event) => setQuery(event.target.value)} />
          <nav aria-label="Resultados da busca" className="max-h-[50dvh] space-y-1 overflow-y-auto">
            {mode === "people" ? peopleResults.map((person) => (
              <button key={person.key} type="button" onClick={() => setSelectedKey(person.key)} className="group flex w-full items-center gap-3 rounded-xl p-3 text-left transition-colors hover:bg-secondary focus-visible:bg-secondary">
                <span className="rounded-lg bg-secondary p-2 text-primary"><UserRound className="h-4 w-4" /></span>
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-800">{person.name}</span><span className="text-xs text-slate-500">{person.destinations.length} {person.destinations.length === 1 ? "lugar" : "lugares"}</span></span>
                <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-primary" />
              </button>
            )) : screenResults.map((entry) => <Link key={`${entry.href}|${entry.group}|${entry.label}`} href={entry.href} target={entry.newTab ? "_blank" : undefined} rel={entry.newTab ? "noopener noreferrer" : undefined} onClick={close} className="group flex items-center gap-3 rounded-xl p-3 transition-colors hover:bg-secondary focus-visible:bg-secondary">
              <span className="rounded-lg bg-secondary p-2 text-primary"><entry.icon className="h-4 w-4" /></span>
              <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-slate-800">{entry.label}</span><span className="text-xs text-slate-500">{entry.group}</span></span>
              <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-primary" />
            </Link>)}
            {!resultCount ? <EmptyState variant="plain" icon={<Search className="h-5 w-5" />} title={mode === "people" ? "Nenhuma pessoa encontrada" : "Nenhuma tela encontrada"} description={mode === "people" ? "Tente outro nome ou e-mail." : "Tente outro nome de módulo ou funcionalidade."} /> : null}
          </nav>
        </>}
      </DialogContent>
    </Dialog>
  );
}

/** Onde a pessoa aparece: cada destino é uma aba/função em que ela existe. */
function PersonDestinations({ person, onBack, onNavigate }: { person: PersonRecord; onBack: () => void; onNavigate: () => void }) {
  return (
    <div className="space-y-3">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
        <ArrowLeft className="h-4 w-4" /> Voltar à busca
      </button>
      <div>
        <p className="text-base font-semibold text-slate-900">{person.name}</p>
        <p className="text-xs text-slate-500">Escolha onde abrir ({person.destinations.length} {person.destinations.length === 1 ? "lugar" : "lugares"})</p>
      </div>
      <nav aria-label="Lugares da pessoa" className="max-h-[50dvh] space-y-1 overflow-y-auto">
        {person.destinations.map((destination) => (
          <Link key={destination.href} href={destination.href} onClick={onNavigate} className="group flex items-center gap-3 rounded-xl p-3 transition-colors hover:bg-secondary focus-visible:bg-secondary">
            <span className="rounded-lg bg-secondary p-2 text-primary"><destination.icon className="h-4 w-4" /></span>
            <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-slate-800">{destination.label}</span><span className="text-xs text-slate-500">{destination.description}</span></span>
            <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-primary" />
          </Link>
        ))}
      </nav>
    </div>
  );
}
