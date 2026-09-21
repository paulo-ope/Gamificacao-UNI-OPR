"use client";

/** Fase 3 do plano de evolução analítica do Atendimento IXC (2026-09-14/15): tela única
 * (`IxcTicketAnalyticsPanel`) consumindo só os endpoints novos `/support/ixc/analytics/*`
 * (Fase 2) - substitui a navegação em duas telas (Visão Geral / Drill-down) por um contexto só
 * que muda de foco (regional -> cidade -> bairro -> motivo) sem trocar de componente.
 *
 * Roda em PARALELO aos componentes antigos (`ixc-ticket-overview.tsx`/`ixc-ticket-drilldown.tsx`)
 * atrás de um toggle interno em `page.tsx` (item 14 do plano: "não remove os componentes antigos
 * até validar visualmente") - nenhuma rota antiga foi alterada. */

import { AlertTriangle, ChevronRight, Gauge, TrendingUp, Zap } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { commonDateRangePresets, DateRangePicker } from "@/components/ui/date-range-picker";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type {
  SupportIxcAnalyticsContext,
  SupportIxcAnalyticsDimension,
  SupportIxcAnalyticsDriverItem,
  SupportIxcAnalyticsPriorityItem,
  SupportIxcSeverityBasis,
  SupportIxcTicketBurstWindow,
  SupportIxcTicketMomentum,
  SupportIxcTicketOsConversion,
  SupportIxcTicketOut,
  SupportIxcTicketSeverity,
} from "@/lib/types";

