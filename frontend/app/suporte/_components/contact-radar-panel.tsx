"use client";

import { AlertCircle, CalendarDays, ChevronRight, Loader2, MapPinned, Radar, RefreshCw, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { KpiCard, SPARK_COLOR } from "@/components/overview/overview-kpi-strip";
import { Button } from "@/components/ui/button";
import { MultiSelect } from "@/components/ui/multi-select";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { api } from "@/lib/api";
import { momentLabel, seriesLabels } from "@/lib/contact-radar-chart-options";
import { percentChange } from "@/lib/period";
import type { SupportContactRadar, SupportContactRadarProtocol, SupportContactRadarRegional, SupportContactRadarStats, SupportOpaFilterOption } from "@/lib/types";

import { localIso, number, percent, regionalLabel } from "./occurrences-format";
import { opaStatusLabel } from "./opa-module-components";
import { OpaDepartmentChip, OpaTagChip } from "./opa-tag-chip";

// Radar de Contatos (Suporte Interno): de onde os clientes estão entrando em contato pelo OPA.
// Só leitura. A localização do cliente (cidade/bairro/regional), a contagem por cliente distinto, a
// comparação com o habitual e o escopo regional do usuário vivem no backend
// (`contact_radar_service.py`); aqui só se formata o que já veio agrupado: regional > cidade > bairro.
//
// Dois modos: "Ao vivo" (últimos N minutos, comparado com a mesma janela dos 7 dias anteriores) e
// "Por período" (de uma data a outra, comparado com o período anterior de mesmo tamanho).

const REFRESH_MS = 60_000;
const MAX_RANGE_DAYS = 31;
const WINDOWS = [
  { value: 15, label: "Últimos 15 min" },
  { value: 30, label: "Últimos 30 min" },
  { value: 60, label: "Última hora" },
  { value: 180, label: "Últimas 3 horas" },
  { value: 720, label: "Últimas 12 horas" },
  { value: 1440, label: "Últimas 24 horas" },
];
const CHANNELS = [
  { value: "", label: "Todos os canais" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "pabx", label: "Ligação" },
  { value: "page", label: "Chat do site" },
];
const CHANNEL_LABEL: Record<string, string> = { whatsapp: "WhatsApp", pabx: "Ligação", page: "Chat do site" };

export type RadarMode = "window" | "range";
export type RadarQuery = {
  mode: RadarMode;
  windowMinutes: number;
  dateFrom: string;
  dateTo: string;
  channel: string;
  departmentIds: string[];
};

// Departamentos que já vêm selecionados (pedido do usuário, 2026-10-20): Suporte Técnico e Financeiro, os
// mesmos de "Indicadores do Suporte". Casados pelo nome, sem acento nem caixa, porque o id vem do OPA e não
// é fixo. A tela sempre abre com este padrão; a escolha feita nela vale só até recarregar.
const DEFAULT_DEPARTMENT_LABELS = ["suporte tecnico", "financeiro"];

function normalizeLabel(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
}

export function defaultDepartmentIds(departments: SupportOpaFilterOption[]) {
  return departments.filter((option) => DEFAULT_DEPARTMENT_LABELS.includes(normalizeLabel(option.label))).map((option) => option.value);
}

function daysAgoIso(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return localIso(date);
}

const PRESETS = [
  { key: "today", label: "Hoje", range: () => ({ dateFrom: daysAgoIso(0), dateTo: daysAgoIso(0) }) },
  { key: "yesterday", label: "Ontem", range: () => ({ dateFrom: daysAgoIso(1), dateTo: daysAgoIso(1) }) },
  { key: "7d", label: "Últimos 7 dias", range: () => ({ dateFrom: daysAgoIso(6), dateTo: daysAgoIso(0) }) },
  { key: "30d", label: "Últimos 30 dias", range: () => ({ dateFrom: daysAgoIso(29), dateTo: daysAgoIso(0) }) },
];

function rangeDays(dateFrom: string, dateTo: string) {
  const from = Date.parse(`${dateFrom}T00:00:00Z`);
  const to = Date.parse(`${dateTo}T00:00:00Z`);
  return Number.isNaN(from) || Number.isNaN(to) ? NaN : Math.round((to - from) / 86_400_000) + 1;
}

/** Texto de erro da validação do período escolhido, ou null quando pode consultar. */
export function rangeProblem(query: RadarQuery): string | null {
  if (query.mode !== "range") return null;
  if (!query.dateFrom || !query.dateTo) return "Escolha a data inicial e a final.";
  const days = rangeDays(query.dateFrom, query.dateTo);
  if (Number.isNaN(days)) return "Data inválida.";
  if (days < 1) return "A data final não pode ser anterior à inicial.";
  if (days > MAX_RANGE_DAYS) return `O período máximo é de ${MAX_RANGE_DAYS} dias.`;
  return null;
}

function ratioLabel(item: SupportContactRadarStats) {
  if (item.ratio == null) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(item.ratio)}×`;
}

function decimal(value: number) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value);
}

type TreeProps = {
  regionals: SupportContactRadarRegional[];
  /** Recorte da consulta: com ele, abrir uma cidade carrega os protocolos dela. */
  query?: RadarQuery;
  /** Muda a cada recarga do radar, para a lista de protocolos abertos acompanhar. */
  refreshKey?: string;
  compare: boolean;
  baselineLabel: string;
  baselineHint: string;
};

// Colunas: nome, clientes, contatos, comparação, variação, situação. A mesma grade vale para o cabeçalho e
// para as três profundidades, para os números ficarem alinhados.
const GRID = "grid grid-cols-[minmax(0,1fr)_72px_72px_88px_72px_132px] items-center gap-2";

function StatCells({ item, compare }: { item: SupportContactRadarStats; compare: boolean }) {
  return (
    <>
      <span className="text-right font-semibold tabular-nums text-slate-900">{number(item.customers)}</span>
      <span className="text-right tabular-nums text-slate-600">{number(item.contacts)}</span>
      <span className="text-right tabular-nums text-slate-600">{compare ? decimal(item.baseline) : "—"}</span>
      <span className="text-right tabular-nums text-slate-700">{compare ? ratioLabel(item) : "—"}</span>
      <span>
        {!compare ? <span className="text-xs text-slate-400">—</span> : item.elevated ? <StatusBadge tone="red" icon={TriangleAlert}>Acima do usual</StatusBadge> : <span className="text-xs text-slate-400">Normal</span>}
      </span>
    </>
  );
}

function ToggleRow({ open, onToggle, label, hint, depth, item, compare }: {
  open: boolean;
  onToggle: () => void;
  label: string;
  hint?: string;
  depth: 0 | 1 | 2;
  item: SupportContactRadarStats;
  compare: boolean;
}) {
  return (
    <button
      type="button"
      aria-expanded={open}
      onClick={onToggle}
      className={`${GRID} w-full px-3 py-2.5 text-left text-sm transition hover:bg-slate-50 ${item.elevated && compare ? "bg-rose-50/60" : ""} ${depth === 1 ? "pl-9" : depth === 2 ? "pl-[3.25rem]" : ""}`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <ChevronRight size={16} className={`shrink-0 text-slate-400 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden="true" />
        <span className={`truncate ${depth === 0 ? "font-semibold text-slate-950" : depth === 1 ? "font-medium text-slate-800" : "text-slate-700"}`} title={label}>{label}</span>
        {hint ? <span className="shrink-0 text-xs text-slate-400">{hint}</span> : null}
      </span>
      <StatCells item={item} compare={compare} />
    </button>
  );
}

