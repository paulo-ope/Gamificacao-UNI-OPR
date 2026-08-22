"use client";

import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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

const FIT_MIN_SCALE = 0.88;
const FIT_BOTTOM_MARGIN = 16;

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

const GAUGE_TONE_COLOR: Record<ReturnType<typeof slaTone>, string> = {
  success: "#10b981",
  warning: "#f59e0b",
  danger: "#ef4444",
  neutral: "#cbd5e1",
};

const GAUGE_RADIUS = 42;
const GAUGE_ARC_LENGTH = Math.PI * GAUGE_RADIUS;

function SlaGauge({
  label,
  rate,
  className,
}: {
  label: string;
  rate: number | null;
  className?: string;
}) {
  const color = GAUGE_TONE_COLOR[slaTone(rate)];
  const pct = rate === null ? 0 : Math.max(0, Math.min(100, rate));
  const offset = GAUGE_ARC_LENGTH * (1 - pct / 100);
  const angle = Math.PI * (1 - pct / 100);
  const markerX = 50 + GAUGE_RADIUS * Math.cos(angle);
  const markerY = 55 - GAUGE_RADIUS * Math.sin(angle);
  return (
    <div className={cn("flex flex-col items-center gap-1.5 px-2 py-3", className)}>
      <p
        className="line-clamp-2 h-9 w-full text-center text-sm font-semibold leading-tight text-slate-700"
        title={label}
      >
        {label}
      </p>
      <div className="relative h-20 w-40">
        <svg viewBox="0 0 100 60" className="h-full w-full overflow-visible">
          <path
            d="M 8 55 A 42 42 0 0 1 92 55"
            fill="none"
            stroke="#e2e8f0"
            strokeWidth="9"
            strokeLinecap="round"
          />
          <path
            d="M 8 55 A 42 42 0 0 1 92 55"
            fill="none"
            stroke={color}
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={GAUGE_ARC_LENGTH}
            strokeDashoffset={offset}
          />
          {pct > 0 ? (
            <circle
              cx={markerX}
              cy={markerY}
              r="5.5"
              fill="white"
              stroke={color}
              strokeWidth="3"
            />
          ) : null}
        </svg>
        <div className="absolute inset-x-0 bottom-0 text-center text-2xl font-bold text-slate-800">
          {number(rate, "%")}
        </div>
      </div>
    </div>
  );
}

function OperationsSlaGaugePanel({
  items,
}: {
  items: OperationSlaHierarchyItem[];
}) {
  const isOdd = items.length % 2 === 1;
  return (
    <div className="grid shrink-0 grid-cols-2 content-start gap-1 self-start rounded-2xl border border-slate-200 bg-slate-50 p-3 lg:w-96">
      {items.map((item, index) => (
        <SlaGauge
          key={item.label}
          label={item.label}
          rate={item.sla_rate}
          className={isOdd && index === items.length - 1 ? "col-span-2" : undefined}
        />
      ))}
    </div>
  );
}

