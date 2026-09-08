"use client";

import { CalendarClock, ListChecks } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { AppCheckbox } from "@/components/ui/checkbox";
import { InfoHint } from "@/components/gamification/info-hint";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  SchedulingDashboard,
  SchedulingFilterState,
  SchedulingRescheduleByOperatorItem,
  SchedulingRescheduleByTechnicianItem,
} from "@/lib/scheduling-api";

import { minutesLabel, number } from "./scheduling-format";

// Rankings por operador/técnico/filial/assunto - análise SECUNDÁRIA do cockpit (pedido do usuário
// 2026-08-31: "rankings ficam em tabs ou painéis recolhíveis", fora da primeira dobra que agora é
// o resumo de hoje + calendário mensal).
export function SchedulingRankingsPanel({
  dashboard,
  reschedulesByOperator,
  reschedulesByTechnician,
  filters,
  onOpenOperatorFirstSchedules,
  onOpenOperatorEvents,
  onOpenTechnicianEvents,
  onOpenFilialLate,
  onOpenAssuntoLate,
}: {
  dashboard: SchedulingDashboard | null;
  reschedulesByOperator: SchedulingRescheduleByOperatorItem[];
  reschedulesByTechnician: SchedulingRescheduleByTechnicianItem[];
  filters: SchedulingFilterState;
  onOpenOperatorFirstSchedules: (operatorId: number, operatorName: string) => void;
  onOpenOperatorEvents: (operatorId: number, operatorName: string) => void;
  onOpenTechnicianEvents: (technicianId: number, technicianName: string) => void;
  onOpenFilialLate: (filialId: string, filialLabel: string) => void;
  onOpenAssuntoLate: (assuntoId: string, assuntoLabel: string) => void;
}) {
  const [operatorsExpanded, setOperatorsExpanded] = useState(false);
  const [technicianRankingExpanded, setTechnicianRankingExpanded] = useState(false);
  const [operatorRankingExpanded, setOperatorRankingExpanded] = useState(false);
  const [teamOnly, setTeamOnly] = useState(false);

  const visibleOperators = teamOnly ? (dashboard?.operators || []).filter((operator) => operator.is_team_member) : dashboard?.operators || [];
  const visibleReschedulesByOperator = teamOnly ? reschedulesByOperator.filter((item) => item.is_team_member) : reschedulesByOperator;

  return (
    <Tabs defaultValue="operadores">
      <div className="mb-2 flex items-center justify-end gap-1.5 text-xs font-medium text-slate-500">
        <AppCheckbox checked={teamOnly} onCheckedChange={setTeamOnly} ariaLabel="Mostrar somente membros da equipe de agendamento" className="h-3.5 w-3.5" />
        <label className="cursor-pointer" onClick={() => setTeamOnly((current) => !current)}>Somente equipe</label>
      </div>
      <TabsList>
        <TabsTrigger value="operadores">Produtividade por operador</TabsTrigger>
        <TabsTrigger value="reagendamentos">Reagendamentos por pessoa</TabsTrigger>
        <TabsTrigger value="atraso">Atraso por filial/assunto</TabsTrigger>
      </TabsList>

      <TabsContent value="operadores">
        <p className="mb-2 text-xs text-slate-500">
          Meta diária ({dashboard?.settings.scheduling_daily_goal ?? "40"}) aplicada só a membros da equipe de agendamento.
          Modo: {filters.count_mode === "all_events" ? "cada ação conta" : "O.S. distintas"}.
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Operador</TableHead>
              <TableHead className="text-right">Ações</TableHead>
              <TableHead className="text-right">O.S. distintas</TableHead>
              <TableHead className="text-right">Por dia</TableHead>
              <TableHead className="w-44">Meta diária</TableHead>
              <TableHead className="text-right">1º agendamento</TableHead>
              <TableHead className="text-right">Tempo típico (útil)</TableHead>
              <TableHead className="text-center">Detalhar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleOperators.slice(0, operatorsExpanded ? undefined : 15).map((operator) => (
              <TableRow key={operator.ixc_operator_id} className="odd:bg-slate-50/60">
                <TableCell>
                  <span className="font-medium text-slate-800">{operator.operator_name}</span>
                  {operator.is_team_member ? <Badge className="ml-2 border-blue-200 bg-blue-50 text-blue-700">Equipe</Badge> : null}
                </TableCell>
                <TableCell className="text-right tabular-nums">{operator.total_events}</TableCell>
                <TableCell className="text-right tabular-nums">{operator.distinct_orders}</TableCell>
                <TableCell className="text-right tabular-nums">{number(operator.per_day)}</TableCell>
                <TableCell>
                  {operator.goal_percentage !== null ? (
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full ${operator.goal_percentage >= 100 ? "bg-emerald-500" : operator.goal_percentage >= 60 ? "bg-blue-500" : "bg-amber-500"}`}
                          style={{ width: `${Math.min(100, operator.goal_percentage)}%` }}
                        />
                      </div>
                      <span className="shrink-0 text-xs tabular-nums text-slate-500">{number(operator.goal_percentage, "%")}</span>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400">fora da equipe</span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">{operator.first_schedules}</TableCell>
                <TableCell className="text-right tabular-nums">{minutesLabel(operator.ttfa_business_median_minutes)}</TableCell>
                <TableCell>
                  <div className="flex items-center justify-center gap-1">
                    <button
                      type="button"
                      title="Ver O.S. que este operador agendou primeiro"
                      aria-label="Ver 1º agendamento"
                      onClick={() => onOpenOperatorFirstSchedules(operator.ixc_operator_id, operator.operator_name)}
                      className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition hover:bg-blue-50 hover:text-blue-700"
                    >
                      <CalendarClock className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      title="Ver todas as ações deste operador no período"
                      aria-label="Ver todas as ações"
                      onClick={() => onOpenOperatorEvents(operator.ixc_operator_id, operator.operator_name)}
                      className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition hover:bg-blue-50 hover:text-blue-700"
                    >
                      <ListChecks className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!visibleOperators.length ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-sm text-slate-500">
                  {teamOnly ? "Nenhum membro da equipe com ação no recorte." : "Nenhuma ação de agendamento no recorte."}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        {visibleOperators.length > 15 ? (
          <button
            type="button"
            onClick={() => setOperatorsExpanded((current) => !current)}
            className="w-full px-4 py-2 text-left text-xs font-medium text-blue-700 hover:bg-slate-50"
          >
            {operatorsExpanded ? "Mostrar menos" : `Mostrar todos os ${visibleOperators.length} operadores`}
          </button>
        ) : null}
        <p className="px-1 py-2 text-[11px] text-slate-400">
          Use os ícones em &quot;Detalhar&quot;: <CalendarClock className="mx-0.5 inline h-3 w-3 align-text-bottom" /> só as O.S. que o operador agendou primeiro,{" "}
          <ListChecks className="mx-0.5 inline h-3 w-3 align-text-bottom" /> todas as ações dele no período (agendamentos e reagendamentos).
        </p>
      </TabsContent>

      <TabsContent value="reagendamentos">
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <span className="mb-1 flex items-center gap-1.5">
              <h3 className="text-sm font-semibold text-slate-950">Por técnico</h3>
              <InfoHint
                ariaLabel="Ajuda sobre reagendamentos por técnico"
                side="bottom"
                title="Reagendamentos gerados pelo técnico"
                description="Quantos REAGENDAMENTOS (evento tipo 10) cada técnico de campo gerou pessoalmente no período - só conta quando ele mesmo é o técnico do evento, não qualquer O.S. dele reagendada por outra pessoa. Considera só colaboradores com modelo de equipe de campo cadastrado na Gestão (exclui backoffice/agendamento)."
              />
            </span>
            <p className="mb-2 text-xs text-slate-500">Conta cada reagendamento gerado pelo próprio técnico, não O.S. distintas · só técnicos de campo cadastrados.</p>
            {reschedulesByTechnician.length ? (
              <>
                <ul className="space-y-1.5">
                  {(technicianRankingExpanded ? reschedulesByTechnician : reschedulesByTechnician.slice(0, 8)).map((item) => (
                    <li key={item.technician_id ?? "sem-tecnico"}>
                      {item.technician_id !== null ? (
                        <button
                          type="button"
                          onClick={() => onOpenTechnicianEvents(item.technician_id as number, item.technician_name)}
                          className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm transition hover:border-blue-200 hover:bg-blue-50/60"
                          title="Ver os reagendamentos que esse técnico gerou pessoalmente no período"
                        >
                          <span className="min-w-0 truncate text-slate-700">{item.technician_name}</span>
                          <span className="shrink-0 text-xs font-semibold text-slate-700">{item.reschedule_events} reagendamento(s)</span>
                        </button>
                      ) : (
                        <div className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm">
                          <span className="min-w-0 truncate text-slate-500">{item.technician_name}</span>
                          <span className="shrink-0 text-xs font-semibold text-slate-500">{item.reschedule_events} reagendamento(s)</span>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                {reschedulesByTechnician.length > 8 ? (
                  <button
                    type="button"
                    onClick={() => setTechnicianRankingExpanded((current) => !current)}
                    className="mt-2 w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium text-blue-700 hover:bg-slate-50"
                  >
                    {technicianRankingExpanded ? "Mostrar menos" : `Mostrar todos os ${reschedulesByTechnician.length} técnicos`}
                  </button>
                ) : null}
              </>
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">Sem O.S. com técnico definido no recorte.</p>
            )}
          </div>
          <div>
            <span className="mb-1 flex items-center gap-1.5">
              <h3 className="text-sm font-semibold text-slate-950">Por operador</h3>
              <InfoHint
                ariaLabel="Ajuda sobre reagendamentos por operador"
                side="bottom"
                title="Ações de reagendamento"
                description="Quantas AÇÕES de reagendamento (nunca o 1º agendamento) cada operador do backoffice/agendamento registrou no período."
              />
            </span>
            <p className="mb-2 text-xs text-slate-500">
              Conta cada ação de reagendar, não O.S. distintas - uma mesma O.S. reagendada 2x pelo mesmo operador soma 2.
              {teamOnly ? " Somente equipe." : ""}
            </p>
            {visibleReschedulesByOperator.length ? (
              <>
                <ul className="space-y-1.5">
                  {(operatorRankingExpanded ? visibleReschedulesByOperator : visibleReschedulesByOperator.slice(0, 8)).map((item) => (
                    <li key={item.operator_id ?? "sem-operador"}>
                      {item.operator_id !== null ? (
                        <button
                          type="button"
                          onClick={() => onOpenOperatorEvents(item.operator_id as number, item.operator_name)}
                          className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm transition hover:border-blue-200 hover:bg-blue-50/60"
                          title="Ver todas as ações desse operador no período (agendamentos e reagendamentos)"
                        >
                          <span className="flex min-w-0 items-center gap-1.5">
                            <span className="truncate text-slate-700">{item.operator_name}</span>
                            {item.is_team_member ? (
                              <Badge className="shrink-0 border-blue-200 bg-blue-50 text-[10px] text-blue-700">Equipe</Badge>
                            ) : null}
                          </span>
                          <span className="shrink-0 text-xs font-semibold text-slate-700">{item.reschedule_events} reagendamento(s)</span>
                        </button>
                      ) : (
                        <div className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm">
                          <span className="truncate text-slate-500">{item.operator_name}</span>
                          <span className="shrink-0 text-xs font-semibold text-slate-500">{item.reschedule_events} reagendamento(s)</span>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                {visibleReschedulesByOperator.length > 8 ? (
                  <button
                    type="button"
                    onClick={() => setOperatorRankingExpanded((current) => !current)}
                    className="mt-2 w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium text-blue-700 hover:bg-slate-50"
                  >
                    {operatorRankingExpanded ? "Mostrar menos" : `Mostrar todos os ${visibleReschedulesByOperator.length} operadores`}
                  </button>
                ) : null}
              </>
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">
                {teamOnly ? "Nenhum reagendamento de membro da equipe no recorte." : "Nenhum reagendamento no recorte."}
              </p>
            )}
          </div>
        </div>
      </TabsContent>

      <TabsContent value="atraso">
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Filiais com mais atraso</h3>
            <p className="mb-2 text-xs text-slate-500">SLA de agendamento por filial · mínimo de 5 O.S. agendadas no período.</p>
            {(dashboard?.filial_ranking || []).length ? (
              <ul className="space-y-1.5">
                {(dashboard?.filial_ranking || []).map((item) => (
                  <li key={item.key}>
                    <button
                      type="button"
                      onClick={() => onOpenFilialLate(item.key, item.label)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm transition hover:border-blue-200 hover:bg-blue-50/60"
                    >
                      <span className="min-w-0 truncate text-slate-700">{item.label}</span>
                      <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
                        <span>{item.scheduled} O.S.</span>
                        <span className={`font-semibold ${item.late_rate >= 50 ? "text-red-600" : "text-slate-700"}`}>{item.late_rate}% atraso</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">Sem volume suficiente no recorte.</p>
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Assuntos com mais atraso</h3>
            <p className="mb-2 text-xs text-slate-500">SLA de agendamento por assunto · mínimo de 5 O.S. agendadas no período.</p>
            {(dashboard?.assunto_ranking || []).length ? (
              <ul className="space-y-1.5">
                {(dashboard?.assunto_ranking || []).map((item) => (
                  <li key={item.key}>
                    <button
                      type="button"
                      onClick={() => onOpenAssuntoLate(item.key, item.label)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left text-sm transition hover:border-blue-200 hover:bg-blue-50/60"
                    >
                      <span className="min-w-0 truncate text-slate-700">{item.label}</span>
                      <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
                        <span>{item.scheduled} O.S.</span>
                        <span className={`font-semibold ${item.late_rate >= 50 ? "text-red-600" : "text-slate-700"}`}>{item.late_rate}% atraso</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">Sem volume suficiente no recorte.</p>
            )}
          </div>
        </div>
      </TabsContent>
    </Tabs>
  );
}
