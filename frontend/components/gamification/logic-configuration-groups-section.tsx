"use client";

import { Trash2 } from "lucide-react";

import {
  AppInput,
  DataTableFrame,
  FilterToolbar,
  GuidanceCard,
  RowActionMenu,
  ToolbarCount,
} from "@/components/gamification/config-ui";
import { groupSnapshot, sameGroupSnapshot } from "@/components/gamification/logic-configuration-helpers";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatInteger, formatMoney, formatPoints } from "@/lib/format";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import { cn } from "@/lib/utils";
import type { ScoringGroup } from "@/lib/types";
import type { GroupSnapshot } from "@/components/gamification/logic-configuration-helpers";

type GroupWithStats = {
  group: ScoringGroup;
  rules: unknown[];
  orders: number;
  impact: number;
};

type Props = {
  newGroupDraft: { name: string; default_points: number };
  setNewGroupDraft: (updater: (current: { name: string; default_points: number }) => { name: string; default_points: number }) => void;
  createGroup: () => Promise<void>;
  busy: boolean;
  subjectsByGroup: GroupWithStats[];
  selectedVisibleGroups: GroupWithStats[];
  setDeleteGroupSelectionOpen: (open: boolean) => void;
  allVisibleGroupsSelected: boolean;
  toggleAllVisibleGroups: (checked: boolean) => void;
  groupBaselines: Record<number, GroupSnapshot>;
  selectedGroupIds: Set<number>;
  toggleGroupSelected: (id: number, checked: boolean) => void;
  globalPointValueLabel: string;
  setEditingGroupId: (id: number | null) => void;
  duplicateGroup: (group: ScoringGroup) => Promise<void>;
  restoreGroup: (groupId: number) => void;
  setPendingDeleteGroupId: (id: number | null) => void;
};

