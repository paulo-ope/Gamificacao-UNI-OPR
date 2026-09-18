"use client";

import { Trash2 } from "lucide-react";

import {
  AppCombobox,
  DataTableFrame,
  FilterToolbar,
  GuidanceCard,
  RowActionMenu,
  ToolbarCount,
} from "@/components/gamification/config-ui";
import { subjectStatus, subjectStatusClass, subjectStatusLabel } from "@/components/gamification/logic-configuration-helpers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatInteger, formatMoney, formatPoints } from "@/lib/format";
import type { ScoringGroup, ScoringSubjectRule } from "@/lib/types";
import type { SubjectFilter } from "@/components/gamification/logic-configuration-helpers";

type Props = {
  subjectFilter: SubjectFilter;
  setSubjectFilter: (value: SubjectFilter) => void;
  subjectGroupFilter: string;
  setSubjectGroupFilter: (value: string) => void;
  activeGroups: ScoringGroup[];
  filteredSubjectRules: ScoringSubjectRule[];
  selectedVisibleSubjectRules: ScoringSubjectRule[];
  setDeleteSubjectSelectionOpen: (open: boolean) => void;
  allVisibleSubjectsSelected: boolean;
  toggleAllVisibleSubjects: (checked: boolean) => void;
  visibleSubjectRules: ScoringSubjectRule[];
  groups: ScoringGroup[];
  periodRuleStats: (rule: ScoringSubjectRule) => { orders: number; impact: number };
  selectedSubjectIds: Set<number>;
  toggleSubjectSelected: (id: number, checked: boolean) => void;
  globalPointValueLabel: string;
  setEditingSubjectId: (id: number | null) => void;
  setPendingDeleteSubjectRuleId: (id: number | null) => void;
  visibleSubjectRulesCount: number;
  setVisibleSubjectRulesCount: (updater: (count: number) => number) => void;
};

