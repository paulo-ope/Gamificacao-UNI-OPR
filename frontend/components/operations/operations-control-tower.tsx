"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, ChevronDown, ChevronRight, ExternalLink, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  operationsApi,
  type OperationControlTower,
  type OperationControlTowerItem,
  type OperationControlTowerLevel,
  type OperationControlTowerPath,
  type OperationControlTowerStatus,
  type OperationFilterState
} from "@/lib/operations-api";
import { cn } from "@/lib/utils";

const STATUS: Record<OperationControlTowerStatus, { label: string; icon: typeof Activity; className: string; panel: string }> = {
  critical: { label: "Crítico", icon: ShieldAlert, className: "border-red-200 bg-red-50 text-red-700", panel: "border-red-200 bg-red-50/70" },
  attention: { label: "Atenção", icon: AlertTriangle, className: "border-amber-200 bg-amber-50 text-amber-700", panel: "border-amber-200 bg-amber-50/70" },
  normal: { label: "Normal", icon: Activity, className: "border-emerald-200 bg-emerald-50 text-emerald-700", panel: "border-emerald-200 bg-emerald-50/70" },
  insufficient: { label: "Histórico insuficiente", icon: Activity, className: "border-slate-200 bg-slate-50 text-slate-600", panel: "border-slate-200 bg-slate-50" }
};

const LEVEL_LABEL: Record<OperationControlTowerLevel, string> = {
  subject: "Assunto",
  regional: "Regional",
  city: "Cidade",
  sector: "Setor",
  responsible: "Responsável"
};

const NEXT_LEVEL: Record<OperationControlTowerLevel, OperationControlTowerLevel | null> = {
  subject: "regional",
  regional: "city",
  city: "sector",
  sector: "responsible",
  responsible: null
};

