"use client";

import { AlertCircle, Archive, ArchiveRestore, CalendarClock, CheckCheck, Loader2, Pencil, Plus, User } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { SupportPlanChild, SupportPlanHealth, SupportPlanItemDetail, SupportPlanKind, SupportPlanStatus } from "@/lib/types";

import {
  CHILD_LABEL,
  HEALTH_LABEL,
  HEALTH_ORDER,
  HEALTH_TONE,
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
  isClosed,
  itemProgress,
} from "./planning-format";

// Painel lateral de um item: dados, avanço, o que há dentro (projeto > resultados-chave > ações; tarefas no projeto),
// check-in da ação, resultado e a linha do tempo. Quem tem `support:plan_write` registra andamento, dá check-in,
// muda o status e arquiva.

type Props = {
  itemId: number | null;
  canWrite: boolean;
  /** Muda a cada gravação feita fora deste painel, para ele recarregar. */
  refreshKey: number;
  onClose: () => void;
  onEdit: (item: SupportPlanItemDetail) => void;
  onOpenItem: (id: number) => void;
  /** Lança um resultado-chave (dentro de projeto) ou uma ação (dentro de resultado-chave). */
  onCreateChild: (kind: SupportPlanKind, parent: { id: number; title: string }) => void;
  onChanged: () => void;
};

function ChildRow({ child, onOpen }: { child: SupportPlanChild; onOpen: (id: number) => void }) {
  return (
    <li>
      <button type="button" className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => onOpen(child.id)}>
        <StatusBadge tone={STATUS_TONE[child.status]} dot>{STATUS_LABEL[child.status]}</StatusBadge>
        <span className="mr-auto min-w-0 truncate text-slate-800">{child.title}</span>
        {child.kind === "key_result" ? <span className="shrink-0 text-xs text-slate-500">{child.children_total} {child.children_total === 1 ? "ação" : "ações"}</span> : null}
        {child.health ? <StatusBadge tone={HEALTH_TONE[child.health]}>{HEALTH_LABEL[child.health]}</StatusBadge> : null}
        {child.progress !== null ? <span className="shrink-0 text-xs font-semibold tabular-nums text-slate-700">{child.progress}%</span> : null}
        <span className={`shrink-0 text-xs ${child.overdue ? "font-semibold text-red-700" : "text-slate-500"}`}>{dueLabel(child)}</span>
      </button>
    </li>
  );
}

