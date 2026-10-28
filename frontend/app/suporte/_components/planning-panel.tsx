"use client";

import { AlertCircle, FolderKanban, LayoutGrid, List, Loader2, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { api } from "@/lib/api";
import type { SupportPlanItem, SupportPlanItemDetail, SupportPlanKind, SupportPlanPerson, SupportPlanStatus, SupportPlanSummary } from "@/lib/types";

import { PlanningBoard } from "./planning-board";
import { PlanningItemForm } from "./planning-item-form";
import { PlanningItemSheet } from "./planning-item-sheet";
import { PlanningSummary } from "./planning-summary";
import { PlanningMoveSheet, moveNeedsText, type PlanningMove } from "./planning-move-sheet";
import {
  BOARD_COLUMNS,
  KIND_LABEL,
  PRIORITY_LABEL,
  PRIORITY_TONE,
  STATUS_LABEL,
  STATUS_TONE,
  assigneesLabel,
  dueLabel,
  progressPercent,
} from "./planning-format";

// Aba "Especialista/Analista" do Suporte Interno: projetos e tarefas que os dois lançam e acompanham.
// Tudo o que é lançado fica visível para quem acessa o Suporte; só quem tem `support:plan_write`
// lança e edita (a regra vale no backend). Atraso, progresso e conflito de edição vêm prontos da API.

type View = "board" | "list";
type Scope = "all" | "mine";

const VIEW_KEY = "suporte.planejamento.view";

function readStoredView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "list" ? "list" : "board";
  } catch {
    return "board";
  }
}

