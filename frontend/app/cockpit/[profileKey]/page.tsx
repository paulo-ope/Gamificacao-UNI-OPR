"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Activity, AlertTriangle, ShieldAlert } from "lucide-react";

import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { type Tone } from "@/lib/tones";
import { cn } from "@/lib/utils";
import {
  intelligenceCockpitApi,
  type CockpitAlertSummary,
  type CockpitContent,
  type CockpitPayload
} from "@/lib/intelligence-cockpit-api";

// Mesmo padrão de "barra de acento de 4px no topo do card" já usado em
// operations-openings-analytics.tsx::MetricCard - cor comunica status sem pintar o card inteiro.
// Vermelho reservado só para CRITICAL (severidade real), nunca como moldura estrutural padrão.
const STATUS_META: Record<CockpitPayload["overall_status"]["status"], { label: string; tone: Tone; accent: string }> = {
  NORMAL: { label: "NORMAL", tone: "emerald", accent: "bg-emerald-500" },
  ATTENTION: { label: "ATENÇÃO", tone: "amber", accent: "bg-amber-500" },
  RISK: { label: "RISCO", tone: "amber", accent: "bg-amber-600" },
  CRITICAL: { label: "CRÍTICO", tone: "red", accent: "bg-red-600" }
};

const SEVERITY_TONE: Record<string, Tone> = { CRITICAL: "red", HIGH: "amber", MEDIUM: "amber", LOW: "slate", INFO: "blue" };
const SEVERITY_LABEL: Record<string, string> = { CRITICAL: "Crítico", HIGH: "Alto", MEDIUM: "Médio", LOW: "Baixo", INFO: "Info" };
// Tinta de linha bem discreta (opacidade baixa), mesmo padrão de operations-control-tower.tsx -
// nunca fundo sólido colorido em lista densa.
const SEVERITY_ROW_TINT: Record<string, string> = {
  CRITICAL: "bg-red-50/40",
  HIGH: "bg-amber-50/30",
  MEDIUM: "",
  LOW: ""
};

