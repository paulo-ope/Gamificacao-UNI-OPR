"use client";

import { Fragment, type Dispatch, type SetStateAction } from "react";
import { Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatInteger, formatMoney } from "@/lib/format";
import type { ScoringGroup, ScoringSubjectRule } from "@/lib/types";
import { subjectStatus, subjectStatusClass, subjectStatusLabel } from "@/components/gamification/logic-configuration-helpers";

export type TypeRow = {
  os_type: string;
  subjects: number;
  orders: number;
  impact: number;
  groups: Set<string>;
  inactive: number;
};

type Props = {
  typeRows: TypeRow[];
  subjectRules: ScoringSubjectRule[];
  groups: ScoringGroup[];
  typeDrafts: Record<string, string>;
  setTypeDrafts: Dispatch<SetStateAction<Record<string, string>>>;
  expandedTypes: Record<string, boolean>;
  setExpandedTypes: Dispatch<SetStateAction<Record<string, boolean>>>;
  periodRuleStats: (rule: ScoringSubjectRule) => { orders: number; impact: number };
  saveTypeGeneral: (currentType: string) => Promise<void>;
  busy: boolean;
};

export function CategoriesSection({
  typeRows,
  subjectRules,
  groups,
  typeDrafts,
  setTypeDrafts,
  expandedTypes,
  setExpandedTypes,
  periodRuleStats,
  saveTypeGeneral,
  busy
}: Props) {
  return (
    <section className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
      <div className="panel-header">
        <div>
          <h3 className="panel-title">Tipos gerais da planilha</h3>
          <p className="panel-subtitle">
            O tipo geral vem da planilha importada e classifica os assuntos por família operacional. Aqui você renomeia o tipo geral; grupo, pontos e status ficam centralizados em Assuntos.
          </p>
        </div>
      </div>
      <div className="grid gap-3 border-b bg-slate-50 p-5 md:grid-cols-3 xl:grid-cols-6">
        {typeRows.map((row) => (
          <div key={row.os_type} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
            <div className="text-sm font-semibold text-slate-950">{row.os_type}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge className="border-slate-200 bg-slate-50 text-slate-700">{formatInteger(row.subjects)} assunto(s)</Badge>
              <Badge className="border-blue-200 bg-blue-50 text-uni-royal">{formatInteger(row.orders)} O.S</Badge>
            </div>
          </div>
        ))}
      </div>
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
          <TableRow className="border-slate-700 hover:bg-slate-900">
            <TableHead>Tipo Geral</TableHead>
            <TableHead>Assuntos</TableHead>
            <TableHead>O.S impactadas</TableHead>
            <TableHead>Valor a ser pago</TableHead>
            <TableHead>Assuntos do Tipo Geral</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Ação</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {typeRows.map((row) => {
            const rowRules = subjectRules
              .filter((rule) => rule.os_type === row.os_type)
              .sort((a, b) => periodRuleStats(b).orders - periodRuleStats(a).orders || a.os_subject.localeCompare(b.os_subject, "pt-BR"));
            const expanded = Boolean(expandedTypes[row.os_type]);

            return (
            <Fragment key={row.os_type}>
            <TableRow>
              <TableCell className="min-w-72">
                <Input
                  value={typeDrafts[row.os_type] ?? row.os_type}
                  onChange={(event) =>
                    setTypeDrafts((current) => ({
                      ...current,
                      [row.os_type]: event.target.value
                    }))
                  }
                />
                <div className="mt-1 text-xs text-slate-500">Tipo atual: {row.os_type}</div>
              </TableCell>
              <TableCell>{formatInteger(row.subjects)}</TableCell>
              <TableCell>{formatInteger(row.orders)}</TableCell>
              <TableCell className="font-medium text-uni-royal">{formatMoney(row.impact)}</TableCell>
              <TableCell className="min-w-96">
                <div className="grid gap-2">
                  <div className="flex flex-wrap gap-2">
                    {rowRules.slice(0, 4).map((rule) => (
                      <Badge key={rule.id} className="max-w-64 truncate border-slate-200 bg-slate-50 text-slate-700">
                        {rule.os_subject}
                      </Badge>
                    ))}
                    {rowRules.length > 4 ? (
                      <Badge className="border-slate-200 bg-slate-50 text-slate-700">+{rowRules.length - 4}</Badge>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="w-fit text-xs font-semibold text-uni-royal hover:text-uni-midnight"
                    onClick={() =>
                      setExpandedTypes((current) => ({
                        ...current,
                        [row.os_type]: !current[row.os_type]
                      }))
                    }
                  >
                    {expanded ? "Ocultar lista de assuntos" : "Abrir lista de assuntos"}
                  </button>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-2">
                  <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Configurado</Badge>
                  {row.inactive ? <Badge className="border-slate-200 bg-slate-50 text-slate-700">{formatInteger(row.inactive)} inativo(s)</Badge> : null}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => void saveTypeGeneral(row.os_type)}
                    disabled={(typeDrafts[row.os_type] ?? row.os_type).trim() === row.os_type || busy}
                  >
                    <Save className="h-4 w-4" />
                    Aplicar tipo
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setExpandedTypes((current) => ({
                        ...current,
                        [row.os_type]: !current[row.os_type]
                      }))
                    }
                  >
                    {expanded ? "Ocultar assuntos" : "Ver assuntos"}
                  </Button>
                </div>
              </TableCell>
            </TableRow>
            {expanded ? (
              <TableRow>
                <TableCell colSpan={7} className="bg-slate-50 p-0">
                  <div className="grid gap-3 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-slate-950">Assuntos em {row.os_type}</div>
                        <div className="text-xs text-slate-500">Lista de conferência. Para alterar grupo, pontos ou status, use a seção Assuntos.</div>
                      </div>
                      <Badge className="border-slate-200 bg-white text-slate-700">{formatInteger(rowRules.length)} assunto(s)</Badge>
                    </div>

                    <div className="grid gap-2">
                      {rowRules.map((rule) => {
                        const selectedGroup = groups.find((group) => group.id === rule.group_id) ?? null;
                        const status = subjectStatus(rule, selectedGroup);
                        const stats = periodRuleStats(rule);

                        return (
                          <div key={rule.id} className="grid gap-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] xl:grid-cols-[minmax(260px,1.3fr)_minmax(220px,0.8fr)_150px_150px] xl:items-center">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-slate-950" title={rule.os_subject}>
                                {rule.os_subject}
                              </div>
                              <div className="text-xs text-slate-500">{formatInteger(stats.orders)} O.S impactadas</div>
                            </div>
                            <div className="min-w-0">
                              <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Grupo atual</div>
                              <div className="mt-1 truncate text-sm text-slate-700" title={selectedGroup?.name ?? "Sem grupo"}>
                                {selectedGroup?.name ?? "Sem grupo"}
                              </div>
                            </div>
                            <Badge className={subjectStatusClass(status)}>{subjectStatusLabel(status)}</Badge>
                            <div className="text-sm font-semibold text-uni-royal">{formatMoney(stats.impact)}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </TableCell>
              </TableRow>
            ) : null}
            </Fragment>
          );
          })}
        </TableBody>
      </Table>
    </section>
  );
}