function MetricCells({ item }: { item: OperationSlaHierarchyItem }) {
  return (
    <>
      <TableCell className="py-1.5 text-center font-semibold tabular-nums">
        {item.completed}
      </TableCell>
      <TableCell className="py-1.5 text-center">
        <SlaValue rate={item.sla_rate} />
      </TableCell>
      <TableCell
        className="py-1.5 text-center tabular-nums"
        title={`${item.timed_orders} O.S. com tempo mensurável`}
      >
        {number(item.up_to_12h_rate, "%")}
      </TableCell>
      <TableCell className="py-1.5 text-center tabular-nums">
        {number(item.from_12h_to_24h_rate, "%")}
      </TableCell>
      <TableCell className="py-1.5 text-center tabular-nums">
        {number(item.from_24h_to_48h_rate, "%")}
      </TableCell>
      <TableCell className="py-1.5 text-center tabular-nums">
        {number(item.from_48h_to_72h_rate, "%")}
      </TableCell>
      <TableCell className="py-1.5 text-center tabular-nums">
        {number(item.after_72h_rate, "%")}
      </TableCell>
      <TableCell className="py-1.5 text-right font-medium tabular-nums">
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
        "print:break-inside-avoid",
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
      <TableCell className="py-1.5">
        <div
          className="flex items-center gap-1.5"
          style={{ paddingLeft: `${level * 16}px` }}
        >
          {expandable ? (
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={expanded}
              aria-label={`${expanded ? "Recolher" : "Expandir"} ${levelLabel.toLocaleLowerCase("pt-BR")} ${item.label}`}
              className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-500 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
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
            <span className="h-4 w-4 shrink-0" />
          )}
          <p
            className={cn(
              "min-w-0 truncate",
              level === 0 || total
                ? "font-semibold text-slate-900"
                : "text-slate-700",
            )}
            title={item.label}
          >
            {item.label}
          </p>
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
  const fitContentRef = useRef<HTMLDivElement>(null);
  const fitMeasureRef = useRef<HTMLTableElement>(null);
  const [fitScale, setFitScale] = useState(1);
  const [fitHeight, setFitHeight] = useState<number | null>(null);
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

  function changeRootLevel(level: "os_type" | "subject" | "diagnosis") {
    setRootLevel(level);
  }

  useEffect(() => {
    setExpandedTypes(new Set());
    setExpandedSubjects(new Set());
    setSubjects({});
    setDiagnoses({});
    setError(null);
    setSelectedType(null);

    if (rootLevel === "os_type") {
      setRootData(data);
      return;
    }

    let active = true;
    setRootLoading(true);
    operationsApi
      .slaHierarchy(filters, rootLevel)
      .then((result) => {
        if (active) setRootData(result);
      })
      .catch((reason) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Não foi possível carregar o agrupamento selecionado.",
          );
        }
      })
      .finally(() => {
        if (active) setRootLoading(false);
      });

    return () => {
      active = false;
    };
  }, [data, filters, rootLevel]);

  useEffect(() => {
    function clearSelection(event: PointerEvent) {
      if (cardRef.current && !cardRef.current.contains(event.target as Node))
        setSelectedType(null);
    }
    document.addEventListener("pointerdown", clearSelection);
    return () => document.removeEventListener("pointerdown", clearSelection);
  }, []);

  useLayoutEffect(() => {
    const measureEl = fitMeasureRef.current;
    if (!measureEl) return;

    if (!presentationMode) {
      setFitScale(1);
      setFitHeight(null);
      return;
    }

    function getScrollParent(node: HTMLElement): HTMLElement | null {
      let parent = node.parentElement;
      while (parent) {
        const style = window.getComputedStyle(parent);
        if (
          /(auto|scroll)/.test(style.overflowY) &&
          parent.scrollHeight > parent.clientHeight
        ) {
          return parent;
        }
        parent = parent.parentElement;
      }
      return null;
    }

    function recompute() {
      if (!measureEl) return;
      const height = measureEl.offsetHeight;
      if (!height) return;
      const elRect = measureEl.getBoundingClientRect();
      const scrollParent = getScrollParent(measureEl);
      let top: number;
      let viewportHeight: number;
      if (scrollParent) {
        const parentRect = scrollParent.getBoundingClientRect();
        top = elRect.top - parentRect.top + scrollParent.scrollTop;
        viewportHeight = scrollParent.clientHeight;
      } else {
        top = elRect.top + window.scrollY;
        viewportHeight = window.innerHeight;
      }
      const available = viewportHeight - top - FIT_BOTTOM_MARGIN;
      const nextScale =
        available > 0
          ? Math.min(1, Math.max(FIT_MIN_SCALE, available / height))
          : FIT_MIN_SCALE;
      setFitHeight(height);
      setFitScale(nextScale);
    }

    recompute();
    const observer = new ResizeObserver(recompute);
    observer.observe(measureEl);
    window.addEventListener("resize", recompute);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", recompute);
    };
  }, [
    presentationMode,
    rootLevel,
    visibleItems,
    expandedTypes,
    expandedSubjects,
    subjects,
    diagnoses,
    isLoading,
    rootLoading,
  ]);

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
    <div className="flex flex-col gap-4 lg:flex-row">
      {!presentationMode ? (
        <OperationsSlaGaugePanel items={data.items} />
      ) : null}
      <Card
      ref={cardRef}
      className={cn(
        "flex min-w-0 flex-1 flex-col rounded-2xl border-slate-200 print:!static print:rounded-none print:border-0 print:shadow-none print:[print-color-adjust:exact] print:[-webkit-print-color-adjust:exact]",
        presentationMode
          ? "fixed inset-0 z-[70] overflow-auto rounded-none border-0 bg-slate-100 p-4 shadow-none lg:p-8 print:!inset-auto print:overflow-visible print:bg-white print:p-0"
          : "overflow-hidden print:overflow-visible",
      )}
    >
      <style>{`
        @page {
          size: landscape;
          margin: 10mm;
        }
      `}</style>
      <CardHeader className={cn("flex-row flex-wrap items-center justify-between gap-3 border-b bg-white print:border-none", presentationMode && "w-full rounded-t-xl")}>
        <div>
          <CardTitle className="text-base font-semibold text-slate-900">
            SLA por hierarquia
          </CardTitle>
          <p className="mt-1 text-xs text-slate-500">
            Expanda sob demanda. Clique nos títulos para ordenar; Ctrl/Cmd +
            clique em uma linha cria um recorte temporário.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 print:hidden">
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
                onSelect={() => changeRootLevel(level)}
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
      <CardContent
        className={cn(
          "flex-1 overflow-x-auto p-0 print:overflow-visible",
          presentationMode &&
            "w-full rounded-b-xl bg-white shadow-sm print:rounded-none print:shadow-none",
        )}
      >
        <div
          className="print:!h-auto"
          style={{ height: fitHeight !== null ? fitHeight * fitScale : undefined }}
        >
          <div
            ref={fitContentRef}
            className="print:!w-full print:!transform-none"
            style={{
              transform: fitScale < 1 ? `scale(${fitScale})` : undefined,
              transformOrigin: "top left",
              width: fitScale < 1 ? `${100 / fitScale}%` : "100%",
            }}
          >
            <table
              ref={fitMeasureRef}
              className="mx-auto w-[1055px] max-w-full table-fixed caption-bottom text-sm print:w-full print:text-[10.5pt] print:leading-snug"
            >
              <colgroup>
                <col style={{ width: 320 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 85 }} />
                <col style={{ width: 85 }} />
                <col style={{ width: 85 }} />
                <col style={{ width: 85 }} />
                <col style={{ width: 85 }} />
                <col style={{ width: 110 }} />
              </colgroup>
              <TableHeader className="sticky top-0 z-20 bg-slate-900 text-white shadow-sm print:static print:[print-color-adjust:exact] print:[-webkit-print-color-adjust:exact]">
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
          </div>
        </div>
      </CardContent>
      <div className="flex flex-wrap gap-3 border-t bg-slate-50 px-4 py-2 text-[10px] font-medium text-slate-600 print:break-inside-avoid print:text-[9pt]">
        <span className="text-emerald-700">Verde: SLA ≥ 80%</span>
        <span className="text-amber-700">Amarelo: 60% ≤ SLA &lt; 80%</span>
        <span className="text-red-700">Vermelho: SLA &lt; 60%</span>
      </div>
      </Card>
    </div>
  );
}