// IA aparece como ANÁLISE (violeta, mesmo tom de "revisão/análise" já usado em scoringStatusTone),
// nunca como se fosse dado medido - distinta de gestão (azul da marca) e sistema/monitor (neutros).
const SOURCE_META: Record<string, { label: string; tone: Tone; caption: string }> = {
  AI: { label: "IA", tone: "violet", caption: "Análise gerada por IA" },
  MCP: { label: "IA", tone: "violet", caption: "Análise gerada por IA" },
  USER: { label: "GESTÃO", tone: "blue", caption: "Publicado pela gestão" },
  SYSTEM: { label: "SISTEMA", tone: "slate", caption: "Gerado pelo sistema" },
  MONITOR: { label: "MONITOR", tone: "amber", caption: "Detectado por monitor" }
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

function KpiCard({ label, value, suffix, tone = "slate" }: { label: string; value: number | null; suffix?: string; tone?: Tone }) {
  const TONE_TEXT: Record<Tone, string> = {
    emerald: "text-emerald-700",
    amber: "text-amber-700",
    red: "text-red-700",
    blue: "text-blue-700",
    violet: "text-violet-700",
    slate: "text-slate-950"
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-center shadow-sm">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className={cn("mt-1 text-4xl font-black tabular-nums", TONE_TEXT[tone])}>
        {formatNumber(value)}
        {value !== null && suffix ? suffix : ""}
      </p>
    </div>
  );
}

function FeaturedProblem({ item }: { item: CockpitAlertSummary }) {
  const tone = SEVERITY_TONE[item.severity] ?? "slate";
  const PANEL_CLASS: Record<Tone, string> = {
    red: "border-red-200 bg-red-50/70",
    amber: "border-amber-200 bg-amber-50/70",
    emerald: "border-emerald-200 bg-emerald-50/70",
    blue: "border-blue-200 bg-blue-50/70",
    violet: "border-violet-200 bg-violet-50/70",
    slate: "border-slate-200 bg-slate-50"
  };
  const Icon = item.severity === "CRITICAL" ? ShieldAlert : AlertTriangle;
  return (
    <div className={cn("rounded-2xl border p-5", PANEL_CLASS[tone])}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={tone} icon={Icon}>
          {item.kind === "INCIDENT" ? "Incidente" : "Alerta"} · {SEVERITY_LABEL[item.severity] ?? item.severity}
        </StatusBadge>
        <span className="text-[11px] text-slate-500">{formatAge(item.age_seconds)}</span>
        {item.regional ? <span className="text-[11px] text-slate-500">· {item.regional}</span> : null}
        {item.confidence !== null && (
          <span className="ml-auto text-[11px] font-medium text-slate-500">confiança {Math.round(item.confidence * 100)}%</span>
        )}
      </div>
      <h3 className="mt-2 text-xl font-semibold text-slate-950">{item.title}</h3>
      <p className="mt-1 text-sm leading-5 text-slate-700">{item.summary}</p>
      {item.recommended_action && (
        <p className="mt-3 text-sm">
          <span className="font-semibold text-slate-900">Próximo passo: </span>
          <span className="text-slate-700">{item.recommended_action}</span>
        </p>
      )}
    </div>
  );
}

function CompactProblemRow({ item }: { item: CockpitAlertSummary }) {
  const tone = SEVERITY_TONE[item.severity] ?? "slate";
  return (
    <div className={cn("flex items-center gap-2 rounded-lg px-2.5 py-2", SEVERITY_ROW_TINT[item.severity] ?? "")}>
      <StatusBadge tone={tone} dot className="shrink-0">
        {SEVERITY_LABEL[item.severity] ?? item.severity}
      </StatusBadge>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">{item.title}</span>
      <span className="shrink-0 text-[11px] text-slate-400">{formatAge(item.age_seconds)}</span>
    </div>
  );
}

function ContentCard({ item }: { item: CockpitContent }) {
  const source = SOURCE_META[item.source_type] ?? SOURCE_META.SYSTEM;
  const severityTone = SEVERITY_TONE[item.severity] ?? "blue";
  return (
    <div className="min-w-[300px] max-w-[400px] flex-shrink-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
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

  const [featured, ...rest] = sortedProblems;

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
  const isIncidentMode = payload.display_mode === "INCIDENT";
  const healthyCount = payload.monitor_health.filter((m) => m.enabled && m.consecutive_failures === 0).length;

  const showProblems = widgetEnabled(payload, "active_alerts") || widgetEnabled(payload, "active_incidents");
  const showProduction = widgetEnabled(payload, "production");
  const showBacklog = widgetEnabled(payload, "backlog");
  const showSla = widgetEnabled(payload, "sla");
  const showMonitorHealth = widgetEnabled(payload, "monitor_health");
  const showContent = widgetEnabled(payload, "cockpit_content");

  return (
    <main className="flex h-screen w-screen flex-col overflow-hidden bg-slate-50 p-5 text-slate-900">
      {/* TOPO */}
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
        <StatusBadge tone={status.tone} icon={Activity} className="px-4 py-2 text-base font-black tracking-wide">
          {status.label}
        </StatusBadge>
      </header>

      {fetchError && (
        <div className="mt-2 flex-shrink-0 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800">
          Atualização falhou — mostrando o último dado válido ({formatClock(lastUpdatedAt?.toISOString() ?? null)}). {fetchError}
        </div>
      )}

      {/* CORPO */}
      <div className="mt-4 grid min-h-0 flex-1 grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] gap-4 overflow-hidden">
        {/* ESQUERDA: PROBLEMAS AGORA */}
        {showProblems && (
          <SectionCard
            eyebrow="UNI Intelligence"
            title="Problemas agora"
            className={cn("flex min-h-0 flex-col", isIncidentMode && "ring-2 ring-red-300")}
            contentClassName="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            {sortedProblems.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center text-center">
                <p className="text-4xl">🟢</p>
                <p className="mt-2 text-lg font-semibold text-slate-700">Nenhum problema ativo</p>
                <p className="text-sm text-slate-500">A operação está dentro do esperado.</p>
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
                {featured && <FeaturedProblem item={featured} />}
                {rest.length > 0 && (
                  <div className="space-y-0.5">
                    {rest.map((item) => (
                      <CompactProblemRow key={`${item.kind}-${item.id}`} item={item} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </SectionCard>
        )}

        {/* DIREITA: KPIs + BACKLOG/SLA/PRODUÇÃO + SAÚDE DOS MONITORES */}
        <section className={cn("flex min-h-0 flex-col gap-3 overflow-y-auto pr-1", !showProblems && "col-span-2")}>
          <div className="grid flex-shrink-0 grid-cols-5 gap-3">
            <KpiCard label="Abertas" value={payload.production.opened_today} tone="blue" />
            <KpiCard label="Finalizadas" value={payload.production.closed_today} tone="emerald" />
            <KpiCard label="Saldo" value={payload.production.balance_today} tone={payload.production.balance_today > 0 ? "amber" : "slate"} />
            <KpiCard label="Backlog" value={payload.backlog.total} tone="slate" />
            <KpiCard
              label="SLA"
              value={payload.sla.current !== null ? Math.round(payload.sla.current) : null}
              suffix="%"
              tone={payload.sla.current !== null && payload.sla.current < payload.sla.target ? "amber" : "emerald"}
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
        </section>
      </div>

      {/* RODAPÉ: CONTEÚDO / UNI INTELLIGENCE */}
      {showContent && (
        <SectionCard eyebrow="UNI Intelligence" title="Conteúdo" className="mt-4 flex-shrink-0 shadow-sm">
          {payload.content.length === 0 ? (
            <p className="text-sm text-slate-400">Nenhum conteúdo publicado no momento.</p>
          ) : (
            <div className="flex gap-3 overflow-x-auto pb-1">
              {payload.content.map((item) => (
                <ContentCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </SectionCard>
      )}
    </main>
  );
}
