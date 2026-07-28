"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { OperationCollaboratorSla } from "@/lib/operations-api";
import { slaBadgeClass } from "@/lib/operations-sla";

function value(value: number | null, suffix = "") {
  if (value === null) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function minutes(valueInMinutes: number | null) {
  if (valueInMinutes === null) return "—";
  if (valueInMinutes < 60) return `${value(valueInMinutes)} min`;
  return `${value(valueInMinutes / 60)} h`;
}

export function OperationsCollaboratorSlaTable({
  data,
}: {
  data: OperationCollaboratorSla;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [expandedRegionals, setExpandedRegionals] = useState<Set<string>>(
    new Set(),
  );
  const [selectedResponsible, setSelectedResponsible] = useState<string | null>(
    null,
  );
  const [sort, setSort] = useState<{
    key: "responsible" | "completed" | "sla_rate" | "average_execution_minutes";
    direction: "asc" | "desc";
  }>({ key: "completed", direction: "desc" });
  const regionals = useMemo(() => {
    const grouped = new Map<string, typeof data.items>();
    for (const item of data.items) {
      const regional = item.regional || "Regional não identificada";
      grouped.set(regional, [...(grouped.get(regional) || []), item]);
    }
    return Array.from(grouped.entries())
      .map(([regional, items]) => ({
        regional,
        items: [...items].sort((a, b) => {
          const left = a[sort.key] ?? -1;
          const right = b[sort.key] ?? -1;
          const comparison =
            typeof left === "string"
              ? left.localeCompare(String(right), "pt-BR")
              : Number(left) - Number(right);
          return sort.direction === "asc" ? comparison : -comparison;
        }),
      }))
      .sort((a, b) => a.regional.localeCompare(b.regional, "pt-BR"));
  }, [data.items, sort]);

  useEffect(() => {
    setExpandedRegionals(new Set());
    setSelectedResponsible(null);
  }, [data]);
  useEffect(() => {
    function clearSelection(event: PointerEvent) {
      if (cardRef.current && !cardRef.current.contains(event.target as Node))
        setSelectedResponsible(null);
    }
    document.addEventListener("pointerdown", clearSelection);
    return () => document.removeEventListener("pointerdown", clearSelection);
  }, []);

  function changeSort(
    key: "responsible" | "completed" | "sla_rate" | "average_execution_minutes",
  ) {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  }

  function toggleRegional(regional: string) {
    setExpandedRegionals((current) => {
      const next = new Set(current);
      if (next.has(regional)) next.delete(regional);
      else next.add(regional);
      return next;
    });
  }

  const totalColumns = data.type_columns.length + 10;

  return (
    <Card
      ref={cardRef}
      className="mt-4 overflow-hidden rounded-2xl border-slate-200"
    >
      <CardHeader className="border-b bg-slate-950 px-4 py-3 text-white">
        <CardTitle className="text-sm font-semibold">
          Produtividade e SLA por colaborador
        </CardTitle>
        <p className="text-[11px] text-slate-300">
          Técnicos ficam agrupados por regional. Clique nos títulos para
          ordenar; Ctrl/Cmd + clique cria um recorte temporário. Tempos usam
          somente execução → finalização. Aderência agenda compara o horário
          agendado com o início real (tolerância de 60 min); só conta O.S. com
          agendamento registrado.
        </p>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <Table className="min-w-[1180px] text-xs">
          <TableHeader className="sticky top-0 z-10 bg-slate-100">
            <TableRow className="hover:bg-slate-100">
              <TableHead className="sticky left-0 z-20 min-w-56 bg-slate-100">
                <button type="button" onClick={() => changeSort("responsible")}>
                  Responsável / filial
                </button>
              </TableHead>
              {data.type_columns.map((column, index) => (
                <TableHead
                  key={`${column}-${index}`}
                  className="max-w-28 text-center text-[10px]"
                >
                  {column}
                </TableHead>
              ))}
              <TableHead className="text-center">
                <button type="button" onClick={() => changeSort("completed")}>
                  Realizadas
                </button>
              </TableHead>
              <TableHead className="text-center">
                <button type="button" onClick={() => changeSort("sla_rate")}>
                  SLA
                </button>
              </TableHead>
              <TableHead className="text-center">Dias</TableHead>
              <TableHead className="text-center">Média/dia</TableHead>
              <TableHead className="text-center">Aderência agenda</TableHead>
              <TableHead className="text-center">Exec. mensuráveis</TableHead>
              <TableHead className="text-right">
                <button
                  type="button"
                  onClick={() => changeSort("average_execution_minutes")}
                >
                  Execução média
                </button>
              </TableHead>
              <TableHead className="text-right">Execução mín.</TableHead>
              <TableHead className="text-right">Execução máx.</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {regionals.length ? (
              regionals.map(({ regional, items }) => {
                const expanded = expandedRegionals.has(regional);
                const totalCompleted = items.reduce(
                  (total, item) => total + item.completed,
                  0,
                );
                return (
                  <Fragment key={`group:${regional}`}>
                    <TableRow
                      key={`regional:${regional}`}
                      className="bg-slate-100 hover:bg-slate-100"
                    >
                      <TableCell colSpan={totalColumns} className="p-0">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-label={`${expanded ? "Recolher" : "Expandir"} técnicos da regional ${regional}`}
                          onClick={() => toggleRegional(regional)}
                          className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-slate-200/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600"
                        >
                          <span className="flex min-w-0 items-center gap-2">
                            <span className="rounded border border-slate-300 bg-white p-0.5 text-slate-600">
                              {expanded ? (
                                <ChevronDown className="h-4 w-4" />
                              ) : (
                                <ChevronRight className="h-4 w-4" />
                              )}
                            </span>
                            <span className="truncate text-xs font-bold uppercase text-slate-900">
                              {regional}
                            </span>
                          </span>
                          <span className="shrink-0 text-[10px] font-medium text-slate-500">
                            {items.length} técnico(s) · {totalCompleted} O.S.
                            realizadas
                          </span>
                        </button>
                      </TableCell>
                    </TableRow>
                    {expanded
                      ? items.map((item) => (
                          <TableRow
                            key={`${item.regional}-${item.responsible}`}
                            onClick={(event) => {
                              if (event.ctrlKey || event.metaKey) {
                                event.preventDefault();
                                setSelectedResponsible((current) =>
                                  current === item.responsible
                                    ? null
                                    : item.responsible,
                                );
                              }
                            }}
                            className={
                              selectedResponsible === item.responsible
                                ? "bg-blue-100 ring-1 ring-inset ring-blue-400"
                                : "odd:bg-white even:bg-slate-50/70"
                            }
                          >
                            <TableCell className="sticky left-0 z-10 bg-inherit py-2 pl-12">
                              <p
                                className="max-w-52 truncate font-semibold uppercase text-slate-900"
                                title={item.responsible}
                              >
                                {item.responsible}
                              </p>
                              <p
                                className="max-w-52 truncate text-[10px] uppercase text-slate-500"
                                title={item.regional}
                              >
                                {item.regional}
                              </p>
                            </TableCell>
                            {data.type_columns.map((column, index) => (
                              <TableCell
                                key={`${column}-${index}`}
                                className="text-center font-medium"
                              >
                                {item.type_counts[column] || "—"}
                              </TableCell>
                            ))}
                            <TableCell className="text-center font-bold text-slate-950">
                              {item.completed}
                            </TableCell>
                            <TableCell className="text-center">
                              <Badge className={slaBadgeClass(item.sla_rate)}>
                                {value(item.sla_rate, "%")}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-center">
                              {item.active_days}
                            </TableCell>
                            <TableCell className="text-center">
                              {value(item.daily_average)}
                            </TableCell>
                            <TableCell className="text-center">
                              {item.scheduled_orders ? (
                                <Badge className={slaBadgeClass(item.schedule_adherence_rate)}>
                                  {value(item.schedule_adherence_rate, "%")}
                                </Badge>
                              ) : (
                                <span className="text-slate-400">Sem agenda</span>
                              )}
                            </TableCell>
                            <TableCell className="text-center tabular-nums">
                              {item.measurable_execution_orders}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {minutes(item.average_execution_minutes)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {minutes(item.minimum_execution_minutes)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {minutes(item.maximum_execution_minutes)}
                            </TableCell>
                          </TableRow>
                        ))
                      : null}
                  </Fragment>
                );
              })
            ) : (
              <TableRow>
                <TableCell
                  colSpan={totalColumns}
                  className="py-12 text-center text-slate-500"
                >
                  Nenhuma O.S. finalizada para calcular a produtividade.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
