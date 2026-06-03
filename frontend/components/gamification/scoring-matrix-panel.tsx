"use client";

import { ChevronDown, Save, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Command, CommandInput } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatInteger, formatMoney, formatPoints } from "@/lib/format";
import type { DiagnosisActionType, ImportedDiagnosis, ScoringGroup, ScoringSubjectRule } from "@/lib/types";

type Props = {
  groups: ScoringGroup[];
  subjectRules: ScoringSubjectRule[];
  importedDiagnoses: ImportedDiagnosis[];
  pointValue: string;
  setGroups: (groups: ScoringGroup[]) => void;
  setSubjectRules: (rules: ScoringSubjectRule[]) => void;
  onSaveGroup: (group: ScoringGroup) => Promise<void>;
  onCreateGroup: (payload: Partial<ScoringGroup>) => Promise<void>;
  onDeleteGroup: (group: ScoringGroup, replacementGroupId?: number | null) => Promise<void>;
  onSaveSubjectRule: (rule: ScoringSubjectRule) => Promise<void>;
  onDeleteSubjectRule: (rule: ScoringSubjectRule) => Promise<void>;
  onSaveDiagnosisRule: (
    diagnosisName: string,
    ruleId: number | null,
    payload: {
      action_type: DiagnosisActionType;
      penalty_points: number;
      force_points_value: number | null;
      active: boolean;
      description: string;
    }
  ) => Promise<void>;
};

type DiagnosisDraft = {
  action_type: DiagnosisActionType;
  penalty_points: number;
  force_points_value: number | null;
  active: boolean;
  description: string;
};

type GroupSort = "orders" | "impact" | "name" | "points";

function replaceById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

function actionLabel(action: DiagnosisActionType | null) {
  if (action === "subtract_points") return "Subtrair pontos";
  if (action === "cancel_points") return "Anular pontos";
  if (action === "requires_review") return "Revisão manual";
  if (action === "force_points") return "Forçar pontos";
  if (action === "no_penalty") return "Sem anulação";
  return "Sem regra";
}

