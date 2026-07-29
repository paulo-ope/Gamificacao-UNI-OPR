"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleX,
  Loader2,
  Maximize2,
  Minimize2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppRadio } from "@/components/ui/radio";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  operationsApi,
  type OperationFilterState,
  type OperationSlaHierarchy,
  type OperationSlaHierarchyItem,
} from "@/lib/operations-api";
import { slaBadgeClass, slaTone } from "@/lib/operations-sla";
import { cn } from "@/lib/utils";

function number(value: number | null, suffix = "") {
  if (value === null) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function subjectKey(osType: string, subject: string) {
  return JSON.stringify([osType, subject]);
}

function SlaValue({ rate }: { rate: number | null }) {
  const tone = slaTone(rate);
  const Icon =
    tone === "success"
      ? CheckCircle2
      : tone === "warning"
        ? CircleAlert
        : tone === "danger"
          ? CircleX
          : CircleAlert;
  return (
    <Badge
      className={cn(
        "inline-flex min-w-16 items-center justify-center gap-1",
        slaBadgeClass(rate),
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {number(rate, "%")}
    </Badge>
  );
}

function MetricCells({ item }: { item: OperationSlaHierarchyItem }) {
  return (
    <>
      <TableCell className="text-center font-semibold tabular-nums">
        {item.completed}
      </TableCell>
      <TableCell className="text-center">
        <SlaValue rate={item.sla_rate} />
      </TableCell>
      <TableCell
        className="text-center tabular-nums"
        title={`${item.timed_orders} O.S. com tempo mensurável`}
      >
        {number(item.up_to_12h_rate, "%")}
      </TableCell>
      <TableCell className="text-center tabular-nums">
        {number(item.from_12h_to_24h_rate, "%")}
      </TableCell>
      <TableCell className="text-center tabular-nums">
        {number(item.from_24h_to_48h_rate, "%")}
      </TableCell>
      <TableCell className="text-center tabular-nums">
        {number(item.from_48h_to_72h_rate, "%")}
      </TableCell>
      <TableCell className="text-center tabular-nums">
        {number(item.after_72h_rate, "%")}
      </TableCell>
      <TableCell className="text-right font-medium tabular-nums">
        {number(item.average_closing_hours)}
      </TableCell>
    </>
  );
}

function HierarchyRow({
  item,
  level,
  expandable,
  expanded,
  loading,
  onToggle,
  total = false,
  selected = false,
  onQuickSelect,
}: {
  item: OperationSlaHierarchyItem;
  level: 0 | 1 | 2;
  expandable?: boolean;
  expanded?: boolean;
  loading?: boolean;
  onToggle?: () => void;
  total?: boolean;
  selected?: boolean;
  onQuickSelect?: (event: React.MouseEvent<HTMLTableRowElement>) => void;
}) {
  const levelLabel =
    level === 0 ? "Tipo geral" : level === 1 ? "Assunto" : "Diagnóstico";
  return (
    <TableRow
      onClick={onQuickSelect}
      className={cn(
        total
          ? "border-t-2 border-slate-400 bg-slate-200 font-bold hover:bg-slate-200"
          : level === 0
            ? "bg-slate-100/80 hover:bg-slate-100"
            : level === 1
              ? "bg-white hover:bg-blue-50/40"
              : "bg-slate-50/70 hover:bg-blue-50/40",
        selected && "bg-blue-100 ring-1 ring-inset ring-blue-400",
      )}
    >
      <TableCell className="min-w-72 py-2">
        <div
          className="flex items-center gap-1.5"
          style={{ paddingLeft: `${level * 22}px` }}
        >
          {expandable ? (
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={expanded}
              aria-label={`${expanded ? "Recolher" : "Expandir"} ${levelLabel.toLocaleLowerCase("pt-BR")} ${item.label}`}
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : expanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
            </button>
          ) : (
            <span className="h-6 w-6 shrink-0" />
          )}
          <div className="min-w-0">
            <p
              className={cn(
                "truncate",
                level === 0 || total
                  ? "font-semibold text-slate-900"
                  : "text-slate-700",
              )}
              title={item.label}
            >
              {item.label}
            </p>
            {!total ? (
              <p className="text-[9px] uppercase tracking-wide text-slate-400">
                {levelLabel}
              </p>
            ) : null}
          </div>
        </div>
      </TableCell>
      <MetricCells item={item} />
    </TableRow>
  );
}

export function OperationsSlaHierarchyTable({
  data,
  filters,
  isLoading,
}: {
  data: OperationSlaHierarchy;
  filters: OperationFilterState;
  isLoading: boolean;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [rootLevel, setRootLevel] = useState<"os_type" | "subject" | "diagnosis">("os_type");
  const [rootData, setRootData] = useState(data);
  const [rootLoading, setRootLoading] = useState(false);
  const [presentationMode, setPresentationMode] = useState(false);
  const showSubject = rootLevel === "os_type";
  const showDiagnosis = rootLevel === "os_type";
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [expandedSubjects, setExpandedSubjects] = useState<Set<string>>(
    new Set(),
  );
  const [subjects, setSubjects] = useState<
    Record<string, OperationSlaHierarchyItem[]>
  >({});
  const [diagnoses, setDiagnoses] = useState<
    Record<string, OperationSlaHierarchyItem[]>
  >({});
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [sort, setSort] = useState<{
    key: "label" | "completed" | "sla_rate";
    direction: "asc" | "desc";
  }>({ key: "completed", direction: "desc" });

  const visibleItems = useMemo(() => {
    return [...rootData.items].sort((left, right) => {
      const leftValue = left[sort.key] ?? -1;
      const rightValue = right[sort.key] ?? -1;
      const comparison =
        typeof leftValue === "string"
          ? leftValue.localeCompare(String(rightValue), "pt-BR")
          : Number(leftValue) - Number(rightValue);
      return sort.direction === "asc" ? comparison : -comparison;
    });
  }, [rootData.items, sort]);

  function changeSort(key: "label" | "completed" | "sla_rate") {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  }

  async function changeRootLevel(level: "os_type" | "subject" | "diagnosis") {
    setRootLevel(level);
    setExpandedTypes(new Set());
    setExpandedSubjects(new Set());
    setSubjects({});
    setDiagnoses({});
    setError(null);
    if (level === "os_type") {
      setRootData(data);
      return;
    }
    setRootLoading(true);
    try {
      setRootData(await operationsApi.slaHierarchy(filters, level));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível carregar o agrupamento selecionado.",
      );
    } finally {
      setRootLoading(false);
    }
  }

  useEffect(() => {
    if (rootLevel === "os_type") setRootData(data);
    setExpandedTypes(new Set());
    setExpandedSubjects(new Set());
    setSubjects({});
    setDiagnoses({});
    setError(null);
    setSelectedType(null);
  }, [data, filters, rootLevel]);

  useEffect(() => {
    function clearSelection(event: PointerEvent) {
      if (cardRef.current && !cardRef.current.contains(event.target as Node))
        setSelectedType(null);
    }
    document.addEventListener("pointerdown", clearSelection);
    return () => document.removeEventListener("pointerdown", clearSelection);
  }, []);

  function setKeyLoading(key: string, loading: boolean) {
    setLoadingKeys((current) => {
      const next = new Set(current);
      if (loading) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  async function toggleType(osType: string) {
    if (expandedTypes.has(osType)) {
      setExpandedTypes((current) => {
        const next = new Set(current);
        next.delete(osType);
        return next;
      });
      return;
    }
    setExpandedTypes((current) => new Set(current).add(osType));
    if (subjects[osType]) return;
    const loadingKey = `type:${osType}`;
    setKeyLoading(loadingKey, true);
    setError(null);
    try {
      const response = await operationsApi.slaHierarchy(
        filters,
        "subject",
        osType,
      );
      setSubjects((current) => ({ ...current, [osType]: response.items }));
    } catch (reason) {
      setExpandedTypes((current) => {
        const next = new Set(current);
        next.delete(osType);
        return next;
      });
      setError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível carregar os assuntos deste tipo geral.",
      );
    } finally {
      setKeyLoading(loadingKey, false);
    }
  }

  async function toggleSubject(osType: string, subject: string) {
    const key = subjectKey(osType, subject);
    if (expandedSubjects.has(key)) {
      setExpandedSubjects((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
      return;
    }
    setExpandedSubjects((current) => new Set(current).add(key));
    if (diagnoses[key]) return;
    const loadingKey = `subject:${key}`;
    setKeyLoading(loadingKey, true);
    setError(null);
    try {
      const response = await operationsApi.slaHierarchy(
        filters,
        "diagnosis",
        osType,
        subject,
      );
      setDiagnoses((current) => ({ ...current, [key]: response.items }));
    } catch (reason) {
      setExpandedSubjects((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
      setError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível carregar os diagnósticos deste assunto.",
      );
    } finally {
      setKeyLoading(loadingKey, false);
    }
  }

  return (
    <Card
      ref={cardRef}
      className={cn(
        "rounded-2xl border-slate-200",
        presentationMode
          ? "fixed inset-0 z-[70] overflow-auto rounded-none border-0 bg-slate-100 p-4 shadow-none lg:p-8"
          : "overflow-hidden",
      )}
    >
      <CardHeader className={cn("flex-row flex-wrap items-center justify-between gap-3 border-b bg-white", presentationMode && "mx-auto w-full max-w-[1080px] rounded-t-xl")}>
        <div>
          <CardTitle className="text-base font-semibold text-slate-900">
            SLA por hierarquia
          </CardTitle>
          <p className="mt-1 text-xs text-slate-500">
            Expanda sob demanda. Clique nos títulos para ordenar; Ctrl/Cmd +
            clique em uma linha cria um recorte temporário.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
        <fieldset className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
          <legend className="sr-only">Agrupamento da tabela SLA</legend>
          {([
            ["os_type", "Tipo geral"],
            ["subject", "Assunto"],
            ["diagnosis", "Diagnóstico"],
          ] as const).map(([level, label]) => (
            <label key={level} className="flex items-center gap-1.5 font-medium text-slate-700">
              <AppRadio
                checked={rootLevel === level}
                disabled={rootLoading}
                onSelect={() => void changeRootLevel(level)}
                ariaLabel={label}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <button
          type="button"
          onClick={() => setPresentationMode((current) => !current)}
          aria-pressed={presentationMode}
          title={presentationMode ? "Sair do modo foco" : "Modo foco"}
          aria-label={presentationMode ? "Sair do modo foco" : "Modo foco"}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        >
          {presentationMode ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
        </div>
      </CardHeader>
      {error ? (
        <div
          role="alert"
          className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      ) : null}
      <CardContent className={cn("p-0", presentationMode ? "mx-auto w-full max-w-[1080px] overflow-x-auto rounded-b-xl bg-white shadow-sm" : "max-h-[70vh] overflow-auto")}>
        <table className="w-full min-w-[1040px] caption-bottom text-xs">
          <TableHeader className="sticky top-0 z-20 bg-slate-900 text-white shadow-sm">
            <TableRow className="border-slate-700 hover:bg-slate-900">
              <TableHead className="text-slate-200">
                <button type="button" onClick={() => changeSort("label")}>
                  {rootLevel === "os_type"
                    ? "Tipo geral / Assunto / Diagnóstico"
                    : rootLevel === "subject"
                      ? "Assunto"
                      : "Diagnóstico"}
                </button>
              </TableHead>
              <TableHead className="text-center text-slate-200">
                <button type="button" onClick={() => changeSort("completed")}>
                  Realizadas
                </button>
              </TableHead>
              <TableHead className="text-center text-slate-200">
                <button type="button" onClick={() => changeSort("sla_rate")}>
                  SLA técnico
                </button>
              </TableHead>
              <TableHead className="text-center text-slate-200">
                Até 12h
              </TableHead>
              <TableHead className="text-center text-slate-200">
                12–24h
              </TableHead>
              <TableHead className="text-center text-slate-200">
                24–48h
              </TableHead>
              <TableHead className="text-center text-slate-200">
                48–72h
              </TableHead>
              <TableHead className="text-center text-slate-200">
                Após 72h
              </TableHead>
              <TableHead className="text-right text-slate-200">
                T.M. fech. (h)
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(isLoading || rootLoading) && !rootData.items.length ? (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className="py-14 text-center text-slate-500"
                >
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  <p className="mt-2">Calculando SLA...</p>
                </TableCell>
              </TableRow>
            ) : (
              rootLevel !== "os_type"
                ? visibleItems.map((item) => (
                    <HierarchyRow
                      key={item.label}
                      item={item}
                      level={rootLevel === "subject" ? 1 : 2}
                    />
                  ))
                : visibleItems.map((typeItem) => {
                const typeExpanded = expandedTypes.has(typeItem.label);
                return (
                  <Fragment key={typeItem.label}>
                    <HierarchyRow
                      item={typeItem}
                      level={0}
                      expandable={showSubject}
                      expanded={typeExpanded}
                      loading={loadingKeys.has(`type:${typeItem.label}`)}
                      onToggle={() => void toggleType(typeItem.label)}
                      selected={selectedType === typeItem.label}
                      onQuickSelect={(event) => {
                        if (event.ctrlKey || event.metaKey) {
                          event.preventDefault();
                          setSelectedType((current) =>
                            current === typeItem.label ? null : typeItem.label,
                          );
                        }
                      }}
                    />
                    {showSubject && typeExpanded
                      ? (subjects[typeItem.label] || []).map((subjectItem) => {
                          const key = subjectKey(
                            typeItem.label,
                            subjectItem.label,
                          );
                          const subjectExpanded = expandedSubjects.has(key);
                          return (
                            <Fragment key={key}>
                              <HierarchyRow
                                item={subjectItem}
                                level={1}
                                expandable={showDiagnosis}
                                expanded={subjectExpanded}
                                loading={loadingKeys.has(`subject:${key}`)}
                                onToggle={() =>
                                  void toggleSubject(
                                    typeItem.label,
                                    subjectItem.label,
                                  )
                                }
                              />
                              {showDiagnosis && subjectExpanded
                                ? (diagnoses[key] || []).map(
                                    (diagnosisItem) => (
                                      <HierarchyRow
                                        key={`${key}:${diagnosisItem.label}`}
                                        item={diagnosisItem}
                                        level={2}
                                      />
                                    ),
                                  )
                                : null}
                            </Fragment>
                          );
                        })
                      : null}
                  </Fragment>
                );
              })
            )}
            {!isLoading && !rootLoading && !rootData.items.length ? (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className="py-14 text-center text-slate-500"
                >
                  Nenhuma O.S. finalizada para o recorte selecionado.
                </TableCell>
              </TableRow>
            ) : null}
            {rootData.total.completed ? (
              <HierarchyRow item={rootData.total} level={0} total />
            ) : null}
          </TableBody>
        </table>
      </CardContent>
      <div className="flex flex-wrap gap-3 border-t bg-slate-50 px-4 py-2 text-[10px] font-medium text-slate-600">
        <span className="text-emerald-700">Verde: SLA ≥ 80%</span>
        <span className="text-amber-700">Amarelo: 60% ≤ SLA &lt; 80%</span>
        <span className="text-red-700">Vermelho: SLA &lt; 60%</span>
      </div>
    </Card>
  );
}
