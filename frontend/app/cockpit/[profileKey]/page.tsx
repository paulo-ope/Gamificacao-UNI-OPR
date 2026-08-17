"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { buildBacklogChartOption, buildProductionChartOption, buildSlaChartOption } from "@/lib/cockpit-chart-options";
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
    <div className={cn("rounded-2xl border p-5", SPOTLIGHT_PANEL_CLASS[tone])}>
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
function FeaturedProblem({ item, slaTarget }: { item: CockpitAlertSummary; slaTarget: number }) {
  const tone = SEVERITY_TONE[item.severity] ?? "slate";
  return (
    <div className={cn("rounded-xl border border-slate-200 border-l-4 bg-white p-3", LEFT_BORDER_CLASS[tone])}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{labelFor(STATUS_WORD_LABELS, item.kind)}</span>
        <SeverityDot tone={tone} label={labelFor(SEVERITY_LABEL, item.severity)} />
        <span className="text-[11px] text-slate-400">{formatAge(item.age_seconds)}</span>
      </div>
      <h3 className="mt-1.5 text-base font-semibold text-slate-950">{item.title}</h3>
      <p className="mt-1 text-sm font-medium text-slate-700">{evidenceLine(item, slaTarget)}</p>
    </div>
  );
}

// Recolhido: fundo branco, borda neutra, cor só no pontinho de severidade - mas mostra uma
// segunda linha com evidência real (nunca só severidade + título + tempo), pedido explícito do
// usuário ("hoje mostram informação insuficiente").
function CompactProblemRow({ item, slaTarget }: { item: CockpitAlertSummary; slaTarget: number }) {
  const tone = SEVERITY_TONE[item.severity] ?? "slate";
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-2.5 py-2">
      <span className={cn("h-2 w-2 shrink-0 rounded-full", DOT_COLOR_CLASS[tone])} title={labelFor(SEVERITY_LABEL, item.severity)} />
      <div className="min-w-0 flex-1">
        {/* O título de todo monitor/regra já embute a regional (ex.: "Deterioração de SLA em X",
            "Possível incidente coletivo - Y") - repetir aqui duplicava a informação. */}
        <p className="truncate text-xs font-semibold text-slate-800">{item.title}</p>
        <p className="truncate text-[11px] text-slate-500">{evidenceLine(item, slaTarget)}</p>
      </div>
      <span className="shrink-0 text-[10px] text-slate-400">{formatAge(item.age_seconds)}</span>
    </div>
  );
}

function MiniChart({ title, option }: { title: string; option: EChartsOption }) {
  return (
    <div className="min-w-[180px] flex-1 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
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
  const requestRef = useRef(0);

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

  const sortedProblems = useMemo(() => {
    if (!payload) return [];
    const rank: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    return [...payload.incidents, ...payload.alerts].sort((a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9));
  }, [payload]);

  const [featuredProblem, ...restProblems] = sortedProblems;

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
  const showProduction = widgetEnabled(payload, "production");
  const showBacklog = widgetEnabled(payload, "backlog");
  const showSla = widgetEnabled(payload, "sla");
  const showMonitorHealth = widgetEnabled(payload, "monitor_health");
  const showContent = widgetEnabled(payload, "cockpit_content") || widgetEnabled(payload, "ai_insights");

  const [featuredContent, ...restContent] = payload.content;

  const productionPoints = payload.charts.production_7d;
  const slaPoints = payload.charts.sla_7d;
  const backlogPoints = payload.charts.backlog_7d;
  const showProductionChart = showProduction && productionPoints.length > 0;
  const showSlaChart = showSla && slaPoints.length > 0;
  const showBacklogChart = showBacklog && backlogPoints.length > 0;
  const showCharts = showProductionChart || showSlaChart || showBacklogChart;

  return (
    <main className="flex h-screen w-screen flex-col overflow-hidden bg-slate-50 p-5 text-slate-900">
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
      </header>

      {fetchError && (
        <div className="mt-2 flex-shrink-0 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800">
          Atualização falhou — mostrando o último dado válido ({formatClock(lastUpdatedAt?.toISOString() ?? null)}). {fetchError}
        </div>
      )}

      {/* CORPO: área principal (UNI Intelligence) + coluna secundária/suporte */}
      <div className="mt-4 grid min-h-0 flex-1 grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-4 overflow-hidden">
        {/* PRINCIPAL: UNI Intelligence - a análise, não apenas o dado bruto */}
        {showContent && (
          <SectionCard
            eyebrow="UNI Intelligence"
            title="Análise e prioridades"
            className="flex min-h-0 flex-col"
            contentClassName="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            {payload.content.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center text-center">
                <p className="text-4xl">🧠</p>
                <p className="mt-2 text-lg font-semibold text-slate-700">Nenhuma publicação no momento</p>
                <p className="text-sm text-slate-500">A próxima análise da UNI Intelligence aparecerá aqui.</p>
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
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
        <section className={cn("flex min-h-0 flex-col gap-3 overflow-y-auto pr-1", !showContent && "col-span-2")}>
          <div className="grid flex-shrink-0 grid-cols-5 gap-3">
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
          </div>

          {(showBacklog || showSla) && (
            <div className="grid flex-shrink-0 grid-cols-2 gap-3">
              {showBacklog && (
                <SectionCard eyebrow="Backlog" title="Por idade" className="shadow-sm">
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
                <SectionCard eyebrow="SLA" title="Regionais críticas" subtitle={`meta ${payload.sla.target}%`} className="shadow-sm">
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
            <div className="flex flex-shrink-0 flex-wrap gap-3">
              {showProductionChart && <MiniChart title="Abertas x finalizadas (7d)" option={buildProductionChartOption(productionPoints)} />}
              {showSlaChart && <MiniChart title="Tendência de SLA (7d)" option={buildSlaChartOption(slaPoints, payload.sla.target)} />}
              {showBacklogChart && <MiniChart title="Evolução do backlog (7d)" option={buildBacklogChartOption(backlogPoints)} />}
            </div>
          )}

          {(showProduction || showMonitorHealth) && (
            <div className="grid flex-shrink-0 grid-cols-2 gap-3">
              {showProduction && (
                <SectionCard eyebrow="Produção" title="Média 7 dias" className="shadow-sm">
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
                <SectionCard eyebrow="UNI Intelligence" title="Saúde dos monitores" className="shadow-sm">
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
            <SectionCard eyebrow="UNI Intelligence" title="Problemas agora" className="flex-shrink-0 shadow-sm">
              {sortedProblems.length === 0 ? (
                <p className="text-sm text-slate-500">Nenhum problema ativo — operação dentro do esperado.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {featuredProblem && <FeaturedProblem item={featuredProblem} slaTarget={payload.sla.target} />}
                  {restProblems.length > 0 && (
                    <div className="space-y-1.5">
                      {restProblems.map((item) => (
                        <CompactProblemRow key={`${item.kind}-${item.id}`} item={item} slaTarget={payload.sla.target} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </SectionCard>
          )}
        </section>
      </div>
    </main>
  );
}
