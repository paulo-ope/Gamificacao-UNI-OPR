"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { WorkspaceLogin } from "@/components/workspace/workspace-login";
import { useWorkspaceAuth } from "@/hooks/use-workspace-auth";
import { cn } from "@/lib/utils";
import {
  intelligenceCockpitApi,
  type CockpitAlertSummary,
  type CockpitContent,
  type CockpitPayload
} from "@/lib/intelligence-cockpit-api";

const STATUS_STYLE: Record<CockpitPayload["overall_status"]["status"], { label: string; bg: string; text: string; ring: string }> = {
  NORMAL: { label: "NORMAL", bg: "bg-emerald-500", text: "text-emerald-950", ring: "ring-emerald-300" },
  ATTENTION: { label: "ATENÇÃO", bg: "bg-amber-400", text: "text-amber-950", ring: "ring-amber-300" },
  RISK: { label: "RISCO", bg: "bg-orange-500", text: "text-white", ring: "ring-orange-300" },
  CRITICAL: { label: "CRÍTICO", bg: "bg-red-600", text: "text-white", ring: "ring-red-300" }
};

const SEVERITY_STYLE: Record<string, { label: string; badge: string }> = {
  CRITICAL: { label: "Crítico", badge: "bg-red-100 text-red-800 border-red-300" },
  HIGH: { label: "Alto", badge: "bg-orange-100 text-orange-800 border-orange-300" },
  MEDIUM: { label: "Médio", badge: "bg-amber-100 text-amber-800 border-amber-300" },
  LOW: { label: "Baixo", badge: "bg-slate-100 text-slate-700 border-slate-300" },
  INFO: { label: "Info", badge: "bg-blue-100 text-blue-700 border-blue-300" }
};

const SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  AI: { label: "IA", className: "bg-violet-600 text-white" },
  MCP: { label: "IA", className: "bg-violet-600 text-white" },
  USER: { label: "GESTÃO", className: "bg-uni-royal text-white" },
  SYSTEM: { label: "SISTEMA", className: "bg-slate-600 text-white" },
  MONITOR: { label: "MONITOR", className: "bg-amber-600 text-white" }
};

function formatAge(seconds: number): string {
  if (seconds < 60) return "agora";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min atrás`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h atrás`;
  const days = Math.floor(hours / 24);
  return `${days}d atrás`;
}

function formatClock(iso: string | null): string {
  if (!iso) return "--:--";
  return new Date(iso).toLocaleTimeString("pt-BR", { timeZone: "America/Porto_Velho", hour: "2-digit", minute: "2-digit" });
}

function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR").format(value);
}