function number(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

function signedPct(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${number(value, 1)}%`;
}

// Mesmo vocabulário de severidade/tom de `ixc-ticket-overview.tsx` - duplicado aqui de propósito
// (mesmo padrão já usado entre `ixc-ticket-overview.tsx`/`ixc-ticket-drilldown.tsx`: cada painel
// é dono da própria formatação visual, não há um módulo compartilhado de "design tokens do IXC").
const SEVERITY_LABEL: Record<SupportIxcTicketSeverity, string> = {
  critico: "CRÍTICO",
  dentro_da_curva: "DENTRO DA CURVA",
  em_melhora: "EM MELHORA",
  sem_dado: "SEM DADO",
};

const SEVERITY_TONE: Record<SupportIxcTicketSeverity, "neutral" | "success" | "danger"> = {
  critico: "danger",
  dentro_da_curva: "neutral",
  em_melhora: "success",
  sem_dado: "neutral",
};

const SEVERITY_ROW_CLASS: Record<SupportIxcTicketSeverity, string> = {
  critico: "border-red-200 bg-red-50 hover:bg-red-100/70",
  dentro_da_curva: "border-slate-200 bg-white hover:bg-slate-50",
  em_melhora: "border-emerald-200 bg-emerald-50 hover:bg-emerald-100/70",
  sem_dado: "border-slate-200 bg-slate-50 hover:bg-slate-100/70",
};

const SEVERITY_TEXT_CLASS: Record<SupportIxcTicketSeverity, string> = {
  critico: "text-red-600",
  dentro_da_curva: "text-slate-400",
  em_melhora: "text-emerald-600",
  sem_dado: "text-slate-400",
};

const DIMENSION_LABEL: Record<SupportIxcAnalyticsDimension, string> = {
  regional: "Regional",
  city: "Cidade",
  neighborhood: "Bairro",
  subject: "Motivo",
};

// Item 1 da correção pedida (2026-09-17) - explica ao humano, não só à IA, de onde vem a
// severidade mostrada (nunca deixar "sem dado" parecer "normal").
const SEVERITY_BASIS_LABEL: Record<SupportIxcSeverityBasis, string> = {
  historical: "vs. histórico próprio",
  peers: "vs. pares (histórico próprio insuficiente)",
  insufficient_data: "sem base de comparação confiável",
};

const MOMENTUM_LABEL: Record<string, string> = {
  accelerating: "acelerando",
  decelerating: "desacelerando",
  stable: "estável",
  sem_dado: "sem dado suficiente",
};

function KpiTile({
  label,
  value,
  helper,
  tone = "neutral",
}: {
  label: string;
  value: string;
  helper: string;
  tone?: "neutral" | "success" | "danger";
}) {
  const toneClass = { neutral: "bg-white text-slate-950", success: "bg-emerald-50 text-emerald-950", danger: "bg-red-50 text-red-950" }[tone];
  const accentClass = { neutral: "bg-blue-600", success: "bg-emerald-600", danger: "bg-red-600" }[tone];
  return (
    <div className={`relative overflow-hidden rounded-2xl p-4 shadow-sm ${toneClass}`}>
      <span className={`absolute inset-x-0 top-0 h-1 ${accentClass}`} />
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold tabular-nums">{value}</p>
      <p className="mt-1.5 text-xs text-slate-500">{helper}</p>
    </div>
  );
}

function last30DaysRange() {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - 30);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { date_from: iso(from), date_to: iso(today) };
}

// Cor do risco ICC (peso do tema + sinal textual da descrição) - mesmos limiares/aviso de
// calibração visual de `ixc-ticket-drilldown.tsx` (duplicado aqui de propósito, mesmo padrão de
// cada painel ser dono da própria formatação visual já usado neste módulo).
function riskBadgeClass(score: number | null): string {
  if (score === null) return "border-slate-200 bg-slate-50 text-slate-400";
  if (score >= 70) return "border-red-200 bg-red-50 text-red-700";
  if (score >= 40) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-100 text-slate-600";
}

function dateTimeLabel(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Porto_Velho" }).format(
    new Date(value),
  );
}

type Scope = {
  regional: string | null;
  city: string | null;
  neighborhood: string | null;
  // Motivo escolhido ao clicar numa linha da dimensão "subject" (fim do drill) - guardado à parte
  // de `subjectLabel` porque `subjectId` é o id opaco do IXC (o que os endpoints esperam) e
  // `subjectLabel` é o nome (`subject_name`) que aparece na breadcrumb.
  subjectId: string | null;
  subjectLabel: string | null;
};

const EMPTY_SCOPE: Scope = { regional: null, city: null, neighborhood: null, subjectId: null, subjectLabel: null };

export function IxcTicketAnalyticsPanel({
  subjectIds = [],
  sectorIds = [],
}: {
  subjectIds?: string[];
  sectorIds?: string[];
}) {
  const [period, setPeriod] = useState(last30DaysRange);
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const [context, setContext] = useState<SupportIxcAnalyticsContext | null>(null);
  const [priorities, setPriorities] = useState<SupportIxcAnalyticsPriorityItem[]>([]);
  const [drivers, setDrivers] = useState<SupportIxcAnalyticsDriverItem[]>([]);
  const [tickets, setTickets] = useState<SupportIxcTicketOut[] | null>(null);
  // Item 8/10 da correção (2026-09-17): "hoje a IA recebe sinais que o usuário não vê na aba" -
  // momentum/burst/conversão em O.S. já existiam só pra IA (opr_ixc_brief); expostos aqui também.
  const [momentum, setMomentum] = useState<SupportIxcTicketMomentum | null>(null);
  const [bursts, setBursts] = useState<SupportIxcTicketBurstWindow[]>([]);
  const [osConversion, setOsConversion] = useState<SupportIxcTicketOsConversion | null>(null);
  const [expandedTicketId, setExpandedTicketId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const sharedSubjectId = subjectIds.join(",") || undefined;
  const sector_id = sectorIds.join(",") || undefined;
  // Motivo escolhido ao drillar (fim do caminho) sobrepõe o filtro compartilhado de motivo - uma
  // vez que o usuário clicou num motivo específico, é ESSE que define o recorte, não a lista da
  // barra de filtros (que pode ter vários motivos selecionados).
  const effectiveSubjectId = scope.subjectId ?? sharedSubjectId;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTickets(null);
    const params = {
      date_from: period.date_from,
      date_to: period.date_to,
      regional: scope.regional ?? undefined,
      city: scope.city ?? undefined,
      neighborhood: scope.neighborhood ?? undefined,
      subject_id: effectiveSubjectId,
      sector_id,
    };

    api
      .supportIxcAnalyticsContext(params)
      .then((contextData) => {
        if (cancelled) return;
        setContext(contextData);
        const nextDimension = contextData.next_dimension;
        return Promise.all([
          nextDimension
            ? api.supportIxcAnalyticsPriorities({ ...params, dimension: nextDimension })
            : Promise.resolve<SupportIxcAnalyticsPriorityItem[]>([]),
          api.supportIxcAnalyticsDrivers(params),
          // Fim do drill (sem próximo nível) - mostra os protocolos individuais, igual ao painel
          // clássico ("clica no motivo, mostra os motivos E os protocolos").
          nextDimension
            ? Promise.resolve(null)
            : api.supportIxcTickets({ ...params, limit: 100 }),
          // Sinais que a IA já via via opr_ixc_brief, agora também na tela (item 8/10).
          api.supportIxcAnalyticsMomentum({ regional: params.regional, city: params.city, subject_id: params.subject_id, sector_id: params.sector_id }),
          api.supportIxcAnalyticsBursts({ regional: params.regional }),
          api.supportIxcAnalyticsOsConversion(params),
        ]);
      })
      .then((result) => {
        if (cancelled || !result) return;
        const [prioritiesData, driversData, ticketPage, momentumData, burstsData, osConversionData] = result;
        setPriorities(prioritiesData);
        setDrivers(driversData);
        setTickets(ticketPage ? ticketPage.items : null);
        setMomentum(momentumData);
        setBursts(burstsData);
        setOsConversion(osConversionData);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar o painel analítico.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [period.date_from, period.date_to, scope.regional, scope.city, scope.neighborhood, effectiveSubjectId, sector_id]);

  function drillInto(item: SupportIxcAnalyticsPriorityItem) {
    if (item.dimension === "subject") {
      setScope((current) => ({ ...current, subjectId: item.key, subjectLabel: item.label }));
      return;
    }
    setScope((current) => ({ ...current, [item.dimension]: item.key }));
  }

  function goToScope(next: Scope) {
    setScope(next);
  }

  const breadcrumbSteps: { label: string; scope: Scope }[] = [
    { label: "Toda operação", scope: EMPTY_SCOPE },
    ...(scope.regional ? [{ label: scope.regional, scope: { ...EMPTY_SCOPE, regional: scope.regional } }] : []),
    ...(scope.city ? [{ label: scope.city, scope: { ...EMPTY_SCOPE, regional: scope.regional, city: scope.city } }] : []),
    ...(scope.neighborhood
      ? [{ label: scope.neighborhood, scope: { ...EMPTY_SCOPE, regional: scope.regional, city: scope.city, neighborhood: scope.neighborhood } }]
      : []),
    ...(scope.subjectId ? [{ label: scope.subjectLabel ?? scope.subjectId, scope }] : []),
  ];

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
        {breadcrumbSteps.map((step, index) => (
          <span key={step.label} className="flex items-center gap-1">
            {index > 0 ? <ChevronRight className="h-3.5 w-3.5 text-slate-300" /> : null}
            <button
              type="button"
              onClick={() => goToScope(step.scope)}
              className={index === breadcrumbSteps.length - 1 ? "font-semibold text-slate-900" : "text-slate-500 hover:text-slate-900"}
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
        onChange={(key, value) => setPeriod((current) => ({ ...current, [key]: value }))}
      />

      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
          <AlertTriangle className="h-4 w-4" /> {error}
        </div>
      ) : null}

      {loading ? (
        <div aria-busy className="grid gap-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-28 animate-pulse rounded-2xl bg-slate-100" />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
        </div>
      ) : null}

      {!loading && !error && context ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile
              label="Atendimentos"
              value={number(context.ticket_count)}
              helper={`Período anterior: ${number(context.previous_ticket_count)}`}
            />
            <KpiTile
              label="Por 1.000 clientes ativos"
              value={context.tickets_per_1000_contracts !== null ? `${number(context.tickets_per_1000_contracts, 2)} / 1.000` : "-"}
              helper={context.contract_count !== null ? `Base: ${number(context.contract_count)}` : "Base indisponível neste nível"}
            />
            <KpiTile
              label="Desvio vs. período anterior"
              value={signedPct(context.deviation_pct)}
              helper={SEVERITY_LABEL[context.severity]}
              tone={SEVERITY_TONE[context.severity]}
            />
            <KpiTile
              label="Clientes únicos afetados"
              value={number(context.reach.unique_customers)}
              helper={
                context.reach.tickets_per_customer !== null
                  ? `${number(context.reach.tickets_per_customer, 2)} atend./cliente · ${number(context.reach.repeat_customers)} reincidente(s)`
                  : "Sem cliente vinculado no recorte"
              }
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="mb-3 flex items-center gap-2">
              <Zap className="h-4 w-4 text-blue-600" />
              <p className="text-sm font-semibold text-slate-900">Sinais</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Base da severidade</p>
                <p className="text-sm font-medium text-slate-800">{SEVERITY_BASIS_LABEL[context.severity_basis]}</p>
              </div>
              {momentum ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Tendência (momentum)</p>
                  <p className="text-sm font-medium text-slate-800">
                    {MOMENTUM_LABEL[momentum.trend] ?? momentum.trend}
                    {momentum.consecutive_days_above_expected > 0
                      ? ` · ${number(momentum.consecutive_days_above_expected)} dia(s) seguido(s) acima do esperado`
                      : ""}
                  </p>
                </div>
              ) : null}
              {(() => {
                const activeBurst = bursts.find((burst) => burst.active);
                if (!activeBurst) return null;
                return (
                  <div className="rounded-xl border border-red-200 bg-red-50 p-3">
                    <p className="text-xs text-red-600">Burst ativo</p>
                    <p className="text-sm font-medium text-red-800">
                      Janela {activeBurst.window}:{" "}
                      {activeBurst.ratio !== null ? `${number(activeBurst.ratio, 1)}x o esperado` : `${number(activeBurst.observed)} atendimentos`}
                    </p>
                  </div>
                );
              })()}
              {context.geographic_concentration?.city ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Concentração geográfica</p>
                  <p className="text-sm font-medium text-slate-800">
                    {context.geographic_concentration.city.value} · {number(context.geographic_concentration.city.share_pct, 1)}%
                    {context.geographic_concentration.neighborhood
                      ? ` (bairro ${context.geographic_concentration.neighborhood.value}: ${number(context.geographic_concentration.neighborhood.share_pct, 1)}%)`
                      : ""}
                  </p>
                </div>
              ) : null}
              {osConversion && osConversion.sample > 0 ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Conversão em O.S. (24h)</p>
                  <p className="text-sm font-medium text-slate-800">
                    {osConversion.conversions["24h"] !== null && osConversion.conversions["24h"] !== undefined
                      ? `${number(osConversion.conversions["24h"], 1)}%`
                      : "-"}{" "}
                    · amostra {number(osConversion.sample)}
                  </p>
                </div>
              ) : null}
            </div>
          </div>

          {context.reach.repeat_contact && Object.values(context.reach.repeat_contact).some((count) => count > 0) ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm sm:p-5">
              <div className="mb-2 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                <p className="text-sm font-semibold text-slate-900">Reincidência pelo mesmo motivo</p>
              </div>
              <p className="mb-3 text-xs text-slate-600">
                Mesmo cliente voltou a entrar em contato pelo MESMO motivo depois do atendimento anterior - sinal de que
                o atendimento anterior pode não ter resolvido o problema.
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(context.reach.repeat_contact).map(([window, count]) => (
                  <span
                    key={window}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700"
                  >
                    <span className="text-slate-500">em até {window}:</span>
                    <span className="font-semibold text-slate-900">{number(count)}</span>
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {context.top_driver ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <div className="mb-3 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-blue-600" />
                <p className="text-sm font-semibold text-slate-900">Principais motivos do excesso</p>
              </div>
              <div className="grid gap-2">
                {drivers
                  .filter((driver) => driver.excess > 0)
                  .slice(0, 5)
                  .map((driver) => (
                    <div key={driver.subject_name} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5">
                      <div>
                        <p className="text-sm font-medium text-slate-800">{driver.subject_name}</p>
                        <p className="text-xs text-slate-500">
                          {number(driver.current)} atual · {number(driver.expected)} esperado · excesso de {number(driver.excess)}
                        </p>
                      </div>
                      <p className="text-sm font-semibold text-blue-700">{number(driver.contribution_pct, 1)}%</p>
                    </div>
                  ))}
                {!drivers.some((driver) => driver.excess > 0) ? (
                  <p className="py-2 text-center text-xs text-slate-500">Nenhum motivo com excesso vs. o período anterior.</p>
                ) : null}
              </div>
            </div>
          ) : null}

          {context.next_dimension ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <div className="mb-3 flex items-center gap-2">
                <Gauge className="h-4 w-4 text-blue-600" />
                <div>
                  <p className="text-sm font-semibold text-slate-900">Prioridades por {DIMENSION_LABEL[context.next_dimension]}</p>
                  <p className="text-xs text-slate-500">Clique em uma linha para aprofundar a leitura.</p>
                </div>
              </div>
              <div className="grid gap-2">
                {!priorities.length ? (
                  <p className="py-6 text-center text-sm text-slate-500">Sem prioridades detectadas no período.</p>
                ) : (
                  priorities.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => drillInto(item)}
                      className={`flex items-center justify-between gap-3 rounded-xl border p-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${SEVERITY_ROW_CLASS[item.severity]}`}
                    >
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{item.label}</p>
                        <p className={`text-[11px] font-semibold ${SEVERITY_TEXT_CLASS[item.severity]}`}>{SEVERITY_LABEL[item.severity]}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="text-right">
                          <p className="text-sm font-semibold text-slate-900">{number(item.ticket_count)} atend.</p>
                          <p className="text-xs text-slate-500">
                            {item.tickets_per_1000_contracts !== null
                              ? `${number(item.tickets_per_1000_contracts, 2)} / 1.000 · `
                              : ""}
                            {signedPct(item.deviation_pct)} vs. anterior
                          </p>
                        </div>
                        <ChevronRight className="h-4 w-4 shrink-0 text-slate-300" />
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <p className="mb-3 text-sm font-semibold text-slate-900">Protocolos deste motivo</p>
              {!tickets || !tickets.length ? (
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
                              title={ticket.subtema_inferido ? `Subtema inferido pela descrição: ${ticket.subtema_inferido}` : "Sem subtema inferido"}
                            >
                              {ticket.risk_score ?? "-"}
                              {ticket.subtema_inferido ? ` · ${ticket.subtema_inferido}` : ""}
                            </span>
                          </TableCell>
                          <TableCell className="text-right text-xs tabular-nums text-slate-500">{dateTimeLabel(ticket.created_at)}</TableCell>
                        </TableRow>
                        {expandedTicketId === ticket.id && ticket.report ? (
                          <TableRow>
                            <TableCell colSpan={6} className="whitespace-pre-line bg-slate-50 text-xs leading-relaxed text-slate-600">
                              <span className="font-semibold text-slate-700">Relato protocolado: </span>
                              {ticket.report}
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
