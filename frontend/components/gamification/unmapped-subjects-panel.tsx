"use client";

import { ClipboardList, Info, Link2, Plus, Save, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { AppCombobox, AppInput, StatusBadge } from "@/components/gamification/config-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ScoringGroup, UnmappedSubject } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function severityTone(serviceOrdersCount: number): "danger" | "warning" | "neutral" {
  if (serviceOrdersCount >= 50) return "danger";
  if (serviceOrdersCount >= 10) return "warning";
  return "neutral";
}

type Props = {
  groups: ScoringGroup[];
  subjects: UnmappedSubject[];
  // Tipos Gerais já cadastrados em alguma regra - lista fechada: o usuário escolhe um destes, não
  // digita um valor novo (evita variações/erros de digitação criando categorias divergentes).
  osTypeOptions: string[];
  onLinkSubject: (subject: UnmappedSubject, groupId: number, osType: string) => Promise<void>;
  onLinkSubjects: (items: Array<{ subject: UnmappedSubject; groupId: number; osType: string }>) => Promise<void>;
  onCreateGroupForSubject: (subject: UnmappedSubject, osType: string) => Promise<void>;
};

export function UnmappedSubjectsPanel({
  groups,
  subjects,
  osTypeOptions,
  onLinkSubject,
  onLinkSubjects,
  onCreateGroupForSubject
}: Props) {
  const [query, setQuery] = useState("");
  const [selectedGroups, setSelectedGroups] = useState<Record<string, number>>({});
  const [selectedOsTypes, setSelectedOsTypes] = useState<Record<string, string>>({});
  const [bulkGroupId, setBulkGroupId] = useState("");
  const [bulkOsType, setBulkOsType] = useState("");

  const knownOsTypes = useMemo(() => new Set(osTypeOptions), [osTypeOptions]);
  const osTypeSelectOptions = useMemo(() => osTypeOptions.map((type) => ({ value: type, label: type })), [osTypeOptions]);

  const filteredSubjects = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const base = normalized
      ? subjects.filter((subject) =>
          [subject.os_type, subject.os_subject, subject.predominant_regional].some((value) =>
            value.toLowerCase().includes(normalized)
          )
        )
      : subjects;
    return [...base].sort((a, b) => b.service_orders_count - a.service_orders_count);
  }, [query, subjects]);

  function subjectKey(subject: UnmappedSubject) {
    return `${subject.os_type}::${subject.os_subject}`;
  }

  // O Tipo Geral que veio junto da O.S (subject.os_type) só serve de sugestão pré-preenchida quando
  // parece uma classificação de verdade (já usada por alguma regra) - nunca pré-preenche com um
  // marcador de pendência ou nome de setor, porque o usuário precisa escolher/confirmar ativamente
  // (é exatamente essa escolha implícita, herdada sem ninguém decidir, que causava o problema).
  function initialOsType(subject: UnmappedSubject) {
    return knownOsTypes.has(subject.os_type) ? subject.os_type : "";
  }

  function osTypeFor(subject: UnmappedSubject) {
    const key = subjectKey(subject);
    return key in selectedOsTypes ? selectedOsTypes[key] : initialOsType(subject);
  }

  const selectedItems = useMemo(
    () =>
      subjects
        .map((subject) => ({
          subject,
          groupId: selectedGroups[subjectKey(subject)],
          osType: (osTypeFor(subject) || "").trim()
        }))
        .filter(
          (item): item is { subject: UnmappedSubject; groupId: number; osType: string } =>
            Boolean(item.groupId) && Boolean(item.osType)
        ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedGroups, selectedOsTypes, subjects]
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

  function updateSubjectOsType(subject: UnmappedSubject, value: string) {
    const key = subjectKey(subject);
    setSelectedOsTypes((current) => ({ ...current, [key]: value }));
  }

  function applyBulkGroupToFiltered() {
    if (!bulkGroupId) return;
    const next = { ...selectedGroups };
    for (const subject of filteredSubjects) {
      next[subjectKey(subject)] = Number(bulkGroupId);
    }
    setSelectedGroups(next);
  }

  function applyBulkOsTypeToFiltered() {
    const nextValue = bulkOsType.trim();
    if (!nextValue) return;
    setSelectedOsTypes((current) => {
      const next = { ...current };
      for (const subject of filteredSubjects) {
        next[subjectKey(subject)] = nextValue;
      }
      return next;
    });
  }

  async function link(subject: UnmappedSubject) {
    const groupId = selectedGroups[subjectKey(subject)];
    const osType = osTypeFor(subject).trim();
    if (!groupId || !osType) return;
    await onLinkSubject(subject, groupId, osType);
  }

  async function saveBulkLinks() {
    if (!selectedItems.length) return;
    await onLinkSubjects(selectedItems);
    setSelectedGroups({});
    setSelectedOsTypes({});
  }

  async function createGroup(subject: UnmappedSubject) {
    const osType = osTypeFor(subject).trim();
    if (!osType) return;
    await onCreateGroupForSubject(subject, osType);
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
            <AppInput
              id="unmapped-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-9"
              placeholder="Tipo, assunto ou regional"
            />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 border-b bg-amber-50 px-5 py-3 text-sm text-amber-800">
        <Info className="h-4 w-4 shrink-0" />
        Escolha o Tipo Geral e o grupo corretos de cada assunto e recalcule para atualizar ranking, auditoria e valor a ser pago.
      </div>

      <div className="grid gap-3 border-b bg-white px-5 py-4 lg:grid-cols-[minmax(200px,1fr)_minmax(240px,1fr)_auto_auto_auto] lg:items-end">
        <div className="grid gap-2">
          <Label>Aplicar Tipo Geral aos assuntos filtrados</Label>
          <AppCombobox
            value={bulkOsType}
            onChange={setBulkOsType}
            placeholder="Selecionar Tipo Geral"
            ariaLabel="Aplicar Tipo Geral aos assuntos filtrados"
            options={osTypeSelectOptions}
          />
        </div>
        <div className="grid gap-2">
          <Label>Aplicar grupo aos assuntos filtrados</Label>
          <AppCombobox
            value={bulkGroupId}
            onChange={setBulkGroupId}
            placeholder="Selecione um grupo"
            ariaLabel="Aplicar grupo aos assuntos filtrados"
            options={groups.map((group) => ({
              value: String(group.id),
              label: `${group.name} (${numberFormat.format(group.default_points)} pts)`,
            }))}
          />
        </div>
        <Button
          variant="outline"
          onClick={() => {
            applyBulkOsTypeToFiltered();
            applyBulkGroupToFiltered();
          }}
          disabled={(!bulkGroupId && !bulkOsType.trim()) || filteredSubjects.length === 0}
        >
          Aplicar aos filtrados
        </Button>
        <Button onClick={saveBulkLinks} disabled={selectedItems.length === 0}>
          <Save className="h-4 w-4" />
          Salvar {numberFormat.format(selectedItems.length)} vínculo(s)
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setSelectedGroups({});
            setSelectedOsTypes({});
          }}
          disabled={selectedItems.length === 0}
        >
          <X className="h-4 w-4" />
          Limpar seleção
        </Button>
      </div>

      <div className="border-b bg-slate-50 px-5 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {selectedItems.length > 0
          ? `${numberFormat.format(selectedItems.length)} assunto(s) com Tipo Geral e grupo selecionados para salvar em massa.`
          : "Escolha o Tipo Geral e o grupo nas linhas (ambos obrigatórios) antes de salvar."}
      </div>

      <div className="table-frame">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
            <TableRow className="border-slate-700 hover:bg-slate-900">
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
              const osType = osTypeFor(subject);
              const canAct = Boolean(selectedGroups[key]) && Boolean(osType.trim());
              return (
                <TableRow key={key}>
                  <TableCell className="min-w-56">
                    <AppCombobox
                      value={osType}
                      onChange={(value) => updateSubjectOsType(subject, value)}
                      placeholder="Selecionar Tipo Geral"
                      ariaLabel={`Tipo Geral do assunto ${subject.os_subject}`}
                      options={osTypeSelectOptions}
                    />
                    {!knownOsTypes.has(subject.os_type) ? (
                      <p className="mt-1 text-xs text-amber-700">Origem: "{subject.os_type}" (não classificado)</p>
                    ) : null}
                  </TableCell>
                  <TableCell className="min-w-80 font-medium text-slate-950">{subject.os_subject}</TableCell>
                  <TableCell>
                    <StatusBadge tone={severityTone(subject.service_orders_count)}>
                      {numberFormat.format(subject.service_orders_count)}
                    </StatusBadge>
                  </TableCell>
                  <TableCell>{numberFormat.format(subject.collaborators_count)}</TableCell>
                  <TableCell>{subject.predominant_regional}</TableCell>
                  <TableCell className="font-medium text-uni-royal">
                    {moneyFormat.format(subject.estimated_financial_impact)}
                  </TableCell>
                  <TableCell className="min-w-64">
                    <AppCombobox
                      value={selectedGroups[key] ? String(selectedGroups[key]) : ""}
                      onChange={(value) => updateSubjectGroup(subject, value)}
                      placeholder="Selecionar grupo"
                      ariaLabel={`Grupo destino do assunto ${subject.os_subject}`}
                      options={groups.map((group) => ({
                        value: String(group.id),
                        label: `${group.name} (${numberFormat.format(group.default_points)} pts)`,
                      }))}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => link(subject)} disabled={!canAct}>
                        <Link2 className="h-4 w-4" />
                        Vincular
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => createGroup(subject)} disabled={!osType.trim()}>
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
