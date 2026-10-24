"use client";

import { AlertCircle, Archive, ArchiveRestore, CalendarClock, Loader2, Pencil, User } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { SupportPlanItemDetail, SupportPlanStatus } from "@/lib/types";

import {
  KIND_LABEL,
  PRIORITY_LABEL,
  PRIORITY_TONE,
  STATUS_LABEL,
  STATUS_ORDER,
  STATUS_TONE,
  assigneesLabel,
  dateLabel,
  dateTimeLabel,
  dueLabel,
  progressPercent,
} from "./planning-format";

// Painel lateral de um item: dados, progresso do projeto, tarefas do projeto, resultado e a linha do
// tempo de andamento. Quem tem `support:plan_write` registra andamento, muda o status e arquiva.

type Props = {
  itemId: number | null;
  canWrite: boolean;
  /** Muda a cada gravação feita fora deste painel, para ele recarregar. */
  refreshKey: number;
  onClose: () => void;
  onEdit: (item: SupportPlanItemDetail) => void;
  onOpenItem: (id: number) => void;
  onChanged: () => void;
};

export function PlanningItemSheet({ itemId, canWrite, refreshKey, onClose, onEdit, onOpenItem, onChanged }: Props) {
  const [item, setItem] = useState<SupportPlanItemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<SupportPlanStatus | "">("");
  const [result, setResult] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (itemId === null) {
      setItem(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportPlanItem(itemId)
      .then((detail) => {
        if (!cancelled) setItem(detail);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar o item. Tente novamente.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itemId, refreshKey]);

  // Trocar de item (ou gravar) limpa o formulário de andamento.
  useEffect(() => {
    setText("");
    setStatus("");
    setResult("");
    setFormError(null);
  }, [itemId, item?.version]);

  const finishing = status === "done";

  async function submitProgress(event: React.FormEvent) {
    event.preventDefault();
    if (!item) return;
    setSaving(true);
    setFormError(null);
    try {
      const saved = await api.addSupportPlanProgress(item.id, {
        version: item.version,
        text,
        ...(status ? { status } : {}),
        ...(finishing ? { result } : {}),
      });
      setItem(saved);
      onChanged();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Não foi possível registrar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleArchive() {
    if (!item) return;
    setSaving(true);
    setFormError(null);
    try {
      const saved = await api.archiveSupportPlanItem(item.id, { version: item.version, archived: !item.archived });
      setItem(saved);
      onChanged();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Não foi possível arquivar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  const percent = item ? progressPercent(item) : null;

  return (
    <Sheet open={itemId !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent className="sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{item?.title ?? "Item"}</SheetTitle>
          <SheetDescription>{item ? `${KIND_LABEL[item.kind]} · lançado por ${item.created_by_name || "—"} em ${dateTimeLabel(item.created_at)}` : "Carregando…"}</SheetDescription>
        </SheetHeader>
        <div className="grid gap-5 p-6">
          {error ? (
            <div className="flex items-center gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
              <AlertCircle size={18} aria-hidden="true" />
              <p className="mr-auto">{error}</p>
            </div>
          ) : null}
          {loading && !item ? (
            <p className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
              <Loader2 className="animate-spin" size={16} aria-hidden="true" />Carregando…
            </p>
          ) : null}
          {item ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={STATUS_TONE[item.status]} dot>{STATUS_LABEL[item.status]}</StatusBadge>
                <StatusBadge tone={PRIORITY_TONE[item.priority]}>Prioridade {PRIORITY_LABEL[item.priority].toLowerCase()}</StatusBadge>
                {item.archived ? <StatusBadge tone="slate">Arquivado</StatusBadge> : null}
                {canWrite ? (
                  <div className="ml-auto flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => onEdit(item)} disabled={saving}><Pencil size={14} aria-hidden="true" />Editar</Button>
                    <Button variant="outline" size="sm" onClick={() => void toggleArchive()} disabled={saving}>
                      {item.archived ? <ArchiveRestore size={14} aria-hidden="true" /> : <Archive size={14} aria-hidden="true" />}
                      {item.archived ? "Desarquivar" : "Arquivar"}
                    </Button>
                  </div>
                ) : null}
              </div>

              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500"><User size={12} aria-hidden="true" />Responsáveis</dt>
                  <dd className="mt-1 text-slate-800">{assigneesLabel(item)}</dd>
                </div>
                <div>
                  <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500"><CalendarClock size={12} aria-hidden="true" />Prazo</dt>
                  <dd className={`mt-1 ${item.overdue ? "font-semibold text-red-700" : "text-slate-800"}`}>{dueLabel(item)}</dd>
                </div>
                {item.parent_id ? (
                  <div className="sm:col-span-2">
                    <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Projeto</dt>
                    <dd className="mt-1">
                      <button type="button" className="text-blue-700 underline-offset-2 hover:underline" onClick={() => onOpenItem(item.parent_id as number)}>{item.parent_title}</button>
                    </dd>
                  </div>
                ) : null}
              </dl>

              {item.description ? <p className="whitespace-pre-line text-sm text-slate-800">{item.description}</p> : null}

              {item.kind === "project" ? (
                <section aria-label="Progresso do projeto" className="grid gap-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold text-slate-800">Progresso</span>
                    <span className="tabular-nums text-slate-600">{percent === null ? "Sem tarefas" : `${item.tasks_done} de ${item.tasks_total} tarefas · ${percent}%`}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={percent ?? 0} aria-valuemin={0} aria-valuemax={100}>
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${percent ?? 0}%` }} />
                  </div>
                  {item.children.length ? (
                    <ul className="mt-1 grid gap-1.5">
                      {item.children.map((child) => (
                        <li key={child.id}>
                          <button type="button" className="flex w-full items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => onOpenItem(child.id)}>
                            <StatusBadge tone={STATUS_TONE[child.status]} dot>{STATUS_LABEL[child.status]}</StatusBadge>
                            <span className="mr-auto min-w-0 truncate text-slate-800">{child.title}</span>
                            <span className={`shrink-0 text-xs ${child.overdue ? "font-semibold text-red-700" : "text-slate-500"}`}>{dueLabel(child)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </section>
              ) : null}

              {item.result ? (
                <section className="rounded-xl bg-emerald-50 p-4" aria-label="Resultado">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Resultado{item.completed_at ? ` · concluído em ${dateTimeLabel(item.completed_at)}` : ""}</p>
                  <p className="mt-1 whitespace-pre-line text-sm text-slate-800">{item.result}</p>
                </section>
              ) : null}

              {canWrite && !item.archived ? (
                <form className="grid gap-3 rounded-xl border border-slate-200 p-4" onSubmit={submitProgress}>
                  <p className="text-sm font-semibold text-slate-800">Registrar andamento</p>
                  {formError ? (
                    <div className="flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-800" role="alert">
                      <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /><p>{formError}</p>
                    </div>
                  ) : null}
                  <Textarea value={text} maxLength={3000} onChange={(event) => setText(event.target.value)} placeholder="O que foi feito, o que falta ou o que está travando" aria-label="Andamento" />
                  <Select value={status} onChange={(event) => setStatus(event.target.value as SupportPlanStatus | "")} aria-label="Novo status">
                    <option value="">Manter status ({STATUS_LABEL[item.status]})</option>
                    {STATUS_ORDER.filter((key) => key !== item.status).map((key) => (
                      <option key={key} value={key}>Mudar para {STATUS_LABEL[key].toLowerCase()}</option>
                    ))}
                  </Select>
                  {finishing ? (
                    <Textarea value={result} maxLength={5000} onChange={(event) => setResult(event.target.value)} placeholder="Resultado: o que foi feito e o que mudou" aria-label="Resultado" />
                  ) : null}
                  <div className="flex justify-end">
                    <Button type="submit" size="sm" disabled={saving || (!text.trim() && !status)}>
                      {saving ? <Loader2 className="animate-spin" size={14} aria-hidden="true" /> : null}Registrar
                    </Button>
                  </div>
                </form>
              ) : formError ? (
                <p className="text-sm text-rose-700" role="alert">{formError}</p>
              ) : null}

              <section aria-label="Linha do tempo" className="grid gap-3">
                <p className="text-sm font-semibold text-slate-800">Linha do tempo</p>
                {item.updates.length ? (
                  <ol className="grid gap-3 border-l border-slate-200 pl-4">
                    {item.updates.map((update) => (
                      <li key={update.id} className="relative">
                        <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-slate-300" aria-hidden="true" />
                        <p className="text-xs text-slate-500">
                          <span className="font-semibold text-slate-700">{update.author_name || "—"}</span> · {dateTimeLabel(update.created_at)}
                          {update.status_to ? ` · ${update.status_from ? STATUS_LABEL[update.status_from] : "—"} → ${STATUS_LABEL[update.status_to]}` : ""}
                        </p>
                        {update.text ? <p className="mt-0.5 whitespace-pre-line text-sm text-slate-800">{update.text}</p> : null}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-sm text-slate-500">Nenhum andamento registrado ainda.</p>
                )}
                <p className="text-xs text-slate-400">Atualizado em {dateTimeLabel(item.updated_at)} · prazo {dateLabel(item.due_date)}</p>
              </section>
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