export function ScoringMatrixPanel({
  groups,
  subjectRules,
  importedDiagnoses,
  pointValue,
  setGroups,
  setSubjectRules,
  onSaveGroup,
  onCreateGroup,
  onDeleteGroup,
  onSaveSubjectRule,
  onDeleteSubjectRule,
  onSaveDiagnosisRule
}: Props) {
  const [query, setQuery] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupPoints, setNewGroupPoints] = useState("");
  const [newGroupPointValue, setNewGroupPointValue] = useState("");
  const [diagnosisQuery, setDiagnosisQuery] = useState("");
  const [diagnosisDrafts, setDiagnosisDrafts] = useState<Record<string, DiagnosisDraft>>({});
  const [deleteTargets, setDeleteTargets] = useState<Record<number, string>>({});
  const [groupSort, setGroupSort] = useState<GroupSort>("orders");

  const groupedRules = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const filtered = subjectRules.filter((rule) => {
      const matchesQuery =
        !normalized ||
        [rule.group?.name, rule.os_type, rule.os_subject].some((value) => value?.toLowerCase().includes(normalized));
      const matchesActive = !activeOnly || rule.active;
      return matchesQuery && matchesActive;
    });

    const grouped = groups
      .map((group) => {
        const rules = filtered.filter((rule) => rule.group_id === group.id);
        return {
          group,
          rules,
          orders: rules.reduce((total, rule) => total + rule.orders_count, 0),
          financial: rules.reduce((total, rule) => total + rule.financial_impact, 0),
          points: rules.reduce((total, rule) => total + rule.effective_points * rule.orders_count, 0)
        };
      })
      .filter((item) => item.rules.length > 0 || !normalized);

    return grouped.sort((a, b) => {
      if (groupSort === "impact") return b.financial - a.financial;
      if (groupSort === "name") return a.group.name.localeCompare(b.group.name, "pt-BR");
      if (groupSort === "points") return b.points - a.points;
      return b.orders - a.orders;
    });
  }, [activeOnly, groupSort, groups, query, subjectRules]);

  const filteredDiagnoses = useMemo(() => {
    const normalized = diagnosisQuery.trim().toLowerCase();
    if (!normalized) return importedDiagnoses;
    return importedDiagnoses.filter((item) =>
      [item.diagnosis_name, item.predominant_regional, ...item.related_subjects].some((value) =>
        value.toLowerCase().includes(normalized)
      )
    );
  }, [diagnosisQuery, importedDiagnoses]);

  const subjectRuleCountByGroup = useMemo(
    () =>
      subjectRules.reduce<Record<number, number>>((counts, rule) => {
        counts[rule.group_id] = (counts[rule.group_id] ?? 0) + 1;
        return counts;
      }, {}),
    [subjectRules]
  );

  const matrixTotals = useMemo(
    () => ({
      activeRules: subjectRules.filter((rule) => rule.active).length,
      orders: subjectRules.reduce((total, rule) => total + rule.orders_count, 0),
      impact: subjectRules.reduce((total, rule) => total + rule.financial_impact, 0)
    }),
    [subjectRules]
  );
  const globalPointValueLabel = pointValue ? formatMoney(Number(pointValue.replace(",", "."))) : "backend";

  async function createGroup() {
    if (!newGroupName.trim()) return;
    await onCreateGroup({
      name: newGroupName.trim(),
      description: "Grupo criado pela matriz operacional.",
      default_points: Number(newGroupPoints || 0),
      point_value_override: newGroupPointValue === "" ? null : Number(newGroupPointValue),
      active: true
    });
    setNewGroupName("");
    setNewGroupPoints("");
    setNewGroupPointValue("");
  }

  function diagnosisDraft(item: ImportedDiagnosis): DiagnosisDraft {
    return (
      diagnosisDrafts[item.diagnosis_name] ?? {
        action_type: item.action_type ?? "no_penalty",
        penalty_points: item.penalty_points ?? 0,
        force_points_value: item.force_points_value ?? null,
        active: item.active ?? true,
        description: item.has_rule
          ? `Regra operacional para diagnóstico ${item.diagnosis_name}.`
          : `Criada a partir do diagnóstico importado ${item.diagnosis_name}.`
      }
    );
  }

  function updateDiagnosisDraft(item: ImportedDiagnosis, patch: Partial<DiagnosisDraft>) {
    setDiagnosisDrafts({
      ...diagnosisDrafts,
      [item.diagnosis_name]: {
        ...diagnosisDraft(item),
        ...patch
      }
    });
  }

  async function deleteGroup(group: ScoringGroup) {
    const linkedSubjects = subjectRuleCountByGroup[group.id] ?? 0;
    const replacementGroupId = deleteTargets[group.id] ? Number(deleteTargets[group.id]) : null;
    const replacementGroup = groups.find((item) => item.id === replacementGroupId) ?? null;
    const confirmation = replacementGroup
      ? `Excluir o grupo "${group.name}" e mover ${linkedSubjects} assunto(s) para "${replacementGroup.name}"?`
      : linkedSubjects > 0
        ? `Este grupo possui ${linkedSubjects} assunto(s). Deseja excluir o grupo e remover estes vínculos?`
        : `Excluir o grupo "${group.name}"?`;
    if (!window.confirm(confirmation)) return;
    await onDeleteGroup(group, replacementGroup?.id ?? null);
    setDeleteTargets((current) => {
      const next = { ...current };
      delete next[group.id];
      return next;
    });
  }

  async function deleteSubjectRule(rule: ScoringSubjectRule) {
    if (!window.confirm(`Remover o vínculo do assunto "${rule.os_subject}"?`)) return;
    await onDeleteSubjectRule(rule);
  }

  async function saveSubjectRule(rule: ScoringSubjectRule) {
    const latestRule = subjectRules.find((item) => item.id === rule.id) ?? rule;
    await onSaveSubjectRule(latestRule);
  }

  return (
    <section className="grid gap-4">
      <Tabs defaultValue="subjects">
        <TabsList className="flex h-auto flex-wrap justify-start">
          <TabsTrigger value="subjects">Matriz por assunto</TabsTrigger>
          <TabsTrigger value="diagnosis">Regras por Diagnóstico</TabsTrigger>
          <TabsTrigger value="groups">Grupos operacionais</TabsTrigger>
        </TabsList>

        <TabsContent value="subjects" className="grid gap-4">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">Matriz de pontuação por assunto</h2>
                <p className="panel-subtitle">O assunto define a pontuação base; o grupo define o padrão e o assunto pode sobrescrever.</p>
              </div>
              <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-96">
                <Label htmlFor="matrix-search">Buscar na matriz</Label>
                <Command className="border-0">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                    <CommandInput
                      id="matrix-search"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      className="pl-9"
                      placeholder="Grupo, tipo ou assunto"
                    />
                  </div>
                </Command>
              </div>
            </div>

            <div className="grid gap-4 border-b p-4 lg:grid-cols-[minmax(220px,1fr)_150px_150px_180px_auto_auto] lg:items-end lg:p-5">
              <div className="grid gap-2">
                <Label>Novo grupo</Label>
                <Input value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} placeholder="Ex.: Manutenção premium" />
              </div>
              <div className="grid gap-2">
                <Label>Pontos padrão</Label>
                <Input type="number" value={newGroupPoints} onChange={(event) => setNewGroupPoints(event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>R$/ponto</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={newGroupPointValue}
                  onChange={(event) => setNewGroupPointValue(event.target.value)}
                  placeholder={`Global ${globalPointValueLabel}`}
                />
              </div>
              <div className="grid gap-2">
                <Label>Ordem</Label>
                <select className="erp-control" value={groupSort} onChange={(event) => setGroupSort(event.target.value as GroupSort)}>
                  <option value="orders">Maior volume</option>
                  <option value="impact">Maior impacto</option>
                  <option value="points">Mais pontos</option>
                  <option value="name">Nome do grupo</option>
                </select>
              </div>
              <Button onClick={createGroup}>Criar grupo</Button>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" className="h-4 w-4 accent-teal-700" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} />
                Somente ativos
              </label>
            </div>

            <div className="grid gap-3 border-b bg-slate-50 px-5 py-3 text-sm sm:grid-cols-3">
              <div>
                <div className="text-xs font-medium uppercase text-slate-500">Vínculos ativos</div>
                <div className="font-semibold text-slate-950">{formatInteger(matrixTotals.activeRules)}</div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase text-slate-500">O.S cobertas</div>
                <div className="font-semibold text-slate-950">{formatInteger(matrixTotals.orders)}</div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase text-slate-500">Impacto configurado</div>
                <div className="font-semibold text-teal-700">{formatMoney(matrixTotals.impact)}</div>
              </div>
            </div>

            <Accordion className="p-4">
              {groupedRules.map(({ group, rules, orders, financial, points }, index) => (
                <AccordionItem key={group.id} value={String(group.id)} defaultOpen={index < 2}>
                  <AccordionTrigger asChild>
                    <button className="grid w-full gap-3 px-4 py-3 text-left md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center">
                      <div className="min-w-0">
                        <div className="text-xs font-medium uppercase text-slate-500">Grupo</div>
                        <div className="truncate text-base font-semibold text-slate-950">{group.name}</div>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5 md:text-right">
                        <div>
                          <div className="text-xs text-slate-500">Assuntos</div>
                          <div className="font-semibold">{formatInteger(rules.length)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-500">Qtd O.S</div>
                          <div className="font-semibold">{formatInteger(orders)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-500">Subtotal</div>
                          <div className="font-semibold">{formatPoints(points)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-500">R$/ponto</div>
                          <div className="font-semibold">
                            {group.point_value_override != null ? formatMoney(group.point_value_override) : `Global ${globalPointValueLabel}`}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-500">Impacto</div>
                          <div className="font-semibold text-teal-700">{formatMoney(financial)}</div>
                        </div>
                      </div>
                      <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
                    </button>
                  </AccordionTrigger>
                  <AccordionContent className="border-t">
                    <div className="table-frame">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Grupo</TableHead>
                          <TableHead>Assunto</TableHead>
                          <TableHead>Usa padrão</TableHead>
                          <TableHead>Pontos especificos</TableHead>
                          <TableHead>R$/ponto</TableHead>
                          <TableHead>Qtd O.S</TableHead>
                          <TableHead>Impacto estimado</TableHead>
                          <TableHead>Ativo</TableHead>
                          <TableHead>Ação</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {rules.map((rule) => {
                          const selectedGroup = groups.find((item) => item.id === rule.group_id) ?? null;
                          const pointValuePlaceholder =
                            selectedGroup?.point_value_override != null
                              ? `Grupo ${formatMoney(selectedGroup.point_value_override)}`
                              : `Global ${globalPointValueLabel}`;

                          return (
                          <TableRow key={rule.id}>
                            <TableCell className="min-w-60">
                              <select
                                className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                                value={rule.group_id}
                                onChange={(event) =>
                                  setSubjectRules(replaceById(subjectRules, rule.id, { group_id: Number(event.target.value) }))
                                }
                              >
                                {groups.map((item) => (
                                  <option key={item.id} value={item.id}>
                                    {item.name} ({formatPoints(item.default_points)})
                                  </option>
                                ))}
                              </select>
                            </TableCell>
                            <TableCell className="min-w-80">
                              <div className="font-medium text-slate-950">{rule.os_subject}</div>
                              <div className="text-xs text-slate-500">{rule.os_type}</div>
                            </TableCell>
                            <TableCell>
                              <input
                                type="checkbox"
                                className="h-4 w-4 accent-teal-700"
                                checked={rule.use_group_default}
                                onChange={(event) =>
                                  setSubjectRules(replaceById(subjectRules, rule.id, { use_group_default: event.target.checked }))
                                }
                              />
                            </TableCell>
                            <TableCell className="w-40">
                              <Input
                                type="number"
                                value={rule.custom_points ?? ""}
                                disabled={rule.use_group_default}
                                placeholder={formatPoints(rule.effective_points)}
                                onChange={(event) =>
                                  setSubjectRules(
                                    replaceById(subjectRules, rule.id, {
                                      custom_points: event.target.value === "" ? null : Number(event.target.value)
                                    })
                                  )
                                }
                              />
                            </TableCell>
                            <TableCell className="w-44">
                              <Input
                                type="number"
                                step="0.01"
                                value={rule.point_value_override ?? ""}
                                placeholder={pointValuePlaceholder}
                                onChange={(event) =>
                                  setSubjectRules(
                                    replaceById(subjectRules, rule.id, {
                                      point_value_override: event.target.value === "" ? null : Number(event.target.value)
                                    })
                                  )
                                }
                              />
                            </TableCell>
                            <TableCell>{formatInteger(rule.orders_count)}</TableCell>
                            <TableCell className="font-medium text-teal-700">{formatMoney(rule.financial_impact)}</TableCell>
                            <TableCell>
                              <input
                                type="checkbox"
                                className="h-4 w-4 accent-teal-700"
                                checked={rule.active}
                                onChange={(event) => setSubjectRules(replaceById(subjectRules, rule.id, { active: event.target.checked }))}
                              />
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-2">
                                <Button variant="outline" size="sm" onClick={() => void saveSubjectRule(rule)}>
                                  <Save className="h-4 w-4" />
                                  Salvar
                                </Button>
                                <Button variant="destructive" size="sm" onClick={() => void deleteSubjectRule(rule)}>
                                  <Trash2 className="h-4 w-4" />
                                  Remover
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </TabsContent>

        <TabsContent value="diagnosis">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">Regras por Diagnóstico</h2>
                <p className="panel-subtitle">O diagnóstico decide anulação, liberação, exceção ou revisão manual sem regra fixa no cálculo.</p>
              </div>
              <div className="flex w-full flex-col gap-2 sm:w-96">
                <Label htmlFor="diagnosis-search">Buscar diagnóstico</Label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <Input
                    id="diagnosis-search"
                    value={diagnosisQuery}
                    onChange={(event) => setDiagnosisQuery(event.target.value)}
                    className="pl-9"
                    placeholder="Diagnóstico, assunto ou regional"
                  />
                </div>
              </div>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Diagnóstico</TableHead>
                  <TableHead>Qtd O.S</TableHead>
                  <TableHead>Ação configurada</TableHead>
                  <TableHead>Pontos anulados</TableHead>
                  <TableHead>Impacto estimado</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead>Assuntos relacionados</TableHead>
                  <TableHead>Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredDiagnoses.map((item) => {
                  const draft = diagnosisDraft(item);
                  return (
                    <TableRow key={item.diagnosis_name}>
                      <TableCell className="min-w-56">
                        <div className="font-medium text-slate-950">{item.diagnosis_name}</div>
                        <div className="mt-1">
                          <Badge className={item.has_rule ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}>
                            {item.has_rule ? "Configurado" : "Sem regra"}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell>{formatInteger(item.service_orders_count)}</TableCell>
                      <TableCell className="min-w-52">
                        <select
                          className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                          value={draft.action_type}
                          onChange={(event) => updateDiagnosisDraft(item, { action_type: event.target.value as DiagnosisActionType })}
                        >
                          <option value="subtract_points">Subtrair pontos</option>
                          <option value="cancel_points">Anular pontos</option>
                          <option value="no_penalty">Sem anulação</option>
                          <option value="requires_review">Revisão manual</option>
                          <option value="force_points">Forçar pontos</option>
                        </select>
                        <div className="mt-1 text-xs text-slate-500">{actionLabel(item.action_type)}</div>
                      </TableCell>
                      <TableCell className="w-40">
                        <Input
                          type="number"
                          value={draft.action_type === "force_points" ? draft.force_points_value ?? "" : draft.penalty_points}
                          onChange={(event) =>
                            updateDiagnosisDraft(
                              item,
                              draft.action_type === "force_points"
                                ? { force_points_value: event.target.value === "" ? null : Number(event.target.value) }
                                : { penalty_points: Number(event.target.value) }
                            )
                          }
                        />
                      </TableCell>
                      <TableCell className="font-medium text-teal-700">{formatMoney(item.estimated_impact)}</TableCell>
                      <TableCell>
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-teal-700"
                          checked={draft.active}
                          onChange={(event) => updateDiagnosisDraft(item, { active: event.target.checked })}
                        />
                      </TableCell>
                      <TableCell className="min-w-80 text-xs text-slate-600">{item.related_subjects.join(" | ") || "-"}</TableCell>
                      <TableCell>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => onSaveDiagnosisRule(item.diagnosis_name, item.rule_id, draft)}
                        >
                          <Save className="h-4 w-4" />
                          Salvar
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="groups">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">Grupos operacionais</h2>
                <p className="panel-subtitle">Edite o comportamento padrão de cada grupo de remuneração.</p>
              </div>
            </div>
            <div className="table-frame">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Grupo</TableHead>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Pontos padrão</TableHead>
                    <TableHead>R$/ponto</TableHead>
                    <TableHead>Assuntos</TableHead>
                    <TableHead>Ativo</TableHead>
                    <TableHead>Ao arquivar o grupo</TableHead>
                    <TableHead>Ação</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {groups.map((group) => (
                    <TableRow key={group.id}>
                      <TableCell className="min-w-64">
                        <Input
                          value={group.name}
                          onChange={(event) => setGroups(replaceById(groups, group.id, { name: event.target.value }))}
                        />
                      </TableCell>
                      <TableCell className="min-w-80">
                        <Input
                          value={group.description ?? ""}
                          onChange={(event) => setGroups(replaceById(groups, group.id, { description: event.target.value }))}
                        />
                      </TableCell>
                      <TableCell className="w-40">
                        <Input
                          type="number"
                          value={group.default_points}
                          onChange={(event) => setGroups(replaceById(groups, group.id, { default_points: Number(event.target.value) }))}
                        />
                      </TableCell>
                      <TableCell className="w-44">
                        <Input
                          type="number"
                          step="0.01"
                          value={group.point_value_override ?? ""}
                          placeholder={`Global ${globalPointValueLabel}`}
                          onChange={(event) =>
                            setGroups(
                              replaceById(groups, group.id, {
                                point_value_override: event.target.value === "" ? null : Number(event.target.value)
                              })
                            )
                          }
                        />
                      </TableCell>
                      <TableCell>{formatInteger(subjectRuleCountByGroup[group.id] ?? 0)}</TableCell>
                      <TableCell>
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-teal-700"
                          checked={group.active}
                          onChange={(event) => setGroups(replaceById(groups, group.id, { active: event.target.checked }))}
                        />
                      </TableCell>
                      <TableCell className="min-w-72">
                        <select
                          className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm"
                          value={deleteTargets[group.id] ?? ""}
                          onChange={(event) =>
                            setDeleteTargets((current) => ({
                              ...current,
                              [group.id]: event.target.value
                            }))
                          }
                        >
                          <option value="">Remover vínculos e deixar assuntos sem regra</option>
                          {groups
                            .filter((item) => item.id !== group.id)
                            .map((item) => (
                              <option key={item.id} value={item.id}>
                                Mover assuntos para {item.name}
                              </option>
                            ))}
                        </select>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          <Button variant="outline" size="sm" onClick={() => onSaveGroup(group)}>
                            <Save className="h-4 w-4" />
                            Salvar
                          </Button>
                          <Button variant="destructive" size="sm" onClick={() => void deleteGroup(group)}>
                            <Trash2 className="h-4 w-4" />
                            Excluir
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </section>
  );
}