function plural(count: number, one: string, many: string) {
  return `${number(count)} ${count === 1 ? one : many}`;
}

const PROTOCOL_PAGE_SIZE = 50;

export function ProtocolRow({ item, showNeighborhood = true }: { item: SupportContactRadarProtocol; showNeighborhood?: boolean }) {
  const meta = [momentLabel(item.opened_at), showNeighborhood ? item.neighborhood : null, item.channel ? (CHANNEL_LABEL[item.channel] ?? item.channel) : null, opaStatusLabel(item.status)].filter(Boolean).join(" · ");
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 pl-[4.5rem] text-sm">
      <span className="font-mono text-[13px] font-semibold text-slate-900">{item.protocol ?? item.source_id}</span>
      {item.department_name ? <OpaDepartmentChip name={item.department_name} /> : null}
      {item.tags.map((tag) => <OpaTagChip key={tag.id} tag={tag} />)}
      <span className="ml-auto text-xs text-slate-500">{meta}</span>
    </li>
  );
}

/**
 * Protocolos do OPA de um bairro no mesmo recorte do radar, com as etiquetas de cada um na cor do OPA. Cada
 * protocolo fica no bairro em que foi aberto. Só é montado quando o bairro é aberto, então nada é buscado até
 * alguém olhar.
 */
