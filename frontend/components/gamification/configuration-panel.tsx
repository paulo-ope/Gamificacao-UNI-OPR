"use client";

import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { HealthRule, PenaltyRule, ScoringGroup, ScoringRule } from "@/lib/types";

type ConfigurationPanelProps = {
  pointValue: string;
  setPointValue: (value: string) => void;
  groups: ScoringGroup[];
  setGroups: (value: ScoringGroup[]) => void;
  scoringRules: ScoringRule[];
  setScoringRules: (value: ScoringRule[]) => void;
  penaltyRules: PenaltyRule[];
  setPenaltyRules: (value: PenaltyRule[]) => void;
  healthRules: HealthRule[];
  setHealthRules: (value: HealthRule[]) => void;
  onSavePointValue: () => Promise<void>;
  onSaveGroup: (group: ScoringGroup) => Promise<void>;
  onSaveScoringRule: (rule: ScoringRule) => Promise<void>;
  onSavePenaltyRule: (rule: PenaltyRule) => Promise<void>;
  onSaveHealthRule: (rule: HealthRule) => Promise<void>;
};

function replaceById<T extends { id: number }>(items: T[], id: number, patch: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

export function ConfigurationPanel({
  pointValue,
  setPointValue,
  groups,
  setGroups,
  scoringRules,
  setScoringRules,
  penaltyRules,
  setPenaltyRules,
  healthRules,
  setHealthRules,
  onSavePointValue,
  onSaveGroup,
  onSaveScoringRule,
  onSavePenaltyRule,
  onSaveHealthRule
}: ConfigurationPanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Configurações de cálculo</h2>
          <p className="panel-subtitle">Matriz de pontos, anulações, saúde operacional e valor do ponto.</p>
        </div>
        <div className="grid w-full gap-2 sm:w-72">
          <Label htmlFor="point-value">Valor do ponto</Label>
          <div className="flex gap-2">
            <Input
              id="point-value"
              type="number"
              min="0"
              step="0.01"
              value={pointValue}
              onChange={(event) => setPointValue(event.target.value)}
            />
            <Button variant="outline" size="icon" onClick={onSavePointValue} aria-label="Salvar valor do ponto">
              <Save className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="p-5">
        <Tabs defaultValue="groups">
          <TabsList className="flex h-auto flex-wrap justify-start">
            <TabsTrigger value="groups">Grupos</TabsTrigger>
            <TabsTrigger value="rules">Regras por assunto</TabsTrigger>
            <TabsTrigger value="penalties">Anulações</TabsTrigger>
            <TabsTrigger value="health">Saúde operacional</TabsTrigger>
          </TabsList>

          <TabsContent value="groups">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Grupo</TableHead>
                  <TableHead>Descrição</TableHead>
                  <TableHead>Pontos padrão</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead className="w-24">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {groups.map((group) => (
                  <TableRow key={group.id}>
                    <TableCell className="min-w-56 font-medium">{group.name}</TableCell>
                    <TableCell className="min-w-72 text-slate-600">{group.description}</TableCell>
                    <TableCell className="w-36">
                      <Input
                        type="number"
                        value={group.default_points}
                        onChange={(event) =>
                          setGroups(replaceById(groups, group.id, { default_points: Number(event.target.value) }))
                        }
                      />
                    </TableCell>
                    <TableCell className="w-24">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={group.active}
                        onChange={(event) => setGroups(replaceById(groups, group.id, { active: event.target.checked }))}
                      />
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => onSaveGroup(group)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          <TabsContent value="rules">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Grupo</TableHead>
                  <TableHead>Tipo da O.S</TableHead>
                  <TableHead>Assunto</TableHead>
                  <TableHead>Pontos</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead className="w-24">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {scoringRules.map((rule) => (
                  <TableRow key={rule.id}>
                    <TableCell className="min-w-56 text-slate-600">{rule.group?.name}</TableCell>
                    <TableCell className="min-w-44 font-medium">{rule.os_type}</TableCell>
                    <TableCell className="min-w-56">{rule.os_subject}</TableCell>
                    <TableCell className="w-32">
                      <Input
                        type="number"
                        value={rule.points}
                        onChange={(event) =>
                          setScoringRules(replaceById(scoringRules, rule.id, { points: Number(event.target.value) }))
                        }
                      />
                    </TableCell>
                    <TableCell className="w-24">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={rule.active}
                        onChange={(event) =>
                          setScoringRules(replaceById(scoringRules, rule.id, { active: event.target.checked }))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => onSaveScoringRule(rule)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          <TabsContent value="penalties">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Regra</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Modo</TableHead>
                  <TableHead>Pontos</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead className="w-24">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {penaltyRules.map((rule) => (
                  <TableRow key={rule.id}>
                    <TableCell className="min-w-64 font-medium">{rule.name}</TableCell>
                    <TableCell className="min-w-40">{rule.penalty_type}</TableCell>
                    <TableCell className="min-w-40 text-slate-600">{rule.calculation_mode}</TableCell>
                    <TableCell className="w-32">
                      <Input
                        type="number"
                        value={rule.points}
                        onChange={(event) =>
                          setPenaltyRules(replaceById(penaltyRules, rule.id, { points: Number(event.target.value) }))
                        }
                      />
                    </TableCell>
                    <TableCell className="w-24">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={rule.active}
                        onChange={(event) =>
                          setPenaltyRules(replaceById(penaltyRules, rule.id, { active: event.target.checked }))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => onSavePenaltyRule(rule)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          <TabsContent value="health">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nível</TableHead>
                  <TableHead>SLA mínimo %</TableHead>
                  <TableHead>Reincidência max. %</TableHead>
                  <TableHead>Multiplicador</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead className="w-24">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {healthRules.map((rule) => (
                  <TableRow key={rule.id}>
                    <TableCell className="min-w-44 font-medium">{rule.name}</TableCell>
                    <TableCell className="w-40">
                      <Input
                        type="number"
                        value={rule.min_sla}
                        onChange={(event) =>
                          setHealthRules(replaceById(healthRules, rule.id, { min_sla: Number(event.target.value) }))
                        }
                      />
                    </TableCell>
                    <TableCell className="w-44">
                      <Input
                        type="number"
                        value={rule.max_recurrence_rate}
                        onChange={(event) =>
                          setHealthRules(
                            replaceById(healthRules, rule.id, { max_recurrence_rate: Number(event.target.value) })
                          )
                        }
                      />
                    </TableCell>
                    <TableCell className="w-40">
                      <Input
                        type="number"
                        step="0.05"
                        value={rule.multiplier}
                        onChange={(event) =>
                          setHealthRules(replaceById(healthRules, rule.id, { multiplier: Number(event.target.value) }))
                        }
                      />
                    </TableCell>
                    <TableCell className="w-24">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-teal-700"
                        checked={rule.active}
                        onChange={(event) =>
                          setHealthRules(replaceById(healthRules, rule.id, { active: event.target.checked }))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => onSaveHealthRule(rule)}>
                        <Save className="h-4 w-4" />
                        Salvar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>
        </Tabs>
      </div>
    </section>
  );
}