function ListView({ items, onOpen }: { items: SupportPlanItem[]; onOpen: (id: number) => void }) {
  return (
    <ul className="grid gap-2">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            onClick={() => onOpen(item.id)}
            className="grid w-full gap-2 rounded-xl border border-slate-200 bg-white p-3 text-left hover:bg-slate-50 sm:grid-cols-[auto_1fr_auto_auto] sm:items-center sm:gap-4"
          >
            <StatusBadge tone={STATUS_TONE[item.status]} dot>{STATUS_LABEL[item.status]}</StatusBadge>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-slate-900">{item.title}</span>
              <span className="block truncate text-xs text-slate-500">
                {KIND_LABEL[item.kind]}{item.parent_title ? ` · ${item.parent_title}` : ""} · {assigneesLabel(item)}
              </span>
            </span>
            <StatusBadge tone={PRIORITY_TONE[item.priority]}>{PRIORITY_LABEL[item.priority]}</StatusBadge>
            <span className={`text-xs ${item.overdue ? "font-semibold text-red-700" : "text-slate-600"}`}>{dueLabel(item)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function PlanningPanel({ canWrite, currentUserId }: { canWrite: boolean; currentUserId: number }) {
  const [view, setView] = useState<View>("board");
  const [scope, setScope] = useState<Scope>("all");
  const [kind, setKind] = useState<"" | SupportPlanKind>("");
  const [assigneeId, setAssigneeId] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  const [showClosed, setShowClosed] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const [items, setItems] = useState<SupportPlanItem[]>([]);
  const [projects, setProjects] = useState<SupportPlanItem[]>([]);
  const [summary, setSummary] = useState<SupportPlanSummary | null>(null);
  const [people, setPeople] = useState<SupportPlanPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  const [openId, setOpenId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<SupportPlanItem | null>(null);
  const [newKind, setNewKind] = useState<SupportPlanKind>("task");
  const [newParent, setNewParent] = useState<{ id: number; title: string } | null>(null);
  const [pendingMove, setPendingMove] = useState<PlanningMove | null>(null);
  const [moveError, setMoveError] = useState<string | null>(null);

  useEffect(() => setView(readStoredView()), []);

  // Busca com espera curta: não consulta a cada tecla.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    api.supportPlanPeople().then(setPeople).catch(() => setPeople([]));
  }, []);

  const effectiveAssignee = scope === "mine" ? currentUserId : assigneeId ? Number(assigneeId) : undefined;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // O quadro mostra concluídos junto; cancelados só entram quando pedidos.
    const status = showClosed ? undefined : "planned,in_progress,blocked,done";
    Promise.all([
      api.supportPlanItems({ status, kind: kind || undefined, assignee_id: effectiveAssignee, q: query || undefined, include_archived: showArchived, only_overdue: onlyOverdue }),
      api.supportPlanSummary(),
      api.supportPlanItems({ kind: "project", status: "planned,in_progress,blocked" }),
    ])
      .then(([page, nextSummary, projectPage]) => {
        if (cancelled) return;
        setItems(page.items);
        setSummary(nextSummary);
        setProjects(projectPage.items);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar os itens. Tente novamente.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, effectiveAssignee, query, onlyOverdue, showClosed, showArchived, reload]);

  const refresh = useCallback(() => setReload((current) => current + 1), []);

  function changeView(next: View) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      /* preferência é só conveniência */
    }
  }

  function openForm(nextKind: SupportPlanKind, parent: { id: number; title: string } | null = null) {
    setEditing(null);
    setNewKind(nextKind);
    setNewParent(parent);
    setFormOpen(true);
  }

  function handleSaved(saved: SupportPlanItemDetail) {
    // `editing` fica como está: zerar já na hora de fechar trocaria o título do painel durante a animação.
    setFormOpen(false);
    // Resultado-chave e ação nascem dentro de um pai: volta para ele, onde a lista já mostra o novo item.
    const inside = (saved.kind === "key_result" || saved.kind === "action") && saved.parent_id !== null;
    setOpenId(inside ? saved.parent_id : saved.id);
    refresh();
  }

  // Move um cartão de coluna. Para andamento/planejado o status muda na hora (a tela já mostra o novo
  // lugar e volta atrás se o servidor recusar); concluir, bloquear e cancelar pedem o texto antes.
  async function sendMove(item: SupportPlanItem, to: SupportPlanStatus, text: string, result: string): Promise<string | null> {
    try {
      await api.addSupportPlanProgress(item.id, { version: item.version, text, status: to, ...(to === "done" ? { result } : {}) });
      refresh();
      return null;
    } catch (reason) {
      refresh();
      return reason instanceof Error ? reason.message : "Não foi possível mover. Tente novamente.";
    }
  }

  async function handleDropMove(item: SupportPlanItem, to: SupportPlanStatus) {
    setMoveError(null);
    if (moveNeedsText(to)) {
      setPendingMove({ item, to });
      return;
    }
    const previous = items;
    setItems((current) => current.map((entry) => (entry.id === item.id ? { ...entry, status: to } : entry)));
    const failure = await sendMove(item, to, "", "");
    if (failure) {
      setItems(previous);
      setMoveError(failure);
    }
  }

  async function confirmMove(move: PlanningMove, text: string, result: string): Promise<string | null> {
    const failure = await sendMove(move.item, move.to, text, result);
    if (!failure) setPendingMove(null);
    return failure;
  }

  const hasFilters = Boolean(kind || assigneeId || query || onlyOverdue || scope === "mine");

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Especialista/Analista</h2>
          <p className="text-sm text-slate-500">Projetos e tarefas da dupla, com o andamento de cada um. Todos veem; quem tem permissão lança e atualiza.</p>
        </div>
        {canWrite ? (
          <div className="ml-auto flex gap-2">
            <Button variant="outline" onClick={() => openForm("project")}><FolderKanban size={16} aria-hidden="true" />Novo projeto</Button>
            <Button onClick={() => openForm("task")}><Plus size={16} aria-hidden="true" />Nova tarefa</Button>
          </div>
        ) : null}
      </div>

      <PlanningSummary summary={summary} />

      <div className="flex flex-wrap items-end gap-3">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por título ou descrição" className="pl-9" aria-label="Buscar" />
        </div>
        <Select value={scope} onChange={(event) => { setScope(event.target.value as Scope); setAssigneeId(""); }} className="w-auto" aria-label="De quem">
          <option value="all">Todos os itens</option>
          <option value="mine">Meus itens</option>
        </Select>
        {scope === "all" ? (
          <Select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)} className="w-auto" aria-label="Responsável">
            <option value="">Qualquer responsável</option>
            {people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
          </Select>
        ) : null}
        <Select value={kind} onChange={(event) => setKind(event.target.value as "" | SupportPlanKind)} className="w-auto" aria-label="Tipo">
          <option value="">Projetos e tarefas</option>
          <option value="project">Só projetos</option>
          <option value="task">Só tarefas</option>
        </Select>
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
          <input type="checkbox" checked={onlyOverdue} onChange={(event) => setOnlyOverdue(event.target.checked)} />Só atrasados
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
          <input type="checkbox" checked={showClosed} onChange={(event) => setShowClosed(event.target.checked)} />Incluir cancelados
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
          <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} />Incluir arquivados
        </label>
        <div className="ml-auto flex overflow-hidden rounded-md border border-input" role="group" aria-label="Modo de exibição">
          <Button variant={view === "board" ? "default" : "ghost"} size="sm" className="rounded-none" onClick={() => changeView("board")} aria-pressed={view === "board"}><LayoutGrid size={14} aria-hidden="true" />Quadro</Button>
          <Button variant={view === "list" ? "default" : "ghost"} size="sm" className="rounded-none" onClick={() => changeView("list")} aria-pressed={view === "list"}><List size={14} aria-hidden="true" />Lista</Button>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
          <AlertCircle size={18} aria-hidden="true" />
          <p className="mr-auto">{error}</p>
          <Button variant="outline" size="sm" onClick={refresh}>Tentar novamente</Button>
        </div>
      ) : null}

      {moveError ? (
        <div className="flex items-center gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
          <AlertCircle size={18} aria-hidden="true" />
          <p className="mr-auto">{moveError}</p>
          <Button variant="outline" size="sm" onClick={() => setMoveError(null)}>Fechar</Button>
        </div>
      ) : null}

      {loading && !items.length ? (
        <p className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
          <Loader2 className="animate-spin" size={16} aria-hidden="true" />Carregando…
        </p>
      ) : null}

      {!error && !loading && !items.length ? (
        <EmptyState
          title={hasFilters ? "Nenhum item com esses filtros" : "Nada lançado ainda"}
          description={hasFilters ? "Tire algum filtro para ver mais itens." : canWrite ? "Lance o primeiro projeto ou tarefa para a equipe acompanhar." : "Quando alguém lançar um projeto ou tarefa, ele aparece aqui."}
          variant="card"
        />
      ) : null}

      {items.length ? (
        view === "board" ? <PlanningBoard items={items} columns={showClosed ? [...BOARD_COLUMNS, "canceled"] : BOARD_COLUMNS} canMove={canWrite} onOpen={setOpenId} onMove={(item, to) => void handleDropMove(item, to)} onCreate={canWrite ? () => openForm("task") : null} /> : <ListView items={items} onOpen={setOpenId} />
      ) : null}

      <PlanningMoveSheet move={pendingMove} onCancel={() => setPendingMove(null)} onConfirm={confirmMove} />
      <PlanningItemSheet
        itemId={openId}
        canWrite={canWrite}
        refreshKey={reload}
        onClose={() => setOpenId(null)}
        onEdit={(item) => { setEditing(item); setFormOpen(true); }}
        onCreateChild={(kind, parent) => openForm(kind, parent)}
        onOpenItem={setOpenId}
        onChanged={refresh}
      />
      {canWrite ? (
        <PlanningItemForm
          open={formOpen}
          item={editing}
          people={people}
          projects={projects}
          defaultKind={newKind}
          defaultParent={newParent}
          currentUserId={currentUserId}
          onClose={() => setFormOpen(false)}
          onSaved={handleSaved}
        />
      ) : null}
    </div>
  );
}
