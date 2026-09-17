"use client";

import { AlertTriangle, ChevronRight, Loader2, TrendingUp } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { commonDateRangePresets, DateRangePicker } from "@/components/ui/date-range-picker";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type {
  SupportIxcTicketBreakdown,
  SupportIxcTicketBreakdownItem,
  SupportIxcTicketBreakdownLevel,
  SupportIxcTicketOut,
} from "@/lib/types";

import { number } from "./opa-module-components";

/** Um degrau da navegação: regional -> cidade -> bairro -> motivo. Cada clique empilha aqui;
 * clicar num breadcrumb anterior corta a pilha de volta pra aquele ponto. */
type DrilldownStep = {
  level: SupportIxcTicketBreakdownLevel;
  key: string;
  label: string;
};

const LEVEL_LABEL: Record<SupportIxcTicketBreakdownLevel, string> = {
  regional: "Regional",
  city: "Cidade",
  neighborhood: "Bairro",
  reason: "Motivo",
};

const NEXT_LEVEL: Record<SupportIxcTicketBreakdownLevel, SupportIxcTicketBreakdownLevel | null> = {
  regional: "city",
  city: "neighborhood",
  neighborhood: "reason",
  reason: null,
};

function dateTimeLabel(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Porto_Velho",
  }).format(new Date(value));
}

/** `value` é uma data pura "YYYY-MM-DD" (limite de período, não timestamp de atendimento) - fixa
 * meio-dia UTC pra não virar o dia anterior/seguinte na virada de fuso do navegador. */
function periodBoundaryLabel(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${value}T12:00:00Z`),
  );
}

/** Barra proporcional ao maior valor da lista - dá noção visual de peso relativo sem precisar
 * de biblioteca de gráfico (o frontend deste projeto ainda não tem nenhuma, ver docs/STATUS.md). */
function RelativeBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full bg-blue-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

function signedPct(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}%`;
}

/** Cor do desvio vs. o período anterior de mesmo tamanho (pedido do usuário, 2026-09-12: "no
 * drill ainda está sem dados de desvio") - mesmo vocabulário de cor da Visão Geral (vermelho =
 * piorou, verde = melhorou), mas sem rótulo de severidade (CRÍTICO/etc.): aqui é só o número,
 * a classificação por faixa fica na Visão Geral. */
function DeviationCell({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-xs text-slate-400">sem dado</span>;
  }
  const colorClass = value > 0 ? "text-red-600" : value < 0 ? "text-emerald-600" : "text-slate-500";
  return <span className={`text-xs font-semibold tabular-nums ${colorClass}`}>{signedPct(value)}</span>;
}

// Cor do risco ICC (peso do tema + sinal textual da descrição, ver `ixc_ticket_text_signal.py`) -
// limiares alinhados com os pesos-base da taxonomia (>=70 cobre "suporte técnico"/"sem conexão"
// elevado, >=40 cobre "equipamentos"/"CTO-rede") - primeira calibração visual, mesmo aviso dos
// demais limiares deste módulo.
function riskBadgeClass(score: number | null): string {
  if (score === null) return "border-slate-200 bg-slate-50 text-slate-400";
  if (score >= 70) return "border-red-200 bg-red-50 text-red-700";
  if (score >= 40) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-100 text-slate-600";
}

function last30DaysRange() {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - 30);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { date_from: iso(from), date_to: iso(today) };
}

