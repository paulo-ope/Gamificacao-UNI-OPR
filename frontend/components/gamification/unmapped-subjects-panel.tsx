"use client";

import { ClipboardList, Link2, Plus, Save, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ScoringGroup, UnmappedSubject } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

type Props = {
  groups: ScoringGroup[];
  subjects: UnmappedSubject[];
  onLinkSubject: (subject: UnmappedSubject, groupId: number) => Promise<void>;
  onLinkSubjects: (items: Array<{ subject: UnmappedSubject; groupId: number }>) => Promise<void>;
  onCreateGroupForSubject: (subject: UnmappedSubject) => Promise<void>;
};

export function UnmappedSubjectsPanel({ groups, subjects, onLinkSubject, onLinkSubjects, onCreateGroupForSubject }: Props) {
  const [query, setQuery] = useState("");
  const [selectedGroups, setSelectedGroups] = useState<Record<string, number>>({});
  const [bulkGroupId, setBulkGroupId] = useState("");

  const filteredSubjects = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return subjects;
    return subjects.filter((subject) =>
      [subject.os_type, subject.os_subject, subject.predominant_regional].some((value) =>
        value.toLowerCase().includes(normalized)
      )
    );
  }, [query, subjects]);

  function subjectKey(subject: UnmappedSubject) {
    return `${subject.os_type}::${subject.os_subject}`;
  }

  const selectedItems = useMemo(
    () =>
      subjects
        .map((subject) => ({ subject, groupId: selectedGroups[subjectKey(subject)] }))
        .filter((item): item is { subject: UnmappedSubject; groupId: number } => Boolean(item.groupId)),
    [selectedGroups, subjects]
  );

  function updateSubjectGroup(subject: UnmappedSubject, value: string) {
    const key = subjectKey(subject);
    const next = { ...selectedGroups };
    if (value) {
      next[key] = Number(value);
    } else {
      delete next[key];
    }
    setSelectedGroups(next);
  }

  function applyBulkGroupToFiltered() {
    if (!bulkGroupId) return;
    const next = { ...selectedGroups };
    for (const subject of filteredSubjects) {
      next[subjectKey(subject)] = Number(bulkGroupId);
    }
    setSelectedGroups(next);
  }

  async function link(subject: UnmappedSubject) {
    const groupId = selectedGroups[subjectKey(subject)];
    if (!groupId) return;
    await onLinkSubject(subject, groupId);
  }

  async function saveBulkLinks() {
    if (!selectedItems.length) return;
    await onLinkSubjects(selectedItems);
    setSelectedGroups({});
  }

  return (
    <section className="panel overflow-hidden">
      <div className="panel-header bg-slate-50/70">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-amber-200 bg-white text-amber-700">
            <ClipboardList className="h-5 w-5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="panel-title">Assuntos sem regra</h2>
              <Badge className="border-amber-200 bg-amber-50 text-amber-700">
                {numberFormat.format(subjects.length)} item(ns)
              </Badge>
            </div>
            <p className="panel-subtitle">Fila operacional do que ainda não pontua e precisa de governança antes do fechamento.</p>
          </div>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-96">
          <Label htmlFor="unmapped-search">Buscar assunto</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <Input
              id="unmapped-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-9"
              placeholder="Tipo, assunto ou regional"
            />
          </div>
        </div>
      </div>

      <div className="border-b bg-amber-50 px-5 py-3 text-sm text-amber-800">
        Vincule cada assunto ao grupo correto e recalcule para atualizar ranking, auditoria e valor a ser pago.
      </div>

      <div className="grid gap-3 border-b bg-white px-5 py-4 lg:grid-cols-[minmax(240px,1fr)_auto_auto_auto] lg:items-end">
        <div className="grid gap-2">
          <Label>Aplicar grupo aos assuntos filtrados</Label>
          <select
            className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
            value={bulkGroupId}
            onChange={(event) => setBulkGroupId(event.target.value)}
          >
            <option value="">Selecione um grupo</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name} ({numberFormat.format(group.default_points)} pts)
              </option>
            ))}
          </select>
        </div>
        <Button variant="outline" onClick={applyBulkGroupToFiltered} disabled={!bulkGroupId || filteredSubjects.length === 0}>
          Aplicar aos filtrados
        </Button>
        <Button onClick={saveBulkLinks} disabled={selectedItems.length === 0}>
          <Save className="h-4 w-4" />
          Salvar {numberFormat.format(selectedItems.length)} vínculo(s)
        </Button>
        <Button variant="ghost" onClick={() => setSelectedGroups({})} disabled={selectedItems.length === 0}>
          <X className="h-4 w-4" />
          Limpar seleção
        </Button>
      </div>

      <div className="border-b bg-slate-50 px-5 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {selectedItems.length > 0
          ? `${numberFormat.format(selectedItems.length)} assunto(s) selecionado(s) para salvar em massa.`
          : "Selecione grupos nas linhas ou aplique um grupo aos assuntos filtrados antes de salvar."}
      </div>

      <div className="table-frame">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tipo Geral</TableHead>
              <TableHead>Assunto</TableHead>
              <TableHead>Qtd O.S</TableHead>
              <TableHead>Colaboradores</TableHead>
              <TableHead>Regional predominante</TableHead>
              <TableHead>Impacto estimado</TableHead>
              <TableHead>Grupo destino</TableHead>
              <TableHead>Ação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredSubjects.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-28 text-center text-sm text-slate-500">
                  Nenhum assunto sem regra encontrado para os filtros atuais.
                </TableCell>
              </TableRow>
            ) : null}
            {filteredSubjects.map((subject) => {
              const key = subjectKey(subject);
              return (
                <TableRow key={key}>
                  <TableCell className="min-w-44">{subject.os_type}</TableCell>
                  <TableCell className="min-w-80 font-medium text-slate-950">{subject.os_subject}</TableCell>
                  <TableCell>
                    <Badge className="border-amber-200 bg-amber-50 text-amber-700">
                      {numberFormat.format(subject.service_orders_count)}
                    </Badge>
                  </TableCell>
                  <TableCell>{numberFormat.format(subject.collaborators_count)}</TableCell>
                  <TableCell>{subject.predominant_regional}</TableCell>
                  <TableCell className="font-medium text-teal-700">
                    {moneyFormat.format(subject.estimated_financial_impact)}
                  </TableCell>
                  <TableCell className="min-w-64">
                    <select
                      className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
                      value={selectedGroups[key] || ""}
                      onChange={(event) => updateSubjectGroup(subject, event.target.value)}
                    >
                      <option value="">Selecionar grupo</option>
                      {groups.map((group) => (
                        <option key={group.id} value={group.id}>
                          {group.name} ({numberFormat.format(group.default_points)} pts)
                        </option>
                      ))}
                    </select>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => link(subject)} disabled={!selectedGroups[key]}>
                        <Link2 className="h-4 w-4" />
                        Vincular
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => onCreateGroupForSubject(subject)}>
                        <Plus className="h-4 w-4" />
                        Criar Grupo
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}