export function GroupsSection({
  newGroupDraft,
  setNewGroupDraft,
  createGroup,
  busy,
  subjectsByGroup,
  selectedVisibleGroups,
  setDeleteGroupSelectionOpen,
  allVisibleGroupsSelected,
  toggleAllVisibleGroups,
  groupBaselines,
  selectedGroupIds,
  toggleGroupSelected,
  globalPointValueLabel,
  setEditingGroupId,
  duplicateGroup,
  restoreGroup,
  setPendingDeleteGroupId,
}: Props) {
  return (
    <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
      <div className="panel-header">
        <div>
          <h3 className="panel-title">1. Grupos de Pontuação</h3>
          <p className="panel-subtitle">O grupo define pontos e R$/ponto padrão; o assunto pode sobrescrever quando necessário.</p>
        </div>
      </div>
      {/*
        O R$/ponto tem 3 níveis de sobrescrita (assunto > grupo > global, ver
        effective_rule_point_value em scoring_detail.py) mas em nenhum lugar da tela isso era
        dito explicitamente perto do campo - só dava pra descobrir lendo o placeholder
        ("Global R$X"/"Grupo R$X") linha por linha. Achado de revisão: clareza, não bug.
      */}
      <div className="mx-5 mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-slate-700">
        <span className="font-semibold text-slate-950">Prioridade do R$/ponto:</span> assunto &gt; grupo &gt; global. Deixe o campo em
        branco para herdar o valor do nível acima.
      </div>
      <FilterToolbar className="items-end">
        <div className="grid min-w-[260px] flex-1 gap-1">
          <Label>Novo grupo de pontuação</Label>
          <AppInput
            value={newGroupDraft.name}
            placeholder="Ex.: Manutenção Especial"
            onChange={(event) => setNewGroupDraft((current) => ({ ...current, name: event.target.value }))}
          />
        </div>
        <div className="grid w-full max-w-[180px] gap-1">
          <Label>Pontos padrão</Label>
          <AppInput
            type="number"
            value={numericInputValue(newGroupDraft.default_points)}
            onChange={(event) => setNewGroupDraft((current) => ({ ...current, default_points: parseNumericInput(event.target.value) }))}
          />
        </div>
        <Button type="button" onClick={() => void createGroup()} disabled={busy}>
          Criar grupo
        </Button>
        <ToolbarCount>{formatInteger(subjectsByGroup.length)} grupo(s) no recorte atual</ToolbarCount>
        {selectedVisibleGroups.length > 0 ? (
          <Button
            type="button"
            variant="outline"
            className="border-red-200 text-red-700 hover:bg-red-50"
            onClick={() => setDeleteGroupSelectionOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
            Excluir selecionados ({selectedVisibleGroups.length})
          </Button>
        ) : null}
      </FilterToolbar>
      <div className="grid gap-3 border-b bg-slate-50/60 px-5 py-4 md:grid-cols-3">
        <GuidanceCard title="Leitura rápida" description='A tabela mostra o essencial; use "Editar" para abrir o cadastro completo do grupo.' />
        <GuidanceCard title="Ações discretas" description="Duplicar e excluir ficam no menu; exclusão sempre confirma em modal." />
        <GuidanceCard title="Impacto visível" description="Assuntos, O.S e custo estimado ficam agrupados em badges suaves para leitura rápida." />
      </div>
      <DataTableFrame className="overflow-x-auto rounded-b-[24px] border-t-0">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
          <TableRow className="border-slate-700 hover:bg-slate-900">
            <TableHead className="w-10">
              <AppCheckbox checked={allVisibleGroupsSelected} onCheckedChange={toggleAllVisibleGroups} ariaLabel={allVisibleGroupsSelected ? "Desmarcar todos" : "Selecionar todos"} />
            </TableHead>
            <TableHead>Grupo</TableHead>
            <TableHead>Pontos do grupo</TableHead>
            <TableHead>R$/Ponto</TableHead>
            <TableHead>Assuntos vinculados</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {subjectsByGroup.map(({ group, rules, orders, impact }) => {
            const baseline = groupBaselines[group.id];
            const dirty = !sameGroupSnapshot(baseline, groupSnapshot(group));

            return (
              <TableRow key={group.id} className={cn("align-top transition-colors hover:bg-slate-50/70", dirty ? "bg-blue-50/40" : "bg-white")}>
                <TableCell className="py-4">
                  <AppCheckbox checked={selectedGroupIds.has(group.id)} onCheckedChange={(checked) => toggleGroupSelected(group.id, checked)} ariaLabel={`Selecionar ${group.name}`} />
                </TableCell>
                <TableCell className="min-w-72 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold text-slate-950">{group.name}</div>
                    {dirty ? <StatusBadge tone="blue">Alterações não salvas</StatusBadge> : null}
                  </div>
                </TableCell>
                <TableCell className="py-4 text-sm text-slate-700">{formatPoints(group.default_points)}</TableCell>
                <TableCell className="py-4 text-sm text-slate-700">
                  {group.point_value_override != null ? formatMoney(group.point_value_override) : `Global ${globalPointValueLabel}`}
                </TableCell>
                <TableCell className="min-w-72 py-4">
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge tone="emerald" className="border-emerald-200 bg-emerald-50 text-emerald-800">
                      {formatInteger(rules.length)} assuntos
                    </StatusBadge>
                    <StatusBadge tone="emerald" className="border-blue-200 bg-blue-50 text-uni-royal">
                      {formatInteger(orders)} O.S
                    </StatusBadge>
                    <StatusBadge tone="emerald" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                      {formatMoney(impact)}
                    </StatusBadge>
                  </div>
                </TableCell>
                <TableCell className="py-4">{group.active ? <StatusBadge tone="emerald">Ativo</StatusBadge> : <StatusBadge tone="slate">Inativo</StatusBadge>}</TableCell>
                <TableCell className="py-4">
                  <div className="flex items-center justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditingGroupId(group.id)}>
                      Editar
                    </Button>
                    <RowActionMenu
                      ariaLabel={`Ações do grupo ${group.name}`}
                      items={[
                        {
                          label: "Duplicar",
                          onSelect: () => void duplicateGroup(group),
                        },
                        ...(dirty
                          ? [
                              {
                                label: "Descartar alterações não salvas",
                                onSelect: () => restoreGroup(group.id),
                              },
                            ]
                          : []),
                        {
                          label: "Excluir",
                          onSelect: () => setPendingDeleteGroupId(group.id),
                          tone: "danger" as const,
                        },
                      ]}
                    />
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      </DataTableFrame>
    </section>
  );
}
