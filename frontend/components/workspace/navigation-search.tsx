"use client";

import Link from "next/link";
import { ArrowUpRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { moduleScreenHref, visibleModuleScreens } from "@/lib/module-screens";
import { moduleIcon, visibleWorkspaceScreens } from "@/lib/workspace-navigation";
import type { WorkspaceVisibleModule } from "@/lib/types";

export function NavigationSearch({ modules, permissions }: { modules: WorkspaceVisibleModule[]; permissions: readonly string[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
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
  const entries = useMemo(() => [
    ...visibleWorkspaceScreens(permissions).map((screen) => ({ href: screen.path, label: screen.name, group: "Workspace", icon: screen.icon })),
    ...modules.flatMap((module) => [
      { href: module.web_path, label: module.name, group: "Módulos", icon: moduleIcon(module.key) },
      ...visibleModuleScreens(module.key, moduleIcon(module.key), permissions).map((screen) => ({
        href: moduleScreenHref(module.web_path, screen), label: screen.label, group: module.name, icon: screen.icon,
      })),
    ]),
  ], [modules, permissions]);
  const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");
  const results = entries.filter((entry) => normalize(`${entry.group} ${entry.label}`).includes(normalize(query.trim())));

  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) setQuery(""); }}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 gap-2 px-2 sm:px-3" aria-label="Buscar telas e módulos">
          <Search className="h-4 w-4" /><span className="hidden xl:inline">Buscar telas</span><kbd className="hidden rounded border bg-slate-50 px-1 text-[10px] text-slate-500 xl:inline">Ctrl K</kbd>
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>Ir para uma tela</DialogTitle><DialogDescription>Encontre módulos e funcionalidades disponíveis para seu perfil.</DialogDescription></DialogHeader>
        <Input aria-label="Pesquisar telas" placeholder="Digite o nome de uma tela ou módulo..." value={query} onChange={(event) => setQuery(event.target.value)} />
        <nav aria-label="Resultados da busca" className="max-h-[50dvh] space-y-1 overflow-y-auto">
          {results.map((entry) => <Link key={entry.href} href={entry.href} onClick={() => { setOpen(false); setQuery(""); }} className="group flex items-center gap-3 rounded-xl p-3 transition-colors hover:bg-secondary focus-visible:bg-secondary">
            <span className="rounded-lg bg-secondary p-2 text-primary"><entry.icon className="h-4 w-4" /></span>
            <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-slate-800">{entry.label}</span><span className="text-xs text-slate-500">{entry.group}</span></span>
            <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-primary" />
          </Link>)}
          {!results.length ? <EmptyState variant="plain" icon={<Search className="h-5 w-5" />} title="Nenhuma tela encontrada" description="Tente outro nome de módulo ou funcionalidade." /> : null}
        </nav>
      </DialogContent>
    </Dialog>
  );
}
