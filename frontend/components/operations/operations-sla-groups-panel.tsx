"use client";

import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import {
  operationsApi,
  type OperationSlaCatalogSubject,
  type OperationSlaGroup,
} from "@/lib/operations-api";

/**
 * Configuração dos grupos de "SLA por tecnologia" da Visão Geral (pedido do usuário em
 * 2026-09-18: os 6 grupos - Ativação/Suporte x Fibra Urbana/Fibra Rural/Rádio - eram um
 * dicionário fixo no backend; agora vivem em `operations_sla_groups`/
 * `operations_sla_subject_groups` e são editáveis aqui: criar/renomear/excluir card e grupo,
 * mover assunto entre grupos). Painel autocontido (busca os próprios dados), no mesmo padrão de
 * `OperationsBranchCapacityPanel`.
 */
export function OperationsSlaGroupsPanel({ canManage }: { canManage: boolean }) {
  const [groups, setGroups] = useState<OperationSlaGroup[]>([]);
  const [catalog, setCatalog] = useState<OperationSlaCatalogSubject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newCardLabel, setNewCardLabel] = useState("");
  const [newName, setNewName] = useState("");
  const [savingCreate, setSavingCreate] = useState(false);
  const [renaming, setRenaming] = useState<Record<number, string>>({});
  const [subjectsDialogGroup, setSubjectsDialogGroup] = useState<OperationSlaGroup | null>(null);
  const [subjectsDraft, setSubjectsDraft] = useState<string[]>([]);
  const [subjectsSearch, setSubjectsSearch] = useState("");
  const [savingSubjects, setSavingSubjects] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<OperationSlaGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [groupsResult, catalogResult] = await Promise.all([
        operationsApi.slaGroups(),
        canManage ? operationsApi.slaCatalogSubjects() : Promise.resolve([]),
      ]);
      setGroups(groupsResult);
      setCatalog(catalogResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao carregar os grupos de SLA.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManage]);

  const cards = useMemo(() => {
    const byCard = new Map<string, OperationSlaGroup[]>();
    for (const group of groups) {
      const list = byCard.get(group.card_label) ?? [];
      list.push(group);
      byCard.set(group.card_label, list);
    }
    Array.from(byCard.values()).forEach((list) => list.sort((a, b) => a.display_order - b.display_order));
    return Array.from(byCard.entries()).sort((a, b) => a[0].localeCompare(b[0], "pt-BR"));
  }, [groups]);

  const filteredCatalog = useMemo(() => {
    const normalized = subjectsSearch.trim().toLocaleLowerCase("pt-BR");
    const filtered = normalized
      ? catalog.filter((item) => item.subject.toLocaleLowerCase("pt-BR").includes(normalized))
      : catalog;
    // Selecionados primeiro - com 120+ assuntos catalogados, o que já está marcado não pode
    // depender de rolar a lista inteira pra confirmar.
    return [...filtered].sort((a, b) => {
      const aSelected = subjectsDraft.includes(a.subject);
      const bSelected = subjectsDraft.includes(b.subject);
      if (aSelected !== bSelected) return aSelected ? -1 : 1;
      return b.order_count - a.order_count;
    });
  }, [catalog, subjectsSearch, subjectsDraft]);

  async function createGroup() {
    if (!newCardLabel.trim() || !newName.trim()) return;
    setSavingCreate(true);
    setError(null);
    try {
      await operationsApi.createSlaGroup({ card_label: newCardLabel.trim(), name: newName.trim() });
      setCreating(false);
      setNewCardLabel("");
      setNewName("");
      setMessage("Grupo criado.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao criar o grupo.");
    } finally {
      setSavingCreate(false);
    }
  }

  async function saveRename(group: OperationSlaGroup) {
    const nextName = renaming[group.id];
    if (nextName === undefined || nextName.trim() === group.name) {
      setRenaming((current) => {
        const copy = { ...current };
        delete copy[group.id];
        return copy;
      });
      return;
    }
    try {
      await operationsApi.updateSlaGroup(group.id, { name: nextName.trim() });
      setRenaming((current) => {
        const copy = { ...current };
        delete copy[group.id];
        return copy;
      });
      setMessage("Grupo renomeado.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao renomear o grupo.");
    }
  }

  function openSubjectsDialog(group: OperationSlaGroup) {
    setSubjectsDialogGroup(group);
    setSubjectsDraft(group.subjects);
    setSubjectsSearch("");
  }

  function toggleSubject(subject: string) {
    setSubjectsDraft((current) =>
      current.includes(subject) ? current.filter((item) => item !== subject) : [...current, subject],
    );
  }

  async function saveSubjects() {
    if (!subjectsDialogGroup) return;
    setSavingSubjects(true);
    try {
      await operationsApi.setSlaGroupSubjects(subjectsDialogGroup.id, subjectsDraft);
      setSubjectsDialogGroup(null);
      setMessage("Assuntos atualizados.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar os assuntos do grupo.");
    } finally {
      setSavingSubjects(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await operationsApi.deleteSlaGroup(deleteTarget.id);
      setDeleteTarget(null);
      setMessage("Grupo excluído. Os assuntos dele ficam sem grupo até serem realocados.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir o grupo.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <CardContent className="space-y-4 p-4">
      <StatusToast
        message={message}
        error={error}
        onDismissMessage={() => setMessage(null)}
        onDismissError={() => setError(null)}
      />

      <p className="text-xs text-slate-500">
        Cada card abaixo (ex.: "SLA de Ativação") aparece como um bloco de gauges na Visão Geral. Um assunto de O.S.
        só pode estar em um grupo por vez - atribuir a outro grupo move automaticamente.
      </p>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Carregando grupos...
        </div>
      ) : (
        <div className="grid gap-4">
          {cards.map(([cardLabel, cardGroups]) => (
            <div key={cardLabel} className="rounded-xl border border-slate-200 p-3">
              <p className="text-sm font-semibold text-slate-800">{cardLabel}</p>
              <div className="mt-2 grid gap-2">
                {cardGroups.map((group) => (
                  <div
                    key={group.id}
                    className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 p-2"
                  >
                    <Input
                      value={renaming[group.id] ?? group.name}
                      disabled={!canManage}
                      onChange={(event) =>
                        setRenaming((current) => ({ ...current, [group.id]: event.target.value }))
                      }
                      onBlur={() => canManage && void saveRename(group)}
                      className="h-8 max-w-[220px] flex-1 text-sm"
                    />
                    <span className="text-[11px] text-slate-500">{group.subjects.length} assunto(s)</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={!canManage}
                      onClick={() => openSubjectsDialog(group)}
                    >
                      Assuntos
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={!canManage}
                      onClick={() => setDeleteTarget(group)}
                      className="text-red-600 hover:bg-red-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {cards.length === 0 ? (
            <p className="text-sm text-slate-500">Nenhum grupo cadastrado ainda.</p>
          ) : null}
        </div>
      )}

      {canManage ? (
        creating ? (
          <div className="grid gap-2 rounded-xl border border-blue-200 bg-blue-50 p-3 sm:grid-cols-[1fr_1fr_auto]">
            <Input
              placeholder="Card (ex.: SLA de Ativação)"
              value={newCardLabel}
              onChange={(event) => setNewCardLabel(event.target.value)}
              className="h-8 text-sm"
            />
            <Input
              placeholder="Nome do grupo (ex.: Ativação Fibra Urbana)"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              className="h-8 text-sm"
            />
            <div className="flex gap-2">
              <Button type="button" size="sm" disabled={savingCreate} onClick={() => void createGroup()}>
                {savingCreate ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Criar
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setCreating(false)}>
                Cancelar
              </Button>
            </div>
          </div>
        ) : (
          <Button type="button" size="sm" variant="outline" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" /> Novo grupo
          </Button>
        )
      ) : null}

      <Dialog open={subjectsDialogGroup !== null} onOpenChange={(open) => !open && setSubjectsDialogGroup(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Assuntos de &quot;{subjectsDialogGroup?.name}&quot;</DialogTitle>
            <DialogDescription>
              Assuntos já vistos em alguma O.S. importada. Marcar um assunto já atribuído a outro grupo move a
              atribuição para este. {subjectsDraft.length} selecionado(s).
            </DialogDescription>
          </DialogHeader>
          {/* Lista inline, sem Popover flutuante: um Popover (Radix/Floating UI) aninhado dentro
              deste Dialog media a posição errada enquanto a animação de abertura do modal ainda
              tem um `transform` ativo (scale de entrada) - achado real, 2026-09-18, o Popover
              renderizava ~450px acima do botão. Lista simples evita a classe de bug inteira. */}
          <Input
            placeholder="Buscar assunto..."
            value={subjectsSearch}
            onChange={(event) => setSubjectsSearch(event.target.value)}
            className="h-8 text-sm"
          />
          <div className="max-h-[320px] overflow-y-auto rounded-lg border border-slate-200">
            {filteredCatalog.length === 0 ? (
              <p className="p-3 text-sm text-slate-500">Nenhum assunto encontrado.</p>
            ) : (
              filteredCatalog.map((item) => {
                const checked = subjectsDraft.includes(item.subject);
                const movingFromOther = item.group_id !== null && item.group_id !== subjectsDialogGroup?.id;
                return (
                  <label
                    key={item.subject}
                    className="flex items-center gap-2 border-b border-slate-100 px-3 py-2 text-sm last:border-b-0 hover:bg-slate-50"
                  >
                    <AppCheckbox
                      checked={checked}
                      onCheckedChange={() => toggleSubject(item.subject)}
                      ariaLabel={`Selecionar ${item.subject}`}
                    />
                    <span className="min-w-0 flex-1 truncate">{item.subject}</span>
                    {movingFromOther ? (
                      <span className="shrink-0 text-[10px] text-amber-600">atualmente em &quot;{item.group_name}&quot;</span>
                    ) : (
                      <span className="shrink-0 text-[10px] text-slate-400">{item.order_count} O.S.</span>
                    )}
                  </label>
                );
              })
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSubjectsDialogGroup(null)}>
              Cancelar
            </Button>
            <Button type="button" disabled={savingSubjects} onClick={() => void saveSubjects()}>
              {savingSubjects ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir &quot;{deleteTarget?.name}&quot;?</DialogTitle>
            <DialogDescription>
              Os {deleteTarget?.subjects.length ?? 0} assunto(s) deste grupo ficam sem grupo (aparecem como
              &quot;Outros&quot; no SLA por tecnologia) até serem realocados para outro grupo.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancelar
            </Button>
            <Button type="button" disabled={deleting} onClick={() => void confirmDelete()} className="bg-red-600 hover:bg-red-700">
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Excluir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </CardContent>
  );
}
