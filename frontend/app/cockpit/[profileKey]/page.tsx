"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { MapPinned, Moon, Sun } from "lucide-react";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { buildBacklogChartOption, buildProductionChartOption, buildSlaChartOption } from "@/lib/cockpit-chart-options";
import { configuredCockpitWidgetSize, type CockpitWidgetSize } from "@/lib/intelligence-cockpit-layout";
import { SEVERITY_LABELS, SOURCE_TYPE_LABELS, STATUS_WORD_LABELS, labelFor } from "@/lib/intelligence-labels";
import { type Tone } from "@/lib/tones";
import { cn } from "@/lib/utils";
import {
  intelligenceCockpitApi,
  type CockpitAlertSummary,
  type CockpitContent,
  type CockpitPayload
} from "@/lib/intelligence-cockpit-api";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-[130px] animate-pulse rounded-lg bg-slate-100" aria-label="Carregando gráfico" />
});

// Mesmo padrão de "barra de acento de 4px no topo do card" já usado em
// operations-openings-analytics.tsx::MetricCard - cor comunica status sem pintar o card inteiro.
// Vermelho reservado só para CRITICAL (severidade real), nunca como moldura estrutural padrão.
// Rótulos vêm de lib/intelligence-labels.ts (nunca duplicados aqui) - só o estilo visual
// (tom/acento/maiúsculas do badge) é próprio desta tela.
const STATUS_META: Record<CockpitPayload["overall_status"]["status"], { label: string; tone: Tone; accent: string }> = {
  NORMAL: { label: labelFor(STATUS_WORD_LABELS, "NORMAL").toUpperCase(), tone: "emerald", accent: "bg-emerald-500" },
  ATTENTION: { label: labelFor(STATUS_WORD_LABELS, "ATTENTION").toUpperCase(), tone: "amber", accent: "bg-amber-500" },
  RISK: { label: labelFor(STATUS_WORD_LABELS, "RISK").toUpperCase(), tone: "amber", accent: "bg-amber-600" },
  CRITICAL: { label: labelFor(STATUS_WORD_LABELS, "CRITICAL").toUpperCase(), tone: "red", accent: "bg-red-600" }
};

// Regra explícita (ajuste visual pedido pelo usuário): CRÍTICA = vermelho, ALTA = âmbar,
// MÉDIA/BAIXA = neutro. Cor nunca pinta o card inteiro - só um indicador pequeno (ver
// SeverityDot/DOT_COLOR_CLASS abaixo) - "excesso de vermelho" incluía MEDIUM usando âmbar antes.
const SEVERITY_TONE: Record<string, Tone> = { CRITICAL: "red", HIGH: "amber", MEDIUM: "slate", LOW: "slate", INFO: "blue" };
const SEVERITY_LABEL = SEVERITY_LABELS;
const DOT_COLOR_CLASS: Record<Tone, string> = {
  red: "bg-red-500",
  amber: "bg-amber-500",
  emerald: "bg-emerald-500",
  blue: "bg-blue-500",
  violet: "bg-violet-500",
  slate: "bg-slate-400"
};
const LEFT_BORDER_CLASS: Record<Tone, string> = {
  red: "border-l-red-500",
  amber: "border-l-amber-500",
  emerald: "border-l-emerald-500",
  blue: "border-l-blue-500",
  violet: "border-l-violet-500",
  slate: "border-l-slate-300"
};

// IA aparece como ANÁLISE (violeta, mesmo tom de "revisão/análise" já usado em scoringStatusTone),
// nunca como se fosse dado medido - distinta de gestão (azul da marca) e sistema/monitor (neutros).
// Rótulo vem de SOURCE_TYPE_LABELS; tom/legenda são próprios desta tela.
const SOURCE_META: Record<string, { label: string; tone: Tone; caption: string }> = {
  AI: { label: labelFor(SOURCE_TYPE_LABELS, "AI").toUpperCase(), tone: "violet", caption: "Análise gerada por IA" },
  MCP: { label: labelFor(SOURCE_TYPE_LABELS, "MCP").toUpperCase(), tone: "violet", caption: "Análise gerada por IA" },
  USER: { label: labelFor(SOURCE_TYPE_LABELS, "USER").toUpperCase(), tone: "blue", caption: "Publicado pela gestão" },
  SYSTEM: { label: labelFor(SOURCE_TYPE_LABELS, "SYSTEM").toUpperCase(), tone: "slate", caption: "Gerado pelo sistema" },
  MONITOR: { label: labelFor(SOURCE_TYPE_LABELS, "MONITOR").toUpperCase(), tone: "amber", caption: "Detectado por monitor" }
};