export function PlanningItemSheet({ itemId, canWrite, refreshKey, onClose, onEdit, onOpenItem, onCreateChild, onChanged }: Props) {
  const [item, setItem] = useState<SupportPlanItemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<SupportPlanStatus | "">("");
  const [result, setResult] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // Check-in da ação: avanço, situação e o que andou.
  const [checkInText, setCheckInText] = useState("");
  const [checkInProgress, setCheckInProgress] = useState(0);
  const [checkInHealth, setCheckInHealth] = useState<SupportPlanHealth>("on_track");

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
    setCheckInText("");
    setCheckInProgress(item?.progress ?? 0);
    setCheckInHealth(item?.health ?? "on_track");
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

  async function submitCheckIn(event: React.FormEvent) {
    event.preventDefault();
    if (!item) return;
    setSaving(true);
    setFormError(null);
    try {
      const saved = await api.addSupportPlanCheckIn(item.id, { version: item.version, text: checkInText, progress: checkInProgress, health: checkInHealth });
      setItem(saved);
      onChanged();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Não foi possível registrar o check-in. Tente novamente.");
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

  const percent = item ? itemProgress(item) : null;
  const childKind = item ? CHILD_LABEL[item.kind] : undefined;
  // O que aparece dentro: projeto tem resultados-chave e tarefas; resultado-chave tem ações.
  const groups: { title: string; kind: SupportPlanKind }[] =
    item?.kind === "project" ? [{ title: "Resultados-chave", kind: "key_result" }, { title: "Tarefas", kind: "task" }] : item?.kind === "key_result" ? [{ title: "Ações", kind: "action" }] : [];

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
                    <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{item.kind === "action" ? "Resultado-chave" : "Projeto"}</dt>
                    <dd className="mt-1">
                      <button type="button" className="text-blue-700 underline-offset-2 hover:underline" onClick={() => onOpenItem(item.parent_id as number)}>{item.parent_title}</button>
                    </dd>
                  </div>
                ) : null}
              </dl>

              {item.description ? <p className="whitespace-pre-line text-sm text-slate-800">{item.description}</p> : null}

              {item.kind !== "task" ? (
                <section aria-label="Avanço" className="grid gap-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold text-slate-800">Avanço</span>
                    <span className="tabular-nums text-slate-600">{percent === null ? "Nada lançado ainda" : `${percent}%`}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={percent ?? 0} aria-valuemin={0} aria-valuemax={100}>
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${percent ?? 0}%` }} />
                  </div>
                  {item.kind === "action" ? (
                    <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      {item.health ? <StatusBadge tone={HEALTH_TONE[item.health]}>{HEALTH_LABEL[item.health]}</StatusBadge> : null}
                      {item.last_check_in_at ? `Último check-in em ${dateTimeLabel(item.last_check_in_at)}` : "Nenhum check-in ainda."}
                    </p>
                  ) : null}
                </section>
              ) : null}

              {groups.map((group, index) => {
                const list = item.children.filter((child) => child.kind === group.kind);
                const creatable = index === 0 && childKind && canWrite && !item.archived;
                return (
                  <section key={group.kind} aria-label={group.title} className="grid gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-slate-800">{group.title}{list.length ? ` (${list.length})` : ""}</p>
                      {creatable ? (
                        <Button variant="outline" size="sm" onClick={() => onCreateChild(childKind.kind, { id: item.id, title: item.title })}>
                          <Plus size={14} aria-hidden="true" />{childKind.new}
                        </Button>
                      ) : null}
                    </div>
                    {list.length ? (
                      <ul className="grid gap-1.5">
                        {list.map((child) => <ChildRow key={child.id} child={child} onOpen={onOpenItem} />)}
                      </ul>
                    ) : (
                      <p className="text-sm text-slate-500">{group.kind === "task" ? "Nenhuma tarefa neste projeto." : `Nenhum${group.kind === "action" ? "a ação" : " resultado-chave"} lançad${group.kind === "action" ? "a" : "o"} ainda.`}</p>
                    )}
                  </section>
                );
              })}

              {item.result ? (
                <section className="rounded-xl bg-emerald-50 p-4" aria-label="Resultado">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Resultado{item.completed_at ? ` · concluído em ${dateTimeLabel(item.completed_at)}` : ""}</p>
                  <p className="mt-1 whitespace-pre-line text-sm text-slate-800">{item.result}</p>
                </section>
              ) : null}

              {canWrite && !item.archived && item.kind === "action" && !isClosed(item.status) ? (
                <form className="grid gap-3 rounded-xl border border-uni-turquoise/50 bg-uni-mist/30 p-4" onSubmit={submitCheckIn}>
                  <p className="flex items-center gap-2 text-sm font-semibold text-slate-800"><CheckCheck size={16} aria-hidden="true" />Check-in</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1.5 text-sm text-slate-700">
                      <span>Avanço: <span className="font-semibold tabular-nums">{checkInProgress}%</span></span>
                      <input type="range" min={0} max={100} step={5} value={checkInProgress} onChange={(event) => setCheckInProgress(Number(event.target.value))} aria-label="Avanço" />
                    </label>
                    <label className="grid gap-1.5 text-sm text-slate-700">
                      <span>Situação</span>
                      <Select value={checkInHealth} onChange={(event) => setCheckInHealth(event.target.value as SupportPlanHealth)} aria-label="Situação">
                        {HEALTH_ORDER.map((key) => <option key={key} value={key}>{HEALTH_LABEL[key]}</option>)}
                      </Select>
                    </label>
                  </div>
                  <Textarea value={checkInText} maxLength={3000} onChange={(event) => setCheckInText(event.target.value)} placeholder="O que andou desde o último check-in, o que falta e o que está travando" aria-label="Check-in" />
                  <div className="flex justify-end">
                    <Button type="submit" size="sm" disabled={saving || !checkInText.trim()}>
                      {saving ? <Loader2 className="animate-spin" size={14} aria-hidden="true" /> : null}Registrar check-in
                    </Button>
                  </div>
                </form>
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
                          {update.is_check_in ? ` · check-in ${update.progress ?? 0}%${update.health ? ` · ${HEALTH_LABEL[update.health]}` : ""}` : ""}
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