export function IxcTicketDrilldownPanel({
  initialRegional,
  onBackToOverview,
  subjectIds = [],
  sectorIds = [],
}: {
  initialRegional?: string;
  onBackToOverview?: () => void;
  // Filtro de motivo/setor - controlado pela barra compartilhada (ver
  // ixc-ticket-filters-bar.tsx/page.tsx), não vive mais aqui: precisa persistir ao trocar entre
  // Visão Geral e drill-down (pedido do usuário, 2026-09-12).
  subjectIds?: string[];
  sectorIds?: string[];
}) {
  const [steps, setSteps] = useState<DrilldownStep[]>(
    initialRegional ? [{ level: "regional", key: initialRegional, label: initialRegional }] : [],
  );
  // Período próprio desta aba - os filtros do OPA (período/atendente/departamento/canal) não se
  // aplicam ao atendimento IXC, outra fonte de dado (pedido explícito do usuário, 2026-09-12).
  // O preset "Hoje" já cobre "filtro de um dia só" sem precisar de nada especial.
  const [period, setPeriod] = useState(last30DaysRange);
  const [breakdown, setBreakdown] = useState<SupportIxcTicketBreakdown | null>(null);
  const [tickets, setTickets] = useState<SupportIxcTicketOut[] | null>(null);
  const [expandedTicketId, setExpandedTicketId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const level: SupportIxcTicketBreakdownLevel = steps.length === 0 ? "regional" : (NEXT_LEVEL[steps[steps.length - 1].level] ?? "reason");
  const regional = steps.find((s) => s.level === "regional")?.key;
  const city = steps.find((s) => s.level === "city")?.key;
  const neighborhood = steps.find((s) => s.level === "neighborhood")?.key;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setBreakdown(null);
    setTickets(null);

    // Multi-seleção (2026-09-12): filtrar por 1+ motivos aqui vale mesmo no nível "reason" - ele
    // já agrupa por motivo, mas restringir a lista aos motivos escolhidos continua fazendo
    // sentido (só resultaria numa linha só se exatamente 1 motivo estivesse selecionado).
    const subject_id = subjectIds.join(",") || undefined;
    const sector_id = sectorIds.join(",") || undefined;
    const params = { level, regional, city, neighborhood, subject_id, sector_id, ...period };

    if (level === "reason") {
      // Nó final: mostra motivos agrupados E a lista de protocolos individuais, como pedido
      // explicitamente ("clica no bairro, mostra os motivos E os protocolos").
      Promise.all([
        api.supportIxcTicketBreakdown(params),
        api.supportIxcTickets({
          regional,
          city,
          neighborhood,
          subject_id,
          sector_id,
          limit: 100,
          ...period,
        }),
      ])
        .then(([breakdownData, ticketPage]) => {
          if (cancelled) return;
          setBreakdown(breakdownData);
          setTickets(ticketPage.items);
        })
        .catch((reason: unknown) => {
          if (cancelled) return;
          setError(reason instanceof Error ? reason.message : "Falha ao carregar o detalhamento.");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    } else {
      api
        .supportIxcTicketBreakdown(params)
        .then((data) => {
          if (cancelled) return;
          setBreakdown(data);
        })
        .catch((reason: unknown) => {
          if (cancelled) return;
          setError(reason instanceof Error ? reason.message : "Falha ao carregar o detalhamento.");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, regional, city, neighborhood, period.date_from, period.date_to, subjectIds, sectorIds]);

  function drillInto(item: SupportIxcTicketBreakdownItem) {
    if (level === "reason") return;
    setSteps((current) => [...current, { level, key: item.key, label: item.label }]);
  }

  function goToStep(index: number) {
    setSteps((current) => current.slice(0, index + 1));
  }

  // Quando entra via uma prioridade da Visão Geral (initialRegional definido), a regional é o
  // PISO da navegação - nunca existiu um caminho "indo pra frente" que passasse pela lista de
  // TODAS as regionais (o clique na prioridade já pula direto pra Cidade). Deixar "voltar" cair
  // nessa lista era o bug relatado pelo usuário (2026-09-12): ela usa uma conta diferente da
  // Visão Geral (período livre da própria aba vs. média histórica/mês) e mostra um número
  // diferente pra mesma regional - uma tela que "aparece voltando" mas nunca existiu "indo".
  // Voltar além do piso agora sai pra Visão Geral em vez de revelar essa tela solta.
  function goBackOneLevel() {
    setSteps((current) => {
      if (initialRegional && current.length <= 1) {
        onBackToOverview?.();
        return current;
      }
      return current.slice(0, -1);
    });
  }

  function goToRoot() {
    if (initialRegional) {
      onBackToOverview?.();
      return;
    }
    setSteps([]);
  }

  const items = breakdown?.items ?? [];
  const maxTickets = items.reduce((max, item) => Math.max(max, item.ticket_count), 0);
  const hasRateColumn = items.some((item) => item.contract_count !== null);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
        {onBackToOverview ? (
          <>
            <button type="button" onClick={onBackToOverview} className="text-slate-500 hover:text-slate-900">
              Visão Geral
            </button>
            <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
          </>
        ) : null}
        {!initialRegional ? (
          <button
            type="button"
            onClick={goToRoot}
            className={steps.length === 0 ? "font-semibold text-slate-900" : "text-slate-500 hover:text-slate-900"}
          >
            Todas as regionais
          </button>
        ) : null}
        {steps.map((step, index) => (
          <span key={`${step.level}-${step.key}`} className="flex items-center gap-1">
            <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
            <button
              type="button"
              onClick={() => goToStep(index)}
              className={index === steps.length - 1 ? "font-semibold text-slate-900" : "text-slate-500 hover:text-slate-900"}
            >
              {step.label}
            </button>
          </span>
        ))}
      </div>

      <DateRangePicker
        dateFrom={period.date_from}
        dateTo={period.date_to}
        presets={commonDateRangePresets()}
        // Atualização funcional: presets e a inversão de intervalo chamam onChange duas vezes
        // seguidas (date_from e date_to) na mesma interação - ver mesmo achado documentado em
        // OpaGlobalFilters (2026-08-27).
        onChange={(key, value) => setPeriod((current) => ({ ...current, [key]: value }))}
      />

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-3 flex flex-row items-center justify-between gap-2">
          <div>
            <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <TrendingUp className="h-4 w-4 text-blue-600" />
              {LEVEL_LABEL[level]}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {periodBoundaryLabel(period.date_from)} até {periodBoundaryLabel(period.date_to)} · atendimento IXC
              (indicador antecipado, não substitui a O.S.)
            </p>
          </div>
          {loading ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : null}
        </div>
        {error ? (
          <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4" /> {error}
          </div>
        ) : null}

        {!error && !loading && !items.length ? (
          <p className="py-8 text-center text-sm text-slate-500">Nenhum atendimento neste recorte.</p>
        ) : null}

        {!error && items.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{LEVEL_LABEL[level]}</TableHead>
                <TableHead className="text-right">Atendimentos</TableHead>
                {hasRateColumn ? <TableHead className="text-right">Clientes ativos</TableHead> : null}
                {hasRateColumn ? <TableHead className="text-right">Por 1.000</TableHead> : null}
                <TableHead className="text-right">Desvio</TableHead>
                <TableHead className="w-32">Peso</TableHead>
                {level !== "reason" ? <TableHead className="w-8" /> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow
                  key={item.key}
                  className={level !== "reason" ? "cursor-pointer hover:bg-slate-50" : undefined}
                  onClick={() => drillInto(item)}
                >
                  <TableCell className="font-medium text-slate-800">{item.label}</TableCell>
                  <TableCell className="text-right tabular-nums">{number(item.ticket_count)}</TableCell>
                  {hasRateColumn ? (
                    <TableCell className="text-right tabular-nums text-slate-500">
                      {item.contract_count !== null ? number(item.contract_count) : "-"}
                    </TableCell>
                  ) : null}
                  {hasRateColumn ? (
                    <TableCell className="text-right tabular-nums font-semibold text-slate-800">
                      {item.tickets_per_1000_contracts !== null ? (
                        number(item.tickets_per_1000_contracts, 2)
                      ) : item.contract_count !== null ? (
                        <span
                          className="cursor-help text-xs font-normal text-amber-600"
                          title={`Base insuficiente: só ${number(item.coverage_pct, 1)}% dos contratos ativos da regional têm cidade cadastrada no IXC - a taxa não seria confiável.`}
                        >
                          Base insuficiente
                        </span>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                  ) : null}
                  <TableCell className="text-right">
                    <DeviationCell value={item.deviation_pct} />
                  </TableCell>
                  <TableCell>
                    <RelativeBar value={item.ticket_count} max={maxTickets} />
                  </TableCell>
                  {level !== "reason" ? (
                    <TableCell>
                      <ChevronRight className="h-4 w-4 text-slate-300" />
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </div>

      {level === "reason" && tickets ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <p className="mb-3 text-sm font-semibold text-slate-900">Protocolos deste bairro</p>
          {!tickets.length ? (
            <p className="py-6 text-center text-sm text-slate-500">Nenhum protocolo neste recorte.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Protocolo</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Risco</TableHead>
                  <TableHead className="text-right">Aberto em</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tickets.map((ticket) => (
                  <Fragment key={ticket.id}>
                    <TableRow
                      className={ticket.report ? "cursor-pointer hover:bg-slate-50" : undefined}
                      onClick={() => ticket.report && setExpandedTicketId((current) => (current === ticket.id ? null : ticket.id))}
                    >
                      <TableCell className="font-mono text-xs text-slate-700">{ticket.protocol ?? ticket.source_id}</TableCell>
                      <TableCell className="max-w-48 truncate text-sm text-slate-700">{ticket.customer_name ?? "Não informado"}</TableCell>
                      <TableCell className="text-sm text-slate-600">{ticket.subject_name ?? "Não informado"}</TableCell>
                      <TableCell>
                        <Badge className="border-slate-200 bg-slate-100 text-slate-700">{ticket.status ?? "-"}</Badge>
                      </TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${riskBadgeClass(ticket.risk_score)}`}
                          title={ticket.subtema_inferido ? `Subtema inferido pela descrição: ${ticket.subtema_inferido}` : "Sem subtema inferido (descrição neutra ou ausente)"}
                        >
                          {ticket.risk_score ?? "-"}
                          {ticket.subtema_inferido ? ` · ${ticket.subtema_inferido}` : ""}
                        </span>
                      </TableCell>
                      <TableCell className="text-right text-xs tabular-nums text-slate-500">
                        {dateTimeLabel(ticket.created_at)}
                      </TableCell>
                    </TableRow>
                    {expandedTicketId === ticket.id && ticket.report ? (
                      <TableRow>
                        <TableCell colSpan={6} className="whitespace-pre-line bg-slate-50 text-xs leading-relaxed text-slate-600">
                          <span className="font-semibold text-slate-700">Relato protocolado: </span>
                          {ticket.report}
                          {ticket.theme_label ? (
                            <p className="mt-1.5 text-slate-500">
                              <span className="font-semibold text-slate-700">Tema: </span>
                              {ticket.category_label} / {ticket.theme_label}
                            </p>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      ) : null}

      {steps.length > 0 ? (
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={goBackOneLevel}>
          Voltar
        </Button>
      ) : null}
    </div>
  );
}