function ProblemCard({ item }: { item: CockpitAlertSummary }) {
  const severity = SEVERITY_STYLE[item.severity] ?? SEVERITY_STYLE.LOW;
  const isIncident = item.kind === "INCIDENT";
  return (
    <div
      className={cn(
        "rounded-2xl border p-4",
        isIncident ? "border-red-300 bg-red-50" : "border-slate-200 bg-white"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", severity.badge)}>
            {isIncident ? "Incidente" : "Alerta"} · {severity.label}
          </span>
          <span className="text-[11px] text-slate-500">{formatAge(item.age_seconds)}</span>
        </div>
        {item.confidence !== null && (
          <span className="text-[11px] font-medium text-slate-500">confiança {Math.round(item.confidence * 100)}%</span>
        )}
      </div>
      <h3 className="mt-2 text-lg font-semibold text-slate-900">{item.title}</h3>
      <p className="mt-1 text-sm text-slate-600">{item.summary}</p>
      {item.recommended_action && (
        <p className="mt-2 text-sm font-medium text-uni-royal">→ {item.recommended_action}</p>
      )}
    </div>
  );
}

function ContentCard({ item }: { item: CockpitContent }) {
  const source = SOURCE_BADGE[item.source_type] ?? SOURCE_BADGE.SYSTEM;
  const severity = SEVERITY_STYLE[item.severity] ?? SEVERITY_STYLE.INFO;
  return (
    <div className="min-w-[320px] max-w-[420px] flex-shrink-0 rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide", source.className)}>{source.label}</span>
        <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase", severity.badge)}>{severity.label}</span>
      </div>
      <h4 className="mt-2 text-sm font-semibold text-slate-900">{item.title}</h4>
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

  const status = STATUS_STYLE[payload.overall_status.status];
  const isIncidentMode = payload.display_mode === "INCIDENT";
  const healthySummary = `${payload.monitor_health.filter((m) => m.enabled && m.consecutive_failures === 0).length}/${payload.monitor_health.length}`;

  return (
    <main className="flex h-screen w-screen flex-col overflow-hidden bg-slate-50 p-5 text-slate-900">
      {/* TOPO */}
      <header className="flex flex-shrink-0 items-center justify-between rounded-2xl border border-slate-200 bg-white px-6 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-uni-royal">UNI Internet</p>
          <h1 className="text-2xl font-bold text-slate-900">Operação Agora</h1>
          <p className="text-xs text-slate-500">
            {payload.profile.name} · atualizado às {formatClock(lastUpdatedAt?.toISOString() ?? payload.generated_at)} · monitores saudáveis {healthySummary}
          </p>
        </div>
        <div className={cn("flex items-center gap-3 rounded-2xl px-6 py-3 ring-4", status.bg, status.text, status.ring)}>
          <span className="text-3xl font-black tracking-wide">{status.label}</span>
        </div>
      </header>

      {fetchError && (
        <div className="mt-2 flex-shrink-0 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800">
          Atualização falhou — mostrando o último dado válido ({formatClock(lastUpdatedAt?.toISOString() ?? null)}). {fetchError}
        </div>
      )}

      {/* CORPO */}
      <div className="mt-4 grid min-h-0 flex-1 grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] gap-4 overflow-hidden">
        {/* ESQUERDA: PROBLEMAS AGORA */}
        <section className={cn("flex min-h-0 flex-col rounded-2xl border bg-white p-5", isIncidentMode ? "border-red-300" : "border-slate-200")}>
          <h2 className="flex-shrink-0 text-sm font-bold uppercase tracking-wide text-slate-500">Problemas agora</h2>
          {sortedProblems.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <p className="text-4xl">🟢</p>
              <p className="mt-2 text-lg font-semibold text-slate-700">Nenhum problema ativo</p>
              <p className="text-sm text-slate-500">A operação está dentro do esperado.</p>
            </div>
          ) : (
            <div className="mt-3 flex-1 space-y-3 overflow-y-auto pr-1">
              {sortedProblems.map((item) => (
                <ProblemCard key={`${item.kind}-${item.id}`} item={item} />
              ))}
            </div>
          )}
        </section>

        {/* DIREITA: KPIs + BACKLOG/SLA/PRODUÇÃO + SAÚDE DOS MONITORES */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <div className="grid flex-shrink-0 grid-cols-5 gap-3">
            {[
              { label: "Abertas", value: payload.production.opened_today },
              { label: "Finalizadas", value: payload.production.closed_today },
              { label: "Saldo", value: payload.production.balance_today },
              { label: "Backlog", value: payload.backlog.total },
              { label: "SLA", value: payload.sla.current !== null ? Math.round(payload.sla.current) : null, suffix: "%" }
            ].map((kpi) => (
              <div key={kpi.label} className="rounded-2xl border border-slate-200 bg-white p-4 text-center">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{kpi.label}</p>
                <p className="mt-1 text-3xl font-black tabular-nums text-slate-900">
                  {formatNumber(kpi.value)}
                  {kpi.suffix ?? ""}
                </p>
              </div>
            ))}
          </div>

          <div className="grid flex-shrink-0 grid-cols-2 gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Backlog por idade</p>
              <div className="mt-2 grid grid-cols-3 gap-2 text-center">
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
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">SLA regionais críticas</p>
              {payload.sla.critical_regionals.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">Nenhuma regional abaixo da meta ({payload.sla.target}%).</p>
              ) : (
                <ul className="mt-2 space-y-1">
                  {payload.sla.critical_regionals.slice(0, 4).map((item) => (
                    <li key={item.regional} className="flex items-center justify-between text-sm">
                      <span className="truncate text-slate-700">{item.regional}</span>
                      <span className="font-bold text-red-700">{item.sla_rate}%</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="grid flex-shrink-0 grid-cols-2 gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Produção (média 7d)</p>
              <div className="mt-2 flex justify-around text-center">
                <div>
                  <p className="text-xl font-bold text-slate-900">{payload.production.avg_opened_7d}</p>
                  <p className="text-[10px] text-slate-500">abertas/dia</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-slate-900">{payload.production.avg_closed_7d}</p>
                  <p className="text-[10px] text-slate-500">finalizadas/dia</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Saúde dos monitores</p>
              <ul className="mt-2 space-y-1">
                {payload.monitor_health.map((monitor) => (
                  <li key={monitor.monitor_key} className="flex items-center justify-between text-xs">
                    <span className="truncate text-slate-700">{monitor.name}</span>
                    <span className={monitor.consecutive_failures > 0 || !monitor.enabled ? "font-bold text-red-600" : "font-bold text-emerald-600"}>
                      {monitor.enabled ? (monitor.consecutive_failures > 0 ? "⚠" : "✓") : "desligado"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </div>

      {/* RODAPÉ: CONTEÚDO / UNI INTELLIGENCE */}
      <footer className="mt-4 flex-shrink-0 rounded-2xl border border-slate-200 bg-white p-4">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-500">Conteúdo · UNI Intelligence</p>
        {payload.content.length === 0 ? (
          <p className="text-sm text-slate-400">Nenhum conteúdo publicado no momento.</p>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-1">
            {payload.content.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </footer>
    </main>
  );
}