// Painel de destaque compartilhado entre o problema principal e a publicação da UNI Intelligence
// em foco - a cor do painel segue o tom da fonte/severidade, nunca vermelho como moldura padrão.
const SPOTLIGHT_PANEL_CLASS: Record<Tone, string> = {
  red: "border-red-200 bg-red-50/70",
  amber: "border-amber-200 bg-amber-50/70",
  emerald: "border-emerald-200 bg-emerald-50/70",
  blue: "border-blue-200 bg-blue-50/70",
  violet: "border-violet-200 bg-violet-50/70",
  slate: "border-slate-200 bg-slate-50"
};

function formatAge(seconds: number): string {
  if (seconds < 60) return "agora";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min atrás`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h atrás`;
  return `${Math.floor(hours / 24)}d atrás`;
}

function formatClock(iso: string | null): string {
  if (!iso) return "--:--";
  return new Date(iso).toLocaleTimeString("pt-BR", { timeZone: "America/Porto_Velho", hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "Horário não informado";
  return new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Porto_Velho", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR").format(value);
}

function widgetEnabled(payload: CockpitPayload, key: string): boolean {
  return payload.profile.widgets.includes(key);
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

// Evidência curta para ler o alerta sem abrir - só monta a partir de campos REAIS de
// `evidence`/`payload` (nunca inventa dado); cai para um recorte do `summary` já gerado pelo
// monitor quando o alert_type não tem um formato dedicado ou os campos esperados não vieram.
function evidenceLine(item: CockpitAlertSummary, slaTarget: number): string {
  const ev = item.evidence ?? {};
  const count = asNumber(ev.cluster_size) ?? asNumber(ev.os_count);
  const radius = asNumber(ev.radius_meters);
  const window = asNumber(ev.window_minutes);

  switch (item.alert_type) {
    case "COLLECTIVE_OUTAGE":
      if (count !== null && radius !== null && window !== null) {
        return `${count} logins offline · ${Math.round(radius)} m · últimos ${window} min`;
      }
      break;
    case "OS_CONCENTRATION_AREA":
    case "OS_CONCENTRATION_LINEAR":
      if (count !== null && radius !== null && window !== null) {
        return `${count} O.S. · raio ${Math.round(radius)} m · ${window} min`;
      }
      break;
    case "SLA_DETERIORATION": {
      const recent = asNumber(ev.sla_recent_pct);
      const drop = asNumber(ev.drop_percentage_points);
      if (recent !== null && drop !== null) {
        return `SLA ${recent}% · meta ${slaTarget}% · queda de ${drop} p.p.`;
      }
      break;
    }
    case "OPERATIONAL_PRESSURE": {
      const deviation = asNumber(ev.deviation_percentage);
      const backlog = asNumber(ev.backlog);
      const parts: string[] = [];
      if (deviation !== null) parts.push(`entrada ${deviation > 0 ? "+" : ""}${Math.round(deviation)}% vs média`);
      if (backlog !== null) parts.push(`backlog ${backlog}`);
      if (parts.length) return parts.join(" · ");
      break;
    }
    case "OS_OPENING_ABOVE_AVERAGE":
    case "OS_GROWTH_ANOMALY": {
      const openedCount = asNumber(ev.count);
      const average = asNumber(ev.baseline_average);
      if (openedCount !== null && window !== null) {
        return `${openedCount} O.S. em ${window} min` + (average !== null && average > 0 ? ` · média ${average.toFixed(1)}` : "");
      }
      break;
    }
    case "BACKLOG_THRESHOLD": {
      const total = asNumber(ev.backlog_total);
      const threshold = asNumber(ev.threshold);
      if (total !== null) return `${total} O.S. em aberto` + (threshold !== null ? ` · limite ${threshold}` : "");
      break;
    }
    case "SLA_THRESHOLD": {
      const rate = asNumber(ev.sla_rate);
      const threshold = asNumber(ev.threshold);
      if (rate !== null) return `SLA ${rate}%` + (threshold !== null ? ` · limite ${threshold}%` : "");
      break;
    }
    case "MONITOR_UNHEALTHY": {
      const failures = asNumber(ev.consecutive_failures);
      const threshold = asNumber(ev.threshold);
      if (failures !== null) return `${failures} falhas seguidas` + (threshold !== null ? ` · limite ${threshold}` : "");
      break;
    }
  }
  // Melhor resumo disponível (já escrito pelo próprio monitor) - nunca deixa o card sem nenhuma
  // evidência só porque o formato dedicado não bateu.
  return item.summary.length > 96 ? `${item.summary.slice(0, 93)}...` : item.summary;
}

// Localização legível sem abrir o detalhe (pedido explícito: "mostrar qual rua e ter as
// coordenadas em cada linha desses alertas"). Rua vem do primeiro endereço da amostra real de O.S.
// (evidence.os_sample) quando existir; coordenadas vêm do centro do agrupamento já calculado pelo
// monitor (evidence.center_latitude/longitude) - nunca inventa dado que não veio na evidência.
function locationLine(item: CockpitAlertSummary): string | null {
  const ev = item.evidence ?? {};
  const sample = Array.isArray(ev.os_sample) ? (ev.os_sample as Array<Record<string, unknown>>) : [];
  const address = typeof sample[0]?.address === "string" ? (sample[0].address as string) : null;
  const lat = asNumber(ev.center_latitude);
  const lng = asNumber(ev.center_longitude);
  const coords = lat !== null && lng !== null ? `${lat.toFixed(5)}, ${lng.toFixed(5)}` : null;
  if (address && coords) return `${address} · ${coords}`;
  if (address) return address;
  if (coords) return coords;
  return null;
}

type OrderSample = { order_code: string; address: string | null; neighborhood: string | null; latitude: number | null; longitude: number | null; opened_at: string | null };

function orderSamples(item: CockpitAlertSummary): OrderSample[] {
  const raw = Array.isArray(item.evidence?.os_sample) ? item.evidence.os_sample : [];
  return raw.flatMap((value) => {
    if (!value || typeof value !== "object") return [];
    const sample = value as Record<string, unknown>;
    const orderCode = typeof sample.order_code === "string" ? sample.order_code : null;
    if (!orderCode) return [];
    return [{
      order_code: orderCode,
      address: typeof sample.address === "string" ? sample.address : null,
      neighborhood: typeof sample.neighborhood === "string" ? sample.neighborhood : null,
      latitude: asNumber(sample.latitude),
      longitude: asNumber(sample.longitude),
      opened_at: typeof sample.opened_at === "string" ? sample.opened_at : null,
    }];
  });
}

function SeverityDot({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500" title={label}>
      <span className={cn("h-1.5 w-1.5 rounded-full", DOT_COLOR_CLASS[tone])} />
      {label}
    </span>
  );
}

// Mesmo padrão neutro do Operação Analítica (operations-control-tower.tsx::SummaryMetric): valor
// SEMPRE neutro (slate-950) por padrão - cor só entra quando o número em si é um problema real
// (ex.: saldo positivo, SLA abaixo da meta), nunca "decoração" por métrica (achado do ajuste
// visual: a TV tinha um arco-íris de azul/verde/âmbar sem relação com bom/ruim).
function KpiCard({ label, value, suffix, tone = "slate" }: { label: string; value: number | null; suffix?: string; tone?: Tone }) {
  const TONE_TEXT: Record<Tone, string> = {
    emerald: "text-emerald-700",
    amber: "text-amber-700",
    red: "text-red-600",
    blue: "text-blue-700",
    violet: "text-violet-700",
    slate: "text-slate-950"
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-center shadow-sm">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className={cn("mt-1 text-4xl font-bold tabular-nums", TONE_TEXT[tone])}>
        {formatNumber(value)}
        {value !== null && suffix ? suffix : ""}
      </p>
    </div>
  );
}

// Spotlight = a publicação/insight mais recente da UNI Intelligence, sempre em destaque na área
// editorial principal da TV (requisito F5: IA deixa de ser rodapé e vira a área central).
function IntelligenceSpotlight({ item }: { item: CockpitContent }) {
  const source = SOURCE_META[item.source_type] ?? SOURCE_META.SYSTEM;
  const tone = item.severity !== "INFO" ? SEVERITY_TONE[item.severity] ?? "blue" : source.tone;
  return (
    <div className={cn("cockpit-spotlight rounded-2xl border p-5", SPOTLIGHT_PANEL_CLASS[tone])}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={source.tone}>{source.label}</StatusBadge>
        {item.severity !== "INFO" && <StatusBadge tone={SEVERITY_TONE[item.severity] ?? "slate"}>{SEVERITY_LABEL[item.severity] ?? item.severity}</StatusBadge>}
        <span className="text-[11px] italic text-slate-500">{source.caption}</span>
        {item.confidence !== null && (
          <span className="ml-auto text-[11px] font-medium text-slate-500">confiança {Math.round(item.confidence * 100)}%</span>
        )}
      </div>
      <h3 className="mt-2 text-2xl font-semibold text-slate-950">{item.title}</h3>
      <p className="mt-2 whitespace-pre-line text-base leading-6 text-slate-700">{item.body}</p>
    </div>
  );
}

function ContentCard({ item }: { item: CockpitContent }) {
  const source = SOURCE_META[item.source_type] ?? SOURCE_META.SYSTEM;
  const severityTone = SEVERITY_TONE[item.severity] ?? "blue";
  return (
    <div className="w-full rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <StatusBadge tone={source.tone}>{source.label}</StatusBadge>
        {item.severity !== "INFO" && <StatusBadge tone={severityTone}>{SEVERITY_LABEL[item.severity] ?? item.severity}</StatusBadge>}
      </div>
      <p className="mt-1.5 text-[10px] italic text-slate-400">{source.caption}</p>
      <h4 className="mt-1 text-sm font-semibold text-slate-950">{item.title}</h4>
      <p className="mt-1 line-clamp-3 text-sm text-slate-600">{item.body}</p>
    </div>
  );
}

// Alerta principal: leve destaque (borda colorida à esquerda), nunca fundo colorido grande -
// severidade fica discreta (SeverityDot), o conteúdo (título + evidência) é o que ocupa espaço.
function RecentAlertCard({ item, slaTarget, showOsDetails = true, showCoordinates = true, showRecommendations = true, compact = false }: { item: CockpitAlertSummary; slaTarget: number; showOsDetails?: boolean; showCoordinates?: boolean; showRecommendations?: boolean; compact?: boolean }) {
  const tone = SEVERITY_TONE[item.severity] ?? "slate";
  const samples = orderSamples(item).slice(0, 3);
  const location = locationLine(item);
  const regional = [item.regional, item.city].filter(Boolean).join(" · ");
  return (
    <article className={cn("rounded-xl border border-slate-200 border-l-4 bg-white", compact ? "p-2.5" : "p-3", LEFT_BORDER_CLASS[tone])}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{labelFor(STATUS_WORD_LABELS, item.kind)}</span>
        <SeverityDot tone={tone} label={labelFor(SEVERITY_LABEL, item.severity)} />
        {regional && <span className="text-[11px] text-slate-500">{regional}</span>}
        <span className="ml-auto text-[11px] text-slate-400">{formatAge(item.age_seconds)}</span>
      </div>
      <h3 className="mt-1.5 text-base font-semibold text-slate-950">{item.title}</h3>
      <p className="mt-1 text-sm font-medium text-slate-700">{evidenceLine(item, slaTarget)}</p>
      {showCoordinates && location && (
        <p className="mt-1 flex items-start gap-1.5 text-xs text-slate-500">
          <MapPinned className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{location}</span>
        </p>
      )}
      {showOsDetails && samples.length > 0 && (
        <ul className="cockpit-soft-panel mt-2 divide-y divide-slate-100 rounded-lg border border-slate-100 bg-slate-50/70 px-2">
          {samples.map((sample) => (
            <li key={sample.order_code} className="py-1.5 text-xs text-slate-600">
              <span className="font-semibold text-slate-800">O.S. {sample.order_code}</span>
              <span className="text-slate-500"> · aberta em {formatDateTime(sample.opened_at)}</span>
              {(sample.address || sample.neighborhood) && <span> · {sample.address ?? sample.neighborhood}</span>}
              {sample.latitude !== null && sample.longitude !== null && <span className="text-slate-400"> · {sample.latitude.toFixed(5)}, {sample.longitude.toFixed(5)}</span>}
            </li>
          ))}
        </ul>
      )}
      {showRecommendations && item.recommended_action && (
        <p className="mt-1 text-xs font-medium text-slate-600">Ação recomendada: {item.recommended_action}</p>
      )}
    </article>
  );
}

const MOSAIC_SPAN: Record<CockpitWidgetSize, string> = {
  S: "col-span-12 md:col-span-6 xl:col-span-3",
  M: "col-span-12 md:col-span-6 xl:col-span-4",
  L: "col-span-12 xl:col-span-8",
  XL: "col-span-12",
};

function widgetSpan(config: Record<string, unknown>, key: string): string {
  return MOSAIC_SPAN[configuredCockpitWidgetSize(config, key)];
}

function widgetOrder(payload: CockpitPayload, key: string, offset = 0): number {
  const index = payload.profile.widgets.indexOf(key);
  return (index < 0 ? payload.profile.widgets.length : index) * 10 + offset;
}

function MiniChart({ title, option, className, order }: { title: string; option: EChartsOption; className?: string; order?: number }) {
  return (
    <div className={cn("min-w-0 rounded-xl border border-slate-200 bg-white p-3 shadow-sm", className)} style={{ order }}>
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{title}</p>
      <ReactECharts option={option} notMerge lazyUpdate opts={{ renderer: "canvas" }} style={{ height: 130, width: "100%" }} />
    </div>
  );
}

export default function CockpitPage() {
  const params = useParams<{ profileKey: string }>();
  const profileKey = params.profileKey;
  const { user, checking, error: authError, login } = useWorkspaceAuth();

  const [payload, setPayload] = useState<CockpitPayload | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const requestRef = useRef(0);
  const secondaryPanelRef = useRef<HTMLDivElement | null>(null);

  const canRead = Boolean(user?.permissions.includes("intelligence:read"));

  useEffect(() => {
    if (!user || !canRead) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      const requestId = ++requestRef.current;
      try {
        const data = await intelligenceCockpitApi.getCockpit(profileKey);
        if (cancelled || requestId !== requestRef.current) return;
        setPayload(data);
        setFetchError(null);
        setLastUpdatedAt(new Date());
        timer = setTimeout(tick, Math.max(data.profile.refresh_seconds, 15) * 1000);
      } catch (reason) {
        if (cancelled || requestId !== requestRef.current) return;
        const message = reason instanceof Error ? reason.message : "Falha ao atualizar o cockpit.";
        setFetchError(message);
        // Mantém o último payload válido na tela - nunca zera fingindo operação normal.
        timer = setTimeout(tick, 30_000);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [user, canRead, profileKey]);

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("uni-cockpit-theme-v2");
    if (storedTheme === "light" || storedTheme === "dark") {
      setTheme(storedTheme);
      return;
    }
    const configured = String(payload?.profile.display_config.theme ?? "LIGHT");
    if (configured === "DARK" || (configured === "AUTO" && window.matchMedia("(prefers-color-scheme: dark)").matches)) setTheme("dark");
    else setTheme("light");
  }, [payload?.profile.display_config.theme]);

  function setCockpitTheme(next: "light" | "dark") {
    setTheme(next);
    window.localStorage.setItem("uni-cockpit-theme-v2", next);
  }

  useEffect(() => {
    const seconds = Number(payload?.profile.display_config.rotate_seconds ?? 0);
    if (seconds <= 0) return;
    const timer = window.setInterval(() => {
      const panel = secondaryPanelRef.current;
      if (!panel) return;
      const nearBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 12;
      panel.scrollTo({ top: nearBottom ? 0 : panel.scrollTop + Math.max(panel.clientHeight * 0.8, 280), behavior: "smooth" });
    }, Math.max(seconds, 10) * 1000);
    return () => window.clearInterval(timer);
  }, [payload?.profile.display_config.rotate_seconds]);

  const sortedProblems = useMemo(() => {
    if (!payload) return [];
    const rank: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    const sortMode = String(payload.profile.display_config.alert_sort ?? "RECENT");
    const impact = (item: CockpitAlertSummary) => asNumber(item.evidence.cluster_size) ?? asNumber(item.evidence.os_count) ?? asNumber(item.evidence.count) ?? 0;
    const rows = [...payload.incidents, ...payload.alerts];
    rows.sort((a, b) => {
      if (sortMode === "SEVERITY") return (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9) || new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
      if (sortMode === "IMPACT") return impact(b) - impact(a) || (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9);
      return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime() || (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9);
    });
    const limit = [4, 6, 8, 12].includes(Number(payload.profile.display_config.alert_limit)) ? Number(payload.profile.display_config.alert_limit) : 4;
    return rows.slice(0, limit);
  }, [payload]);

  if (checking && !user) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">Carregando UNI Workspace...</main>;
  }
  if (!user) {
    return <WorkspaceLogin isLoading={checking} error={authError} onLogin={login} />;
  }
  if (!canRead) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-8 text-center text-slate-600">
        Acesso não autorizado — seu perfil não possui a permissão intelligence:read.
      </main>
    );
  }
  if (!payload) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        {fetchError ? `Não foi possível carregar o cockpit: ${fetchError}` : "Carregando cockpit..."}
      </main>
    );
  }

  const status = STATUS_META[payload.overall_status.status];
  const healthyCount = payload.monitor_health.filter((m) => m.enabled && m.consecutive_failures === 0).length;

  const showProblems = widgetEnabled(payload, "active_alerts") || widgetEnabled(payload, "active_incidents");
  const showOverall = widgetEnabled(payload, "overall_status");
  const showProduction = widgetEnabled(payload, "production");
  const showBacklog = widgetEnabled(payload, "backlog");
  const showSla = widgetEnabled(payload, "sla");
  const showMonitorHealth = widgetEnabled(payload, "monitor_health");
  const showContent = widgetEnabled(payload, "cockpit_content") || widgetEnabled(payload, "ai_insights");
  const contentWidgetKey = payload.profile.widgets.find((key) => key === "ai_insights" || key === "cockpit_content") ?? "cockpit_content";
  const problemsWidgetKey = payload.profile.widgets.find((key) => key === "active_incidents" || key === "active_alerts") ?? "active_alerts";

  const [featuredContent, ...restContent] = payload.content;

  const productionPoints = payload.charts.production_7d;
  const slaPoints = payload.charts.sla_7d;
  const backlogPoints = payload.charts.backlog_7d;
  const showProductionChart = showProduction && productionPoints.length > 0;
  const showSlaChart = showSla && slaPoints.length > 0;
  const showBacklogChart = showBacklog && backlogPoints.length > 0;
  const showCharts = showProductionChart || showSlaChart || showBacklogChart;
  const displayConfig = payload.profile.display_config;
  const compactAlerts = displayConfig.density === "COMPACT";
  const showOsDetails = displayConfig.show_os_details !== false;
  const showCoordinates = displayConfig.show_coordinates !== false;
  const showRecommendations = displayConfig.show_recommendations !== false;

  return (
    <main className={cn("flex h-screen w-screen flex-col overflow-hidden", displayConfig.density === "COMPACT" ? "p-3" : displayConfig.density === "TV" ? "p-6" : "p-5", theme === "dark" ? "cockpit-theme-dark bg-[#101216] text-slate-100" : "bg-slate-50 text-slate-900")}>
      {/* TOPO: profile, freshness, saúde dos monitores - sem badge de status geral (o estado já
          fica claro pela área de Problemas agora e pelos indicadores, ajuste visual pedido). */}
      <header className="relative flex flex-shrink-0 items-center justify-between overflow-hidden rounded-2xl border border-slate-200 bg-white px-6 py-4 shadow-sm">
        <span className={cn("absolute inset-x-0 top-0 h-1", status.accent)} />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-uni-royal">UNI Internet</p>
          <h1 className="text-2xl font-bold text-slate-950">Operação Agora</h1>
          <p className="text-xs text-slate-500">
            {payload.profile.name} · atualizado às {formatClock(lastUpdatedAt?.toISOString() ?? payload.generated_at)} · monitores saudáveis {healthyCount}/
            {payload.monitor_health.length}
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-slate-200 p-1" aria-label="Tema do cockpit">
          <button
            type="button"
            onClick={() => setCockpitTheme("light")}
            className={cn("inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium", theme === "light" ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-700")}
            aria-pressed={theme === "light"}
          >
            <Sun className="h-3.5 w-3.5" aria-hidden="true" />
            Claro
          </button>
          <button
            type="button"
            onClick={() => setCockpitTheme("dark")}
            className={cn("inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium", theme === "dark" ? "bg-slate-800 text-white" : "text-slate-500 hover:text-slate-700")}
            aria-pressed={theme === "dark"}
          >
            <Moon className="h-3.5 w-3.5" aria-hidden="true" />
            Escuro
          </button>
        </div>
      </header>

      {fetchError && (
        <div className="mt-2 flex-shrink-0 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800">
          Atualização falhou — mostrando o último dado válido ({formatClock(lastUpdatedAt?.toISOString() ?? null)}). {fetchError}
        </div>
      )}

      {/* Mosaico responsivo: a ordem vem do profile e os tamanhos ficam em display_config. */}
      <div ref={secondaryPanelRef} className="mt-4 grid min-h-0 flex-1 grid-flow-dense auto-rows-max grid-cols-12 gap-4 overflow-y-auto pr-1">
        {/* PRINCIPAL: UNI Intelligence - a análise, não apenas o dado bruto */}
        {showContent && (
          <SectionCard
            eyebrow="UNI Intelligence"
            title="Análise e prioridades"
            className={cn("self-start", widgetSpan(displayConfig, contentWidgetKey))}
            contentClassName="min-h-0"
            style={{ order: widgetOrder(payload, contentWidgetKey) }}
          >
            {payload.content.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center text-center">
                <p className="text-4xl">🧠</p>
                <p className="mt-2 text-lg font-semibold text-slate-700">Nenhuma publicação no momento</p>
                <p className="text-sm text-slate-500">A próxima análise da UNI Intelligence aparecerá aqui.</p>
              </div>
            ) : (
              <div className="grid gap-3">
                {featuredContent && <IntelligenceSpotlight item={featuredContent} />}
                {restContent.length > 0 && (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {restContent.map((item) => (
                      <ContentCard key={item.id} item={item} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </SectionCard>
        )}

        {/* SECUNDÁRIO + SUPORTE: KPIs, tendências, incidentes compactos, saúde dos monitores */}
        <section className="contents">
          {showOverall && <div className={cn("grid grid-cols-2 gap-3 self-start", widgetSpan(displayConfig, "overall_status"), configuredCockpitWidgetSize(displayConfig, "overall_status") !== "M" && "xl:grid-cols-5")} style={{ order: widgetOrder(payload, "overall_status") }}>
            <KpiCard label="Abertas" value={payload.production.opened_today} />
            <KpiCard label="Finalizadas" value={payload.production.closed_today} />
            {/* Saldo positivo (abriu mais do que fechou) é o único sinal de problema real aqui -
                mesma semântica de operations-control-tower.tsx (net_flow > 0 = vermelho). */}
            <KpiCard label="Saldo" value={payload.production.balance_today} tone={payload.production.balance_today > 0 ? "red" : "slate"} />
            <KpiCard label="Backlog" value={payload.backlog.total} />
            <KpiCard
              label="SLA"
              value={payload.sla.current !== null ? Math.round(payload.sla.current) : null}
              suffix="%"
              tone={payload.sla.current !== null && payload.sla.current < payload.sla.target ? "red" : "slate"}
            />
          </div>}

          {(showBacklog || showSla) && (
            <div className="contents">
              {showBacklog && (
                <SectionCard eyebrow="Backlog" title="Por idade" className={cn("self-start shadow-sm", widgetSpan(displayConfig, "backlog"))} style={{ order: widgetOrder(payload, "backlog") }}>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-xl font-bold text-slate-900">{formatNumber(payload.backlog.gt_3d)}</p>
                      <p className="text-[10px] text-slate-500">&gt; 3 dias</p>
                    </div>
                    <div>
                      <p className="text-xl font-bold text-amber-700">{formatNumber(payload.backlog.gt_7d)}</p>
                      <p className="text-[10px] text-slate-500">&gt; 7 dias</p>
                    </div>
                    <div>
                      <p className="text-xl font-bold text-red-700">{formatNumber(payload.backlog.gt_15d)}</p>
                      <p className="text-[10px] text-slate-500">&gt; 15 dias</p>
                    </div>
                  </div>
                </SectionCard>
              )}

              {showSla && (
                <SectionCard eyebrow="SLA" title="Regionais críticas" subtitle={`meta ${payload.sla.target}%`} className={cn("self-start shadow-sm", widgetSpan(displayConfig, "sla"))} style={{ order: widgetOrder(payload, "sla") }}>
                  {payload.sla.critical_regionals.length === 0 ? (
                    <p className="text-sm text-slate-500">Nenhuma regional abaixo da meta.</p>
                  ) : (
                    <ul className="space-y-1">
                      {payload.sla.critical_regionals.slice(0, 4).map((item) => (
                        <li key={item.regional} className="flex items-center justify-between text-sm">
                          <span className="truncate text-slate-700">{item.regional}</span>
                          <span className="font-bold text-red-700">{item.sla_rate}%</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </SectionCard>
              )}
            </div>
          )}

          {showCharts && (
            <div className="contents">
              {showProductionChart && <MiniChart className={widgetSpan(displayConfig, "production")} order={widgetOrder(payload, "production", 1)} title="Abertas x finalizadas (7d)" option={buildProductionChartOption(productionPoints)} />}
              {showSlaChart && <MiniChart className={widgetSpan(displayConfig, "sla")} order={widgetOrder(payload, "sla", 1)} title="Tendência de SLA (7d)" option={buildSlaChartOption(slaPoints, payload.sla.target)} />}
              {showBacklogChart && <MiniChart className={widgetSpan(displayConfig, "backlog")} order={widgetOrder(payload, "backlog", 1)} title="Evolução do backlog (7d)" option={buildBacklogChartOption(backlogPoints)} />}
            </div>
          )}

          {(showProduction || showMonitorHealth) && (
            <div className="contents">
              {showProduction && (
                <SectionCard eyebrow="Produção" title="Média 7 dias" className={cn("self-start shadow-sm", widgetSpan(displayConfig, "production"))} style={{ order: widgetOrder(payload, "production") }}>
                  <div className="flex justify-around text-center">
                    <div>
                      <p className="text-xl font-bold text-slate-900">{payload.production.avg_opened_7d}</p>
                      <p className="text-[10px] text-slate-500">abertas/dia</p>
                    </div>
                    <div>
                      <p className="text-xl font-bold text-slate-900">{payload.production.avg_closed_7d}</p>
                      <p className="text-[10px] text-slate-500">finalizadas/dia</p>
                    </div>
                  </div>
                </SectionCard>
              )}

              {showMonitorHealth && (
                <SectionCard eyebrow="UNI Intelligence" title="Saúde dos monitores" className={cn("self-start shadow-sm", widgetSpan(displayConfig, "monitor_health"))} style={{ order: widgetOrder(payload, "monitor_health") }}>
                  <ul className="space-y-1">
                    {payload.monitor_health.map((monitor) => (
                      <li key={monitor.monitor_key} className="flex items-center justify-between text-xs">
                        <span className="truncate text-slate-700">{monitor.name}</span>
                        <span className={monitor.consecutive_failures > 0 || !monitor.enabled ? "font-bold text-red-600" : "font-bold text-emerald-600"}>
                          {monitor.enabled ? (monitor.consecutive_failures > 0 ? "⚠" : "✓") : "desligado"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </SectionCard>
              )}
            </div>
          )}

          {showProblems && (
            <SectionCard eyebrow="UNI Intelligence" title="Alertas da operação" subtitle={`Mostrando ${sortedProblems.length} ocorrência(s) conforme este profile`} className={cn("self-start shadow-sm", widgetSpan(displayConfig, problemsWidgetKey))} style={{ order: widgetOrder(payload, problemsWidgetKey) }}>
              {sortedProblems.length === 0 ? (
                <p className="text-sm text-slate-500">Nenhum problema ativo — operação dentro do esperado.</p>
              ) : (
                <div className="grid gap-2">
                  {sortedProblems.map((item) => (
                    <RecentAlertCard key={`${item.kind}-${item.id}`} item={item} slaTarget={payload.sla.target} compact={compactAlerts} showOsDetails={showOsDetails} showCoordinates={showCoordinates} showRecommendations={showRecommendations} />
                  ))}
                </div>
              )}
              {payload.recent_alerts.length > 0 && (
                <div className="mt-3 border-t border-slate-200 pt-3">
                  <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-600">Normalizados recentemente</p>
                  <div className="space-y-1.5">
                    {payload.recent_alerts.slice(0, 6).map((item) => (
                      <div key={`resolved-${item.id}`} className="cockpit-resolved flex flex-wrap items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2 text-xs">
                        <span className="font-semibold text-emerald-800">Normalizado</span>
                        <span className="min-w-0 flex-1 truncate text-slate-700">{item.title}</span>
                        <span className="text-slate-500">{formatDateTime(item.resolved_at)}</span>
                        <span className="text-slate-400">{item.resolution_reason === "auto_resolve" ? "Condição não voltou a ocorrer" : item.resolution_reason ?? "Encerrado"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </SectionCard>
          )}
        </section>
      </div>
      <style jsx global>{`
        .cockpit-theme-dark .bg-white { background-color: #171b22 !important; }
        .cockpit-theme-dark .bg-slate-50 { background-color: #101216 !important; }
        .cockpit-theme-dark .cockpit-soft-panel { background-color: rgba(27, 33, 43, 0.92) !important; }
        .cockpit-theme-dark .cockpit-spotlight { background-color: rgba(45, 30, 38, 0.78) !important; }
        .cockpit-theme-dark .cockpit-resolved { background-color: rgba(16, 62, 45, 0.72) !important; }
        .cockpit-theme-dark .bg-red-50\\/70 { background-color: rgba(69, 26, 33, 0.55) !important; }
        .cockpit-theme-dark .bg-amber-50\\/70 { background-color: rgba(66, 46, 18, 0.55) !important; }
        .cockpit-theme-dark .bg-emerald-50\\/70 { background-color: rgba(16, 62, 45, 0.55) !important; }
        .cockpit-theme-dark .bg-blue-50\\/70 { background-color: rgba(22, 43, 72, 0.55) !important; }
        .cockpit-theme-dark .bg-violet-50\\/70 { background-color: rgba(51, 35, 78, 0.55) !important; }
        .cockpit-theme-dark .border-red-200 { border-color: rgba(248, 113, 113, 0.35) !important; }
        .cockpit-theme-dark .border-amber-200 { border-color: rgba(251, 191, 36, 0.35) !important; }
        .cockpit-theme-dark .border-emerald-200 { border-color: rgba(52, 211, 153, 0.35) !important; }
        .cockpit-theme-dark .border-blue-200 { border-color: rgba(96, 165, 250, 0.35) !important; }
        .cockpit-theme-dark .border-violet-200 { border-color: rgba(167, 139, 250, 0.35) !important; }
        .cockpit-theme-dark .bg-slate-50\\/70 { background-color: rgba(27, 33, 43, 0.72) !important; }
        .cockpit-theme-dark .border-slate-100,
        .cockpit-theme-dark .border-slate-200 { border-color: rgba(148, 163, 184, 0.2) !important; }
        .cockpit-theme-dark .divide-slate-100 > :not([hidden]) ~ :not([hidden]) { border-color: rgba(148, 163, 184, 0.15) !important; }
        .cockpit-theme-dark .text-slate-950,
        .cockpit-theme-dark .text-slate-900,
        .cockpit-theme-dark .text-slate-800,
        .cockpit-theme-dark .text-slate-700 { color: #f1f5f9 !important; }
        .cockpit-theme-dark .text-slate-600,
        .cockpit-theme-dark .text-slate-500,
        .cockpit-theme-dark .text-slate-400 { color: #aeb9c8 !important; }
        .cockpit-theme-dark select { background-color: #171b22; color: #f1f5f9; }
      `}</style>
    </main>
  );
}