function number(value: number | null, digits = 1) {
  if (value === null) return "—";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

function signed(value: number) {
  return `${value > 0 ? "+" : ""}${number(value, 0)}`;
}

function hours(value: number | null) {
  if (value === null) return "—";
  if (value < 24) return `${number(value)}h`;
  return `${number(value / 24)}d`;
}

function operationalReading(data: OperationControlTower) {
  const deviation = data.summary.deviation_percentage;
  const backlogDirection = data.summary.net_flow > 0 ? "cresceu" : data.summary.net_flow < 0 ? "reduziu" : "ficou estável";
  if (data.summary.status === "critical") return {
    title: "A operação exige ação imediata",
    description: `As entradas estão ${deviation === null ? "fora do padrão" : `${number(Math.abs(deviation))}% ${deviation >= 0 ? "acima" : "abaixo"} do esperado`} e o backlog ${backlogDirection} em ${Math.abs(data.summary.net_flow)} O.S. no período.`,
    action: "Abra “Onde agir” e priorize os assuntos críticos com backlog vencido."
  };
  if (data.summary.status === "attention") return {
    title: "Há sinais de aumento que merecem acompanhamento",
    description: `O volume recente está ${deviation === null ? "oscilando" : `${number(Math.abs(deviation))}% ${deviation >= 0 ? "acima" : "abaixo"} do esperado`} e o backlog ${backlogDirection} em ${Math.abs(data.summary.net_flow)} O.S.`,
    action: "Confira os assuntos em atenção e valide se o aumento continua nos próximos dias."
  };
  if (data.summary.status === "normal") return {
    title: "A demanda está dentro do comportamento esperado",
    description: `Aberturas e capacidade estão equilibradas; o backlog ${backlogDirection} em ${Math.abs(data.summary.net_flow)} O.S. no período.`,
    action: "Nenhuma intervenção geral é necessária. Acompanhe exceções específicas em “Onde agir”."
  };
  return {
    title: "Ainda não há histórico suficiente para uma conclusão",
    description: "O monitor precisa de mais dias comparáveis para separar variação normal de um aumento real.",
    action: "Use o volume atual como referência e volte a consultar após novas cargas diárias."
  };
}

function pathKey(path: OperationControlTowerPath) {
  return ["subject", "regional", "city", "sector", "responsible"]
    .map((level) => `${level}:${path[level as OperationControlTowerLevel] || ""}`)
    .join("|");
}

function StatusBadge({ status, persistentDays }: { status: OperationControlTowerStatus; persistentDays: number }) {
  const config = STATUS[status];
  const Icon = config.icon;
  return <Badge className={cn("w-fit whitespace-nowrap gap-1", config.className)}><Icon className="h-3 w-3" />{config.label}{persistentDays > 0 ? ` · ${persistentDays}d` : ""}</Badge>;
}

function SummaryMetric({ label, value, helper, accent }: { label: string; value: string; helper: string; accent?: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm"><p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p><p className={cn("mt-1 text-xl font-semibold tabular-nums text-slate-950", accent)}>{value}</p><p className="mt-1 text-[10px] leading-4 text-slate-500">{helper}</p></div>;
}

export function OperationsControlTower({
  data,
  filters,
  isLoading,
  onOpenOrders
}: {
  data: OperationControlTower;
  filters: OperationFilterState;
  isLoading: boolean;
  onOpenOrders: (path: OperationControlTowerPath) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [children, setChildren] = useState<Record<string, OperationControlTower>>({});
  const [loadingNodes, setLoadingNodes] = useState<Set<string>>(new Set());
  const [nodeError, setNodeError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const reading = useMemo(() => operationalReading(data), [data]);

  useEffect(() => {
    setExpanded(new Set());
    setChildren({});
    setLoadingNodes(new Set());
    setNodeError(null);
  }, [data.reference_date, data.path, filters]);

  async function toggle(item: OperationControlTowerItem) {
    const key = pathKey(item.path);
    if (expanded.has(key)) {
      setExpanded((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
      return;
    }
    setExpanded((current) => new Set(current).add(key));
    const nextLevel = NEXT_LEVEL[item.level];
    if (!nextLevel || children[key]) return;
    setLoadingNodes((current) => new Set(current).add(key));
    setNodeError(null);
    try {
      const response = await operationsApi.controlTower(filters, nextLevel, item.path);
      setChildren((current) => ({ ...current, [key]: response }));
    } catch (reason) {
      setExpanded((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
      setNodeError(reason instanceof Error ? reason.message : "Falha ao expandir o recorte operacional.");
    } finally {
      setLoadingNodes((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
    }
  }

  function rows(items: OperationControlTowerItem[], depth = 0): React.ReactNode[] {
    return items.flatMap((item) => {
      const key = pathKey(item.path);
      const isExpanded = expanded.has(key);
      const isNodeLoading = loadingNodes.has(key);
      const nested = children[key]?.items || [];
      const row = <TableRow key={key} className={cn("border-slate-100", item.status === "critical" && "bg-red-50/30", item.status === "attention" && "bg-amber-50/20")}>
        <TableCell className="sticky left-0 z-10 min-w-60 bg-inherit py-2.5">
          <div className="flex items-start gap-1.5" style={{ paddingLeft: `${depth * 14}px` }}>
            {item.has_children ? <button type="button" aria-label={`${isExpanded ? "Recolher" : "Expandir"} ${item.label}`} className="mt-0.5 rounded p-0.5 text-slate-500 hover:bg-slate-200" onClick={() => void toggle(item)}>{isNodeLoading ? <Activity className="h-4 w-4 animate-pulse" /> : isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button> : <span className="w-5" />}
            <div className="min-w-0"><p className="break-words text-xs font-semibold text-slate-900">{item.label}</p><p className="text-[9px] uppercase tracking-wide text-slate-400">{LEVEL_LABEL[item.level]}</p></div>
          </div>
        </TableCell>
        <TableCell>
          <StatusBadge status={item.status} persistentDays={item.persistent_days} />
          {item.reasons.length ? (
            <ul className="mt-1 max-w-48 space-y-0.5 text-[9px] leading-tight text-slate-500">
              {item.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
        </TableCell>
        <TableCell className="text-right font-semibold tabular-nums">{item.opened_recent}</TableCell>
        <TableCell className={cn("text-right font-semibold tabular-nums", (item.deviation_percentage || 0) >= 25 ? "text-red-600" : "text-slate-700")}>{item.deviation_percentage === null ? "—" : `${item.deviation_percentage > 0 ? "+" : ""}${number(item.deviation_percentage)}%`}</TableCell>
        <TableCell className={cn("text-right font-semibold tabular-nums", item.net_flow > 0 ? "text-red-600" : "text-emerald-700")}>{signed(item.net_flow)}</TableCell>
        <TableCell className="text-right tabular-nums">{item.backlog}</TableCell>
        <TableCell className="text-right tabular-nums text-red-600">{item.overdue_backlog}</TableCell>
        <TableCell className="text-right"><Button type="button" size="sm" variant="ghost" className="h-7 whitespace-nowrap px-2 text-[10px] text-blue-700" onClick={() => onOpenOrders(item.path)}>Ver O.S. <ExternalLink className="h-3 w-3" /></Button></TableCell>
      </TableRow>;
      return isExpanded && nested.length ? [row, ...rows(nested, depth + 1)] : [row];
    });
  }

  const status = STATUS[data.summary.status];
  const StatusIcon = status.icon;
  if (isLoading && !data.reference_date) return <div className="mt-4 h-[520px] animate-pulse rounded-2xl border bg-white" aria-label="Carregando monitor preventivo" />;

  return <section className="mt-4 space-y-4" aria-label="Monitor preventivo de aberturas">
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 py-4">
        <div><p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">Monitor preventivo</p><CardTitle className="mt-1 text-base font-semibold text-slate-950">A demanda está saindo do controle?</CardTitle><p className="mt-1 text-[11px] text-slate-500">Uma leitura direta do volume recente, capacidade de atendimento e pontos que exigem ação.</p></div>
        <Button type="button" variant="outline" size="sm" aria-expanded={isOpen} onClick={() => setIsOpen((current) => !current)}>{isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}{isOpen ? "Recolher monitor" : "Ver situação"}</Button>
      </CardHeader>
    </Card>
    {isOpen ? <>
      <div className={cn("grid gap-4 rounded-2xl border px-4 py-4 lg:grid-cols-[minmax(0,1fr)_auto]", status.panel)}>
        <div>
          <div className="flex flex-wrap items-center gap-2"><Badge className={cn("gap-1", status.className)}><StatusIcon className="h-3.5 w-3.5" />{status.label}</Badge><span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Situação atual</span></div>
          <h2 className="mt-2 text-lg font-semibold text-slate-950">{reading.title}</h2>
          <p className="mt-1 max-w-3xl text-sm leading-5 text-slate-700">{reading.description}</p>
          {data.summary.reasons.length ? (
            <ul className="mt-3 max-w-3xl space-y-1 rounded-lg border border-white/70 bg-white/70 px-3 py-2 text-xs text-slate-700">
              {data.summary.reasons.map((reason) => (
                <li key={reason} className="flex gap-1.5"><span aria-hidden>•</span>{reason}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-2 text-xs font-medium text-slate-700"><strong>Próximo passo:</strong> {reading.action}</p>
        </div>
        <div className="min-w-32 text-left lg:text-right"><p className="text-[9px] font-bold uppercase tracking-wide text-slate-400">Variação das aberturas</p><p className={cn("mt-1 text-3xl font-semibold tabular-nums", (data.summary.deviation_percentage || 0) > 0 ? "text-red-700" : "text-emerald-700")}>{data.summary.deviation_percentage === null ? "—" : `${data.summary.deviation_percentage > 0 ? "+" : ""}${number(data.summary.deviation_percentage)}%`}</p><p className="text-[10px] text-slate-500">comparado ao esperado</p></div>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-6">
        <SummaryMetric label="Aberturas recentes" value={number(data.summary.opened_recent, 0)} helper={`Esperado: ${number(data.summary.expected_opened)}`} />
        <SummaryMetric label="Balanço operacional" value={signed(data.summary.net_flow)} helper={`${number(data.summary.completed_recent, 0)} finalizadas`} accent={data.summary.net_flow > 0 ? "text-red-600" : "text-emerald-700"} />
        <SummaryMetric label="Estoque aberto" value={number(data.summary.backlog, 0)} helper={`${data.summary.overdue_backlog} vencidas`} accent={data.summary.overdue_backlog > 0 ? "text-red-600" : undefined} />
        <SummaryMetric label="Onde exige atenção" value={number(data.summary.critical_nodes + data.summary.attention_nodes, 0)} helper={`${data.summary.critical_nodes} críticos`} />
        <SummaryMetric label="Índice entradas/saídas" value={data.summary.pressure_ratio === null ? "—" : `${number(data.summary.pressure_ratio, 2)}x`} helper="Acima de 1x: entra mais do que sai" />
        <SummaryMetric label="Idade média do backlog" value={hours(data.summary.average_backlog_age_hours)} helper="Das O.S. ainda abertas" />
      </div>

      <Card className="overflow-hidden rounded-2xl border-slate-200 shadow-sm">
        <CardHeader className="flex-row items-start justify-between gap-4 pb-3"><div><p className="text-[9px] font-bold uppercase tracking-[0.18em] text-blue-600">Onde agir</p><CardTitle className="mt-1 text-base font-semibold text-slate-950">Assuntos que mais precisam de atenção</CardTitle><p className="mt-1 text-[11px] text-slate-500">Clique no assunto para avançar por Regional → Cidade → Setor → Responsável.</p></div><Badge className="border-blue-200 bg-blue-50 text-blue-700">{data.items.length} assuntos</Badge></CardHeader>
        <CardContent className="px-0 pb-0">
          {nodeError ? <div role="alert" className="mx-4 mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{nodeError}</div> : null}
          <div className="overflow-x-auto"><Table className="min-w-[880px]"><TableHeader><TableRow><TableHead className="sticky left-0 z-20 bg-slate-50">Grupo operacional</TableHead><TableHead>Situação</TableHead><TableHead className="text-right">Abertas</TableHead><TableHead className="text-right">Variação</TableHead><TableHead className="text-right">Saldo</TableHead><TableHead className="text-right">Backlog</TableHead><TableHead className="text-right">Vencidas</TableHead><TableHead /></TableRow></TableHeader><TableBody>{data.items.length ? rows(data.items) : <TableRow><TableCell colSpan={8} className="py-14 text-center text-sm text-slate-500">Não há volume suficiente para indicar pontos de ação.</TableCell></TableRow>}</TableBody></Table></div>
        </CardContent>
      </Card>

      <details className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-[10px] text-slate-500">
        <summary className="cursor-pointer font-semibold text-slate-700">Como o esperado e o risco são calculados?</summary>
        <p className="mt-2 max-w-4xl leading-5">{data.calculation_note} O esperado compara o mesmo dia da semana nas {data.baseline_weeks} semanas anteriores. Crítico exige persistência ou crescimento relevante junto com incapacidade de absorção; um pico isolado tende a ficar apenas em atenção. O filtro de responsável não altera as aberturas, porque a entrada da operação não pertence ao técnico que posteriormente recebe a O.S. O gráfico "Aberturas x finalizações" já mostrado nesta página cobre a mesma evolução ao longo do tempo.</p>
      </details>
    </> : null}
  </section>;
}
