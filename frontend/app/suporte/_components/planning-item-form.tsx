"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { SupportPlanItem, SupportPlanItemDetail, SupportPlanKind, SupportPlanPerson, SupportPlanPriority } from "@/lib/types";

import { KIND_LABEL, PRIORITY_LABEL } from "./planning-format";

// Formulário de lançar/editar projeto ou tarefa. Só coleta e envia: as regras (pai tem de ser
// projeto, responsável ativo, conflito de versão) são decididas e validadas no backend.

type Props = {
  open: boolean;
  /** Item em edição; null = lançar novo. */
  item: SupportPlanItem | null;
  people: SupportPlanPerson[];
  projects: SupportPlanItem[];
  defaultKind?: SupportPlanKind;
  currentUserId: number;
  onClose: () => void;
  onSaved: (item: SupportPlanItemDetail) => void;
};

type Draft = {
  kind: SupportPlanKind;
  title: string;
  description: string;
  priority: SupportPlanPriority;
  dueDate: string;
  assigneeIds: number[];
  parentId: string;
};

function initialDraft(item: SupportPlanItem | null, kind: SupportPlanKind, currentUserId: number): Draft {
  if (item) {
    return {
      kind: item.kind,
      title: item.title,
      description: item.description ?? "",
      priority: item.priority,
      dueDate: item.due_date ?? "",
      assigneeIds: item.assignees.map((person) => person.id),
      parentId: item.parent_id ? String(item.parent_id) : "",
    };
  }
  return { kind, title: "", description: "", priority: "medium", dueDate: "", assigneeIds: [currentUserId], parentId: "" };
}

export function PlanningItemForm({ open, item, people, projects, defaultKind = "task", currentUserId, onClose, onSaved }: Props) {
  const [draft, setDraft] = useState<Draft>(() => initialDraft(item, defaultKind, currentUserId));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDraft(initialDraft(item, defaultKind, currentUserId));
      setError(null);
    }
  }, [open, item, defaultKind, currentUserId]);

  function toggleAssignee(id: number) {
    setDraft((current) => ({
      ...current,
      assigneeIds: current.assigneeIds.includes(id) ? current.assigneeIds.filter((value) => value !== id) : [...current.assigneeIds, id],
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      setError("Informe o título.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const parentId = draft.kind === "task" && draft.parentId ? Number(draft.parentId) : null;
      const saved = item
        ? await api.updateSupportPlanItem(item.id, {
            version: item.version,
            title: draft.title,
            description: draft.description,
            priority: draft.priority,
            assignee_ids: draft.assigneeIds,
            ...(draft.dueDate ? { due_date: draft.dueDate } : { clear_due_date: true }),
            ...(parentId ? { parent_id: parentId } : { clear_parent: true }),
          })
        : await api.createSupportPlanItem({
            kind: draft.kind,
            title: draft.title,
            description: draft.description || null,
            priority: draft.priority,
            due_date: draft.dueDate || null,
            assignee_ids: draft.assigneeIds,
            parent_id: parentId,
          });
      onSaved(saved);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  const editing = item !== null;
  const noun = KIND_LABEL[draft.kind].toLowerCase();

  return (
    <Sheet open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <SheetContent className="sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{editing ? `Editar ${noun}` : `Lançar ${draft.kind === "project" ? "projeto" : "tarefa"}`}</SheetTitle>
          <SheetDescription>Tudo o que for lançado fica visível para a equipe do Suporte.</SheetDescription>
        </SheetHeader>
        <form className="grid gap-4 p-6" onSubmit={submit}>
          {error ? (
            <div className="flex items-start gap-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-800" role="alert">
              <AlertCircle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
              <p>{error}</p>
            </div>
          ) : null}
          {!editing ? (
            <Field className="grid gap-1.5">
              <Label>Tipo</Label>
              <Select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as SupportPlanKind, parentId: "" })}>
                <option value="task">Tarefa</option>
                <option value="project">Projeto</option>
              </Select>
            </Field>
          ) : null}
          <Field className="grid gap-1.5">
            <Label>Título</Label>
            <Input value={draft.title} maxLength={200} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="O que precisa ser feito" autoFocus />
          </Field>
          <Field className="grid gap-1.5">
            <Label>Descrição</Label>
            <Textarea value={draft.description} maxLength={5000} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="Contexto, objetivo e como será feito (opcional)" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field className="grid gap-1.5">
              <Label>Prioridade</Label>
              <Select value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: event.target.value as SupportPlanPriority })}>
                {(Object.keys(PRIORITY_LABEL) as SupportPlanPriority[]).map((key) => (
                  <option key={key} value={key}>{PRIORITY_LABEL[key]}</option>
                ))}
              </Select>
            </Field>
            <Field className="grid gap-1.5">
              <Label>Prazo</Label>
              <Input type="date" value={draft.dueDate} onChange={(event) => setDraft({ ...draft, dueDate: event.target.value })} />
            </Field>
          </div>
          {draft.kind === "task" ? (
            <Field className="grid gap-1.5">
              <Label>Projeto</Label>
              <Select value={draft.parentId} onChange={(event) => setDraft({ ...draft, parentId: event.target.value })}>
                <option value="">Tarefa avulsa (sem projeto)</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{project.title}</option>
                ))}
              </Select>
            </Field>
          ) : null}
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium text-slate-800">Responsáveis</legend>
            {people.length ? (
              <div className="flex flex-wrap gap-2">
                {people.map((person) => {
                  const checked = draft.assigneeIds.includes(person.id);
                  return (
                    <label
                      key={person.id}
                      className={`flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-sm ${checked ? "border-blue-300 bg-blue-50 font-semibold text-blue-800" : "border-slate-200 text-slate-700"}`}
                    >
                      <input type="checkbox" className="sr-only" checked={checked} onChange={() => toggleAssignee(person.id)} />
                      {person.name}
                    </label>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Nenhuma pessoa disponível para escolher.</p>
            )}
          </fieldset>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Cancelar</Button>
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 className="animate-spin" size={16} aria-hidden="true" /> : null}
              {editing ? "Salvar alterações" : "Lançar"}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