export function NeighborhoodProtocols({ regional, city, neighborhood, query, refreshKey }: { regional: string; city: string; neighborhood: string; query: RadarQuery; refreshKey?: string }) {
  const [items, setItems] = useState<SupportContactRadarProtocol[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [retry, setRetry] = useState(0);
  const departmentKey = query.departmentIds.join(",");

  const request = useCallback(
    (offset: number) =>
      api.supportContactRadarProtocols({
        regional,
        city,
        neighborhood,
        window_minutes: query.windowMinutes,
        date_from: query.mode === "range" ? query.dateFrom : undefined,
        date_to: query.mode === "range" ? query.dateTo : undefined,
        channel: query.channel,
        department_ids: query.departmentIds,
        limit: PROTOCOL_PAGE_SIZE,
        offset,
      }),
    // `departmentKey` representa `query.departmentIds` sem refazer a consulta a cada novo array igual.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [regional, city, neighborhood, query.mode, query.windowMinutes, query.dateFrom, query.dateTo, query.channel, departmentKey],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    request(0)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar os protocolos deste bairro.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request, refreshKey, retry]);

  const loadMore = () => {
    setMore(true);
    request(items.length)
      .then((page) => {
        setItems((current) => [...current, ...page.items]);
        setTotal(page.total);
      })
      .catch(() => setError("Não foi possível carregar mais protocolos."))
      .finally(() => setMore(false));
  };

  return (
    <div className="border-b border-slate-100 pb-2">
      <p className="px-3 pb-1 pl-[4.5rem] pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Protocolos{!loading || items.length ? ` · ${number(total)}` : ""}
      </p>
      {error ? (
        <p className="flex items-center gap-3 px-3 py-2 pl-[4.5rem] text-xs text-rose-700" role="alert">
          {error}
          <Button variant="outline" size="sm" onClick={() => { setError(null); setRetry((current) => current + 1); }}>Tentar novamente</Button>
        </p>
      ) : null}
      {loading && items.length === 0 && !error ? (
        <p className="flex items-center gap-2 px-3 py-2 pl-[4.5rem] text-xs text-slate-500" role="status"><Loader2 size={14} className="animate-spin" aria-hidden="true" /> Carregando protocolos…</p>
      ) : null}
      {!loading && !error && items.length === 0 ? <p className="px-3 py-2 pl-[4.5rem] text-xs text-slate-500">Nenhum protocolo neste bairro no recorte.</p> : null}
      {items.length ? (
        <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto" aria-label={`Protocolos de ${neighborhood}, ${city}`}>
          {items.map((item) => <ProtocolRow key={item.source_id} item={item} showNeighborhood={false} />)}
        </ul>
      ) : null}
      {items.length && items.length < total ? (
        <div className="px-3 pl-[4.5rem] pt-2">
          <Button variant="outline" size="sm" onClick={loadMore} disabled={more}>
            {more ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : null}
            Carregar mais ({number(total - items.length)} restantes)
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** Regionais; ao clicar numa, abrem as cidades que entraram em contato; numa cidade, os bairros; num bairro, os protocolos abertos nele. */
export function RegionalTree({ regionals, query, refreshKey, compare, baselineLabel, baselineHint, initialOpen = [] }: TreeProps & { initialOpen?: string[] }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(initialOpen));
  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const allKeys = regionals.flatMap((regional) => [regional.regional, ...regional.cities.map((city) => `${regional.regional}|${city.city}`)]);
  const everythingOpen = allKeys.length > 0 && allKeys.every((key) => open.has(key));

  return (
    <section className="min-w-0 rounded-2xl bg-white p-2 shadow-sm" aria-label="Contatos por regional">
      <div className="flex items-center justify-between px-3 pb-1 pt-2">
        <h3 className="text-sm font-semibold text-slate-900">Por regional</h3>
        <Button variant="outline" size="sm" onClick={() => setOpen(everythingOpen ? new Set() : new Set(allKeys))}>
          {everythingOpen ? "Recolher tudo" : "Expandir tudo"}
        </Button>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[680px]">
          <div className={`${GRID} border-b border-slate-100 px-3 py-2 pl-9 text-xs font-medium uppercase tracking-wide text-slate-500`}>
            <span>Regional · cidade · bairro</span>
            <span className="text-right">Clientes</span>
            <span className="text-right">Contatos</span>
            <span className="text-right" title={baselineHint}>{baselineLabel}</span>
            <span className="text-right">Variação</span>
            <span>Situação</span>
          </div>
          <ul className="divide-y divide-slate-100">
            {regionals.map((regional) => (
              <li key={regional.regional}>
                <ToggleRow
                  open={open.has(regional.regional)}
                  onToggle={() => toggle(regional.regional)}
                  label={regionalLabel(regional.regional)}
                  hint={plural(regional.cities.length, "cidade", "cidades")}
                  depth={0}
                  item={regional}
                  compare={compare}
                />
                {open.has(regional.regional) ? (
                  <ul className="border-t border-slate-100 bg-slate-50/40">
                    {regional.cities.map((city) => {
                      const cityKey = `${regional.regional}|${city.city}`;
                      return (
                        <li key={cityKey}>
                          <ToggleRow
                            open={open.has(cityKey)}
                            onToggle={() => toggle(cityKey)}
                            label={city.city}
                            hint={plural(city.neighborhoods.length, "bairro", "bairros")}
                            depth={1}
                            item={city}
                            compare={compare}
                          />
                          {open.has(cityKey) ? (
                            <ul className="bg-white/70">
                              {city.neighborhoods.map((hood) => {
                                const hoodKey = `${cityKey}|${hood.neighborhood}`;
                                return (
                                  <li key={hoodKey}>
                                    <ToggleRow
                                      open={open.has(hoodKey)}
                                      onToggle={() => toggle(hoodKey)}
                                      label={hood.neighborhood}
                                      depth={2}
                                      item={hood}
                                      compare={compare}
                                    />
                                    {open.has(hoodKey) && query ? (
                                      <NeighborhoodProtocols regional={regional.regional} city={city.city} neighborhood={hood.neighborhood} query={query} refreshKey={refreshKey} />
                                    ) : null}
                                  </li>
                                );
                              })}
                            </ul>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function topBy<T>(items: T[], value: (item: T) => number): T | null {
  return items.reduce<T | null>((best, item) => (best === null || value(item) > value(best) ? item : best), null);
}

/** Cartões com mini-gráfico e gráficos do recorte, no desenho dos Indicadores do Suporte. */
export function RadarDashboard({ data }: { data: SupportContactRadar }) {
  const isRange = data.mode === "range";
  const { totals, series, previous } = data;
  const points = series.points;
  const labels = useMemo(() => seriesLabels(points, series.bucket_minutes), [points, series.bucket_minutes]);
  const againstLabel = isRange ? "período anterior" : "média dos 7 dias";
  const delta = (current: number, before: number) => ({ value: percentChange(current, before), goodWhenUp: null, againstLabel });

  const overallCoverage = totals.coverage_pct ?? 0;
  const coverageSpark = points.map((point) => (point.contacts ? Math.round((point.located_contacts * 1000) / point.contacts) / 10 : overallCoverage));
  const channelSpark = (key: string) => points.map((point) => point.by_channel[key] ?? 0);
  const channelTotal = (key: string) => data.by_channel.find((item) => item.channel === key)?.contacts ?? 0;

  const regionals = data.regionals;
  const cities = regionals.flatMap((regional) => regional.cities.map((city) => ({ regional: regional.regional, city })));
  const topRegional = topBy(regionals, (item) => item.customers);
  const topCity = topBy(cities, (item) => item.city.customers);
  const hoodAlerts = regionals.flatMap((regional) => regional.cities.flatMap((city) => city.neighborhoods.filter((hood) => hood.elevated)));
  const cityAlerts = cities.filter((item) => item.city.elevated).length;
  const regionalAlerts = regionals.filter((regional) => regional.elevated).length;

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <KpiCard
          label="Contatos no recorte - OPA"
          value={number(totals.contacts)}
          tone="blue"
          large
          hint={data.by_channel.map((item) => `${CHANNEL_LABEL[item.channel] ?? item.channel} ${number(item.contacts)}`).join(" · ") || "Nenhum contato no período"}
          delta={delta(totals.contacts, previous.contacts)}
          spark={points.map((point) => point.contacts)}
          sparkLabels={labels}
          sparkFormat={number}
          sparkColor={SPARK_COLOR.blue}
        />
        <KpiCard
          label="Clientes localizados - IXC"
          value={number(totals.customers)}
          tone="emerald"
          large
          hint="clientes distintos, com cidade e bairro no cadastro"
          delta={delta(totals.customers, previous.customers)}
          spark={points.map((point) => point.customers)}
          sparkLabels={labels}
          sparkFormat={number}
          sparkColor={SPARK_COLOR.emerald}
        />
        <KpiCard
          label="Cobertura da localização"
          value={percent(totals.coverage_pct)}
          tone="violet"
          large
          hint={`${number(totals.located_contacts)} contatos localizados${previous.coverage_pct != null ? ` · ${isRange ? "período anterior" : "média dos 7 dias"} ${percent(previous.coverage_pct)}` : ""}`}
          spark={coverageSpark}
          sparkLabels={labels}
          sparkFormat={(value) => percent(value)}
          sparkColor={SPARK_COLOR.violet}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <KpiCard
          label="Regional mais acionada"
          value={topRegional ? regionalLabel(topRegional.regional) : "—"}
          tone="slate"
          hint={topRegional ? `${number(topRegional.customers)} clientes · ${number(topRegional.contacts)} contatos` : "Sem contatos localizados"}
          spark={[]}
          sparkColor={SPARK_COLOR.blue}
        />
        <KpiCard
          label="Cidade mais acionada"
          value={topCity ? topCity.city.city : "—"}
          tone="slate"
          hint={topCity ? `${regionalLabel(topCity.regional)} · ${number(topCity.city.customers)} clientes` : "Sem contatos localizados"}
          spark={[]}
          sparkColor={SPARK_COLOR.blue}
        />
        <KpiCard
          label="Bairros acima do usual"
          value={data.alerts_enabled ? number(hoodAlerts.length) : "—"}
          tone={!data.alerts_enabled ? "slate" : hoodAlerts.length ? "red" : "emerald"}
          hint={data.alerts_enabled ? `${number(cityAlerts)} cidades · ${number(regionalAlerts)} regionais acima do usual` : "alertas desligados: histórico ainda em carga"}
          spark={[]}
          sparkColor={SPARK_COLOR.red}
        />
        <KpiCard
          label="Não localizados"
          value={totals.coverage_pct == null && totals.unlocated_contacts === 0 ? "—" : number(totals.unlocated_contacts)}
          tone="amber"
          hint="sem cliente identificado no OPA"
          spark={points.map((point) => point.contacts - point.located_contacts)}
          sparkLabels={labels}
          sparkFormat={number}
          sparkColor={SPARK_COLOR.amber}
        />
        <KpiCard
          label="WhatsApp"
          value={number(channelTotal("whatsapp"))}
          tone="blue"
          hint="contatos por mensagem"
          spark={channelSpark("whatsapp")}
          sparkLabels={labels}
          sparkFormat={number}
          sparkColor={SPARK_COLOR.blue}
        />
        <KpiCard
          label="Ligação"
          value={number(channelTotal("pabx"))}
          tone="violet"
          hint="contatos por telefone (PABX)"
          spark={channelSpark("pabx")}
          sparkLabels={labels}
          sparkFormat={number}
          sparkColor={SPARK_COLOR.violet}
        />
      </div>
    </div>
  );
}

function initialQuery(): RadarQuery {
  return { mode: "window", windowMinutes: 60, dateFrom: daysAgoIso(0), dateTo: daysAgoIso(0), channel: "", departmentIds: [] };
}

export function ContactRadarPanel() {
  const [query, setQuery] = useState<RadarQuery>(initialQuery);
  const [departments, setDepartments] = useState<SupportOpaFilterOption[]>([]);
  const [data, setData] = useState<SupportContactRadar | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // A primeira consulta espera a lista de departamentos, para já sair com o padrão aplicado em vez de
  // consultar "todos" e refazer em seguida.
  const [filtersReady, setFiltersReady] = useState(false);

  const refresh = useCallback(() => setTick((current) => current + 1), []);
  const problem = rangeProblem(query);
  const live = query.mode === "window" || query.dateTo >= daysAgoIso(0);

  useEffect(() => {
    let cancelled = false;
    api
      .supportOpaFilters()
      .then((filters) => {
        if (cancelled) return;
        setDepartments(filters.departments);
        setQuery((current) => ({ ...current, departmentIds: defaultDepartmentIds(filters.departments) }));
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setFiltersReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!live) return undefined;
    const timer = window.setInterval(refresh, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [live, refresh]);

  useEffect(() => {
    if (problem || !filtersReady) return undefined;
    let cancelled = false;
    setLoading(true);
    api
      .supportContactRadar({
        window_minutes: query.windowMinutes,
        date_from: query.mode === "range" ? query.dateFrom : undefined,
        date_to: query.mode === "range" ? query.dateTo : undefined,
        channel: query.channel,
        department_ids: query.departmentIds,
      })
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar o Radar de Contatos. Tente novamente ou contate o administrador.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, problem, filtersReady, tick]);

  return (
    <ContactRadarView
      data={data}
      loading={loading && !problem}
      error={error}
      problem={problem}
      query={query}
      departments={departments}
      onQueryChange={(patch) => setQuery((current) => ({ ...current, ...patch }))}
      onRefresh={refresh}
    />
  );
}

type ViewProps = {
  data: SupportContactRadar | null;
  loading: boolean;
  error: string | null;
  problem?: string | null;
  query: RadarQuery;
  departments: SupportOpaFilterOption[];
  onQueryChange: (patch: Partial<RadarQuery>) => void;
  onRefresh: () => void;
};

export function ContactRadarView({ data, loading, error, problem = null, query, departments, onQueryChange, onRefresh }: ViewProps) {
  const regionals = data?.regionals ?? [];
  // O aviso lista o recorte mais fino que passou do usual: bairros; se nenhum bairro passou, cidades; depois regionais.
  const hoods = regionals.flatMap((regional) => regional.cities.flatMap((city) => city.neighborhoods.filter((hood) => hood.elevated).map((hood) => ({ label: `${hood.neighborhood} (${city.city})`, item: hood }))));
  const cityAlerts = regionals.flatMap((regional) => regional.cities.filter((city) => city.elevated).map((city) => ({ label: city.city, item: city })));
  const regionalAlerts = regionals.filter((regional) => regional.elevated).map((regional) => ({ label: regionalLabel(regional.regional), item: regional }));
  const alerts = !data?.alerts_enabled ? [] : hoods.length ? hoods : cityAlerts.length ? cityAlerts : regionalAlerts;
  const alertKind = hoods.length ? ["bairro", "bairros"] : cityAlerts.length ? ["cidade", "cidades"] : ["regional", "regionais"];
  const totals = data?.totals;
  const isRange = data?.mode === "range";
  const baselineLabel = isRange ? "Período anterior" : "Habitual";
  const baselineHint = isRange
    ? "Clientes no período imediatamente anterior, de mesmo tamanho"
    : "Média de clientes na mesma janela dos 7 dias anteriores";
  const activePreset = PRESETS.find((preset) => {
    const range = preset.range();
    return range.dateFrom === query.dateFrom && range.dateTo === query.dateTo;
  })?.key;

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid grid-cols-1 gap-3 rounded-2xl bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <div className="mr-auto flex items-center gap-2">
            <Radar size={20} className="text-sky-600" aria-hidden="true" />
            <div>
              <h2 className="text-base font-semibold text-slate-950">Radar de Contatos</h2>
              <p className="text-xs text-slate-500">
                De onde os clientes estão entrando em contato pelo OPA, por cliente distinto.
                {query.mode === "window" || query.dateTo >= daysAgoIso(0) ? " Atualiza a cada minuto." : ""}
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1 text-xs font-medium text-slate-600">
            Período
            <div className="flex flex-wrap rounded-lg border border-slate-200 bg-slate-50 p-1" role="group" aria-label="Período">
              <button
                type="button"
                aria-pressed={query.mode === "window"}
                onClick={() => onQueryChange({ mode: "window" })}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${query.mode === "window" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Ao vivo
              </button>
              {PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  aria-pressed={query.mode === "range" && activePreset === preset.key}
                  onClick={() => onQueryChange({ mode: "range", ...preset.range() })}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${query.mode === "range" && activePreset === preset.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
          {query.mode === "window" ? (
            <label className="grid gap-1 text-xs font-medium text-slate-600">
              Janela
              <Select value={query.windowMinutes} onChange={(event) => onQueryChange({ windowMinutes: Number(event.target.value) })}>
                {WINDOWS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </Select>
            </label>
          ) : null}
          {/* O filtro por data fica sempre à vista; mexer numa data passa a consulta para "por período". */}
          <label className="grid gap-1 text-xs font-medium text-slate-600">
            <span className="flex items-center gap-1"><CalendarDays size={12} aria-hidden="true" /> De</span>
            <input
              type="date"
              value={query.dateFrom}
              max={query.dateTo || undefined}
              onChange={(event) => onQueryChange({ mode: "range", dateFrom: event.target.value })}
              className={`h-10 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700 ${query.mode === "window" ? "opacity-70" : ""}`}
            />
          </label>
          <label className="grid gap-1 text-xs font-medium text-slate-600">
            Até
            <input
              type="date"
              value={query.dateTo}
              min={query.dateFrom || undefined}
              onChange={(event) => onQueryChange({ mode: "range", dateTo: event.target.value })}
              className={`h-10 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700 ${query.mode === "window" ? "opacity-70" : ""}`}
            />
          </label>
          <div className="grid gap-1 text-xs font-medium text-slate-600">
            Departamentos
            <MultiSelect<SupportOpaFilterOption>
              className="h-10 w-60 text-sm"
              values={query.departmentIds}
              options={departments}
              getValue={(option) => option.value}
              formatOption={(option) => option.label}
              placeholder="Todos os departamentos"
              ariaLabel="Departamentos do OPA"
              onChange={(next) => onQueryChange({ departmentIds: next })}
            />
          </div>
          <label className="grid gap-1 text-xs font-medium text-slate-600">
            Canal
            <Select value={query.channel} onChange={(event) => onQueryChange({ channel: event.target.value })}>
              {CHANNELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </Select>
          </label>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading || Boolean(problem)} aria-label="Atualizar agora">
            {loading ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <RefreshCw size={14} aria-hidden="true" />}
            Atualizar
          </Button>
        </div>
        {problem ? <p className="text-xs font-medium text-rose-700" role="alert">{problem}</p> : null}
      </div>

      {error ? (
        <div className="flex items-center gap-3 rounded-2xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
          <AlertCircle size={20} aria-hidden="true" />
          <p className="mr-auto">{error}</p>
          <Button variant="outline" size="sm" onClick={onRefresh}>Tentar novamente</Button>
        </div>
      ) : null}

      {loading && !data ? (
        <div className="flex items-center gap-2 rounded-2xl bg-white p-6 text-sm text-slate-500 shadow-sm" role="status">
          <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Carregando o radar…
        </div>
      ) : null}

      {data && totals ? (
        <>
          <RadarDashboard data={data} />

          {!data.alerts_enabled ? (
            <div className="rounded-2xl bg-amber-50 p-4 text-sm text-amber-900" role="status">
              Alertas de volume desligados por enquanto: a localização dos clientes do período de comparação ainda está sendo resolvida, e a comparação com o {isRange ? "período anterior" : "habitual"} ficaria distorcida.
            </div>
          ) : null}

          {alerts.length ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" role="status">
              <p className="flex items-center gap-2 font-semibold">
                <TriangleAlert size={16} aria-hidden="true" /> {alerts.length === 1 ? `1 ${alertKind[0]} com volume acima do usual` : `${alerts.length} ${alertKind[1]} com volume acima do usual`}
              </p>
              <p className="mt-1">
                {alerts.slice(0, 6).map(({ label, item }) => `${label}: ${item.customers} clientes, ${isRange ? "período anterior" : "habitual"} ${decimal(item.baseline)}`).join(" · ")}
              </p>
            </div>
          ) : null}

          {regionals.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-2xl bg-white p-10 text-center shadow-sm">
              <MapPinned size={28} className="text-slate-400" aria-hidden="true" />
              <p className="text-sm font-medium text-slate-700">Nenhum contato localizado neste recorte.</p>
              <p className="max-w-md text-xs text-slate-500">
                A localização vem do cadastro do cliente no IXC e é resolvida aos poucos para clientes novos. Contatos sem cliente identificado no OPA não aparecem aqui.
              </p>
            </div>
          ) : (
            <RegionalTree regionals={regionals} query={query} refreshKey={data.generated_at} compare={data.alerts_enabled} baselineLabel={baselineLabel} baselineHint={baselineHint} />
          )}
        </>
      ) : null}
    </div>
  );
}