export function SubjectsSection({
  subjectFilter,
  setSubjectFilter,
  subjectGroupFilter,
  setSubjectGroupFilter,
  activeGroups,
  filteredSubjectRules,
  selectedVisibleSubjectRules,
  setDeleteSubjectSelectionOpen,
  allVisibleSubjectsSelected,
  toggleAllVisibleSubjects,
  visibleSubjectRules,
  groups,
  periodRuleStats,
  selectedSubjectIds,
  toggleSubjectSelected,
  globalPointValueLabel,
  setEditingSubjectId,
  setPendingDeleteSubjectRuleId,
  visibleSubjectRulesCount,
  setVisibleSubjectRulesCount,
}: Props) {
  return (
    <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
      <div className="panel-header">
        <div>
          <h3 className="panel-title">2. Assuntos</h3>
          <p className="panel-subtitle">Vínculo permanente de assunto para grupo, com pontos e valor por ponto específicos quando precisar.</p>
        </div>
      </div>
      <div className="mx-5 mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-slate-700">
        <span className="font-semibold text-slate-950">Prioridade do R$/ponto:</span> assunto &gt; grupo &gt; global. Deixe o campo em
        branco para herdar o valor do nível acima.
      </div>
      <div className="grid gap-3 border-b bg-slate-50/60 px-5 py-4 md:grid-cols-2">
        <GuidanceCard title="Leitura rápida" description='A tabela mostra o essencial; use "Editar" para abrir o cadastro completo do assunto.' />
        <GuidanceCard title="Ação em lote" description="Marque as linhas na coluna à esquerda para remover vários assuntos de uma vez." />
      </div>
      <FilterToolbar>
        {[
          ["all", "Todos"],
          ["scored", "Pontuam"],
          ["not_scored", "Não pontuam"],
          ["without_group", "Sem grupo"]
        ].map(([value, label]) => (
          <Button
            key={value}
            type="button"
            variant={subjectFilter === value ? "default" : "outline"}
            size="sm"
            onClick={() => setSubjectFilter(value as SubjectFilter)}
          >
            {label}
          </Button>
        ))}
        <div className="flex min-w-72 items-center gap-2">
          <Label htmlFor="subject-group-filter" className="sr-only">
            Filtrar por grupo
          </Label>
          <AppCombobox
            value={subjectGroupFilter}
            onChange={setSubjectGroupFilter}
            placeholder="Todos os grupos"
            ariaLabel="Filtrar assuntos por grupo"
            options={[
              { value: "all", label: "Todos os grupos", description: "Exibe qualquer grupo vinculado." },
              ...activeGroups.map((group) => ({
                value: String(group.id),
                label: group.name,
                description: `${formatPoints(group.default_points)} por grupo`,
              })),
            ]}
          />
          {subjectGroupFilter !== "all" ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setSubjectGroupFilter("all")}>
              Limpar grupo
            </Button>
          ) : null}
        </div>
        <ToolbarCount>{formatInteger(filteredSubjectRules.length)} assunto(s) no filtro</ToolbarCount>
        {selectedVisibleSubjectRules.length > 0 ? (
          <Button
            type="button"
            variant="outline"
            className="border-red-200 text-red-700 hover:bg-red-50"
            onClick={() => setDeleteSubjectSelectionOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
            Remover selecionados ({selectedVisibleSubjectRules.length})
          </Button>
        ) : null}
      </FilterToolbar>
      <DataTableFrame>
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
          <TableRow className="border-slate-700 hover:bg-slate-900">
            <TableHead className="w-10">
              <AppCheckbox checked={allVisibleSubjectsSelected} onCheckedChange={toggleAllVisibleSubjects} ariaLabel={allVisibleSubjectsSelected ? "Desmarcar todos" : "Selecionar todos"} />
            </TableHead>
            <TableHead>Assunto</TableHead>
            <TableHead>Grupo vinculado</TableHead>
            <TableHead>Pontos</TableHead>
            <TableHead>R$/ponto</TableHead>
            <TableHead>O.S impactadas</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleSubjectRules.map((rule) => {
            const selectedGroup = groups.find((group) => group.id === rule.group_id) ?? null;
            const stats = periodRuleStats(rule);
            const status = subjectStatus(rule, selectedGroup);

            return (
            <TableRow key={rule.id}>
              <TableCell>
                <AppCheckbox checked={selectedSubjectIds.has(rule.id)} onCheckedChange={(checked) => toggleSubjectSelected(rule.id, checked)} ariaLabel="Selecionar assunto" />
              </TableCell>
              <TableCell className="min-w-72">
                <div className="font-medium text-slate-950">{rule.os_subject}</div>
                <div className="text-xs text-slate-500">Tipo Geral: {rule.os_type}</div>
              </TableCell>
              <TableCell className="min-w-48 text-sm text-slate-700">
                {selectedGroup ? selectedGroup.name : <Badge className="border-amber-200 bg-amber-50 text-amber-800">Sem grupo</Badge>}
              </TableCell>
              <TableCell className="text-sm text-slate-700">{formatPoints(rule.effective_points)}</TableCell>
              <TableCell className="text-sm text-slate-700">
                {rule.point_value_override != null
                  ? formatMoney(rule.point_value_override)
                  : selectedGroup?.point_value_override != null
                    ? `Grupo ${formatMoney(selectedGroup.point_value_override)}`
                    : `Global ${globalPointValueLabel}`}
              </TableCell>
              <TableCell>
                <div className="font-medium">{formatInteger(stats.orders)}</div>
                <div className="text-xs font-medium text-uni-royal">{formatMoney(stats.impact)}</div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-2">
                  <Badge className={subjectStatusClass(status)}>{subjectStatusLabel(status)}</Badge>
                  <Badge className={rule.active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-700"}>
                    {rule.active ? "Ativo" : "Inativo"}
                  </Badge>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex items-center justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setEditingSubjectId(rule.id)}>
                    Editar
                  </Button>
                  <RowActionMenu
                    ariaLabel={`Ações do assunto ${rule.os_subject}`}
                    items={[{ label: "Remover", onSelect: () => setPendingDeleteSubjectRuleId(rule.id), tone: "danger" }]}
                  />
                </div>
              </TableCell>
            </TableRow>
            );
          })}
          {visibleSubjectRules.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8} className="py-6 text-center text-sm text-slate-500">
                Nenhum assunto encontrado para os filtros atuais.
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
      </DataTableFrame>
      {filteredSubjectRules.length > visibleSubjectRulesCount ? (
        <div className="flex items-center justify-center border-t border-slate-200 py-3">
          <Button type="button" variant="outline" size="sm" onClick={() => setVisibleSubjectRulesCount((count) => count + 80)}>
            Mostrar mais ({visibleSubjectRulesCount} de {formatInteger(filteredSubjectRules.length)})
          </Button>
        </div>
      ) : null}
    </section>
  );
}
