"use client";

import {
  BookOpen,
  Building2,
  Calculator,
  ClipboardCheck,
  ClipboardList,
  Loader2,
  LogOut,
  Medal,
  Search,
  ShieldCheck,
  Sparkles,
  Trophy,
  UserRound
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, setAuthToken } from "@/lib/api";
import type { PortalAudit, PortalOrder, PortalOverview, PortalRules, PortalSimulation, PortalSummary } from "@/lib/types";

type PortalTab = "overview" | "home" | "audit" | "ranking" | "orders" | "simulation" | "rules";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const tabs: Array<{ id: PortalTab; label: string; icon: typeof Trophy; fullOnly?: boolean }> = [
  { id: "overview", label: "Visao geral", icon: Building2, fullOnly: true },
  { id: "home", label: "Painel", icon: UserRound },
  { id: "audit", label: "Auditoria", icon: ClipboardCheck },
  { id: "ranking", label: "Ranking", icon: Trophy },
  { id: "orders", label: "O.S", icon: ClipboardList },
  { id: "simulation", label: "Simular", icon: Calculator },
  { id: "rules", label: "Regras", icon: BookOpen }
];

function formatNumber(value: number | null | undefined) {
  return numberFormat.format(Number(value ?? 0));
}

function formatMoney(value: number | null | undefined) {
  return moneyFormat.format(Number(value ?? 0));
}

function periodLabel(summary: PortalSummary | null) {
  const month = summary?.period.reference_month;
  const year = summary?.period.reference_year;
  if (!month || !year) return "Sem fechamento";
  return `${String(month).padStart(2, "0")}/${year}`;
}

function statusClass(label: string) {
  const value = label.toLowerCase();
  if (value.includes("sem regra") || value.includes("manual")) return "border-amber-200 bg-amber-50 text-amber-800";
  if (value.includes("anulada") || value.includes("desconto")) return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function StatCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-500">{detail}</p> : null}
    </div>
  );
}

function RuleList({
  title,
  items,
  primaryKey,
  secondaryKey
}: {
  title: string;
  items: PortalRules[keyof PortalRules];
  primaryKey: string;
  secondaryKey?: string;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase text-slate-600">{title}</h2>
        <Badge>{items.length}</Badge>
      </div>
      <div className="space-y-2">
        {items.slice(0, 80).map((item, index) => (
          <div key={`${title}-${index}`} className="rounded-lg border bg-white p-3 shadow-sm">
            <p className="text-sm font-semibold text-slate-950">{String(item[primaryKey] ?? "Regra")}</p>
            {secondaryKey ? <p className="mt-1 text-xs text-slate-500">{String(item[secondaryKey] ?? "")}</p> : null}
          </div>
        ))}
        {!items.length ? <p className="rounded-lg border bg-white p-4 text-sm text-slate-500">Nenhuma regra ativa.</p> : null}
      </div>
    </section>
  );
}

export default function PortalPage() {
  const [activeTab, setActiveTab] = useState<PortalTab>("home");
  const [summary, setSummary] = useState<PortalSummary | null>(null);
  const [overview, setOverview] = useState<PortalOverview | null>(null);
  const [orders, setOrders] = useState<PortalOrder[]>([]);
  const [audit, setAudit] = useState<PortalAudit | null>(null);
  const [rules, setRules] = useState<PortalRules | null>(null);
  const [simulation, setSimulation] = useState<PortalSimulation | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [extraPoints, setExtraPoints] = useState("10");
  const [auditQuery, setAuditQuery] = useState("");
  const [auditBreakdown, setAuditBreakdown] = useState<"groups" | "subjects">("groups");
  const [loading, setLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPortal = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, orderData, ruleData, auditData] = await Promise.all([
        api.portalSummary(), api.portalOrders(80), api.portalRules(), api.portalAudit()
      ]);
      setSummary(summaryData);
      setOrders(orderData);
      setRules(ruleData);
      setAudit(auditData);
      if (summaryData.user.permissions.includes("portal:read_overview")) {
        setOverview(await api.portalOverview());
      } else {
        setOverview(null);
      }
    } catch (err) {
      setSummary(null);
      setOrders([]);
      setRules(null);
      setAudit(null);
      setOverview(null);
      setError(err instanceof Error ? err.message : "Nao foi possivel carregar o portal.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPortal();
  }, [loadPortal]);

  const score = summary?.score ?? null;
  const availableTabs = tabs.filter((tab) => !tab.fullOnly || summary?.user.permissions.includes("portal:read_overview"));
  const positionLabel = summary?.regional_position ? `${summary.regional_position} de ${summary.regional_total}` : "--";
  const filteredOrders = useMemo(() => orders.slice(0, 80), [orders]);
  const auditOrders = useMemo(() => {
    const query = auditQuery.trim().toLowerCase();
    if (!query) return audit?.orders ?? [];
    return (audit?.orders ?? []).filter((order) =>
      [order.os_code, order.os_type, order.os_subject, order.group_name, order.status_label]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [audit, auditQuery]);
  const auditBreakdowns = audit ? audit[auditBreakdown] : [];
  const auditMaxBreakdownPoints = Math.max(1, ...auditBreakdowns.map((item) => item.net_points));

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginLoading(true);
    setError(null);
    try {
      const result = await api.login(email.trim(), password);
      setAuthToken(result.access_token);
      await loadPortal();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel entrar.");
    } finally {
      setLoginLoading(false);
    }
  }

  async function handleSimulation() {
    const parsed = Number(extraPoints.replace(",", "."));
    if (!Number.isFinite(parsed) || parsed < 0) {
      setError("Informe pontos extras validos.");
      return;
    }
    setError(null);
    setSimulation(await api.portalSimulation(parsed));
  }

  function logout() {
    setAuthToken(null);
    setSummary(null);
    setOrders([]);
    setRules(null);
    setAudit(null);
    setOverview(null);
    setSimulation(null);
  }

  if (loading && !summary) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="flex items-center gap-3 rounded-lg border bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          <Loader2 className="h-4 w-4 animate-spin text-sky-600" />
          Carregando portal
        </div>
      </main>
    );
  }

  if (!summary) {
    return (
      <main className="min-h-screen bg-slate-50 px-4 py-8">
        <section className="mx-auto max-w-md rounded-lg border bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-600 text-white">
              <Trophy className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-950">Portal do ranking</h1>
              <p className="text-sm text-slate-500">Acompanhamento individual e regional.</p>
            </div>
          </div>
          <form className="space-y-3" onSubmit={handleLogin}>
            <Input autoComplete="email" placeholder="E-mail" value={email} onChange={(event) => setEmail(event.target.value)} />
            <Input
              autoComplete="current-password"
              placeholder="Senha"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}
            <Button className="w-full" disabled={loginLoading} type="submit">
              {loginLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Entrar
            </Button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 pb-24 text-slate-950 md:pb-0">
      <header className="sticky top-0 z-20 border-b bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase text-sky-700">UNI OPR</p>
            <h1 className="truncate text-lg font-semibold">Portal do ranking</h1>
          </div>
          <div className="flex items-center gap-2">
            <Badge>{periodLabel(summary)}</Badge>
            <Button aria-label="Sair" size="icon" variant="ghost" onClick={logout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <nav className="mx-auto hidden max-w-6xl gap-2 px-4 pb-3 md:flex">
          {availableTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <Button key={tab.id} size="sm" variant={activeTab === tab.id ? "default" : "outline"} onClick={() => setActiveTab(tab.id)}>
                <Icon className="h-4 w-4" />
                {tab.label}
              </Button>
            );
          })}
        </nav>
      </header>

      <div className="mx-auto max-w-6xl space-y-5 px-4 py-5">
        {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}
        {summary.message ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{summary.message}</p> : null}

        {activeTab === "overview" && overview ? (
          <section className="space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-sm text-slate-500">Acompanhamento executivo de todas as regionais</p>
                <h2 className="text-2xl font-semibold">Visao geral do fechamento</h2>
              </div>
              <Badge className="border-sky-200 bg-sky-50 text-sky-700">{overview.total_regionals} regionais</Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Colaboradores" value={formatNumber(overview.total_collaborators)} detail={`${formatNumber(overview.total_service_orders)} O.S. no periodo`} />
              <StatCard label="Pontuacao total" value={`${formatNumber(overview.final_points)} pts`} detail={`${formatNumber(overview.scored_service_orders)} O.S. pontuadas`} />
              <StatCard label="Pagamento estimado" value={formatMoney(overview.estimated_payment)} detail={`${formatNumber(overview.penalty_points)} pts em descontos`} />
              <StatCard label="Pendencias" value={formatNumber(overview.unscored_service_orders + overview.manual_review_service_orders)} detail={`${overview.unscored_service_orders} sem regra, ${overview.manual_review_service_orders} em revisao`} />
            </div>
            {overview.alerts.length ? <div className="rounded-lg border border-amber-200 bg-amber-50 p-4"><h3 className="text-sm font-semibold text-amber-900">Pontos de atencao</h3><ul className="mt-2 space-y-1 text-sm text-amber-800">{overview.alerts.map((alert) => <li key={alert}>{alert}</li>)}</ul></div> : null}
            <div className="grid gap-5 lg:grid-cols-2">
              <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">Desempenho por regional</h3></div>
                <div className="divide-y">
                  {overview.regional_summary.map((regional) => <div key={regional.regional} className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3"><div><p className="font-medium">{regional.regional}</p><p className="text-xs text-slate-500">{regional.collaborators} colaboradores · {regional.service_orders} O.S. · saude {formatNumber(regional.health_average)}x</p></div><div className="text-right"><p className="font-semibold">{formatNumber(regional.final_points)} pts</p><p className="text-xs text-slate-500">{formatMoney(regional.estimated_payment)}</p></div></div>)}
                </div>
              </section>
              <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">Ranking geral</h3></div>
                <div className="divide-y">
                  {overview.ranking.slice(0, 10).map((item) => <div key={item.collaborator_id} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-4 py-3"><span className="text-sm font-semibold text-slate-500">#{item.position}</span><div className="min-w-0"><p className="truncate font-medium">{item.collaborator_name}</p><p className="truncate text-xs text-slate-500">{item.regional} · {item.role ?? "Colaborador"}</p></div><div className="text-right"><p className="font-semibold">{formatNumber(item.final_points)} pts</p><p className="text-xs text-slate-500">{item.service_orders_count} O.S.</p></div></div>)}
                </div>
              </section>
            </div>
          </section>
        ) : null}

        {activeTab === "home" ? (
          <section className="space-y-4">
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <p className="text-sm text-slate-500">{summary.collaborator?.regional ?? "Regional nao vinculada"}</p>
              <h2 className="mt-1 text-2xl font-semibold">{summary.collaborator?.name ?? summary.user.name}</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge className="border-sky-200 bg-sky-50 text-sky-700">
                  <Medal className="mr-1 h-3 w-3" />
                  Regional: {positionLabel}
                </Badge>
                <Badge>Geral: {summary.general_position ?? "--"} de {summary.general_total}</Badge>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Pontuacao" value={`${formatNumber(score?.final_points)} pts`} detail={`Bruto: ${formatNumber(score?.gross_points)} pts`} />
              <StatCard label="Pagamento estimado" value={formatMoney(score?.estimated_payment)} detail={`Multiplicador: ${formatNumber(score?.health_multiplier)}`} />
              <StatCard label="O.S pontuadas" value={formatNumber(score?.scored_service_orders)} detail={`${formatNumber(score?.service_orders_count)} O.S no periodo`} />
              <StatCard label="Para subir" value={`${formatNumber(summary.next_position_gap)} pts`} detail={summary.next_position_gap ? "Ate a posicao acima" : "Voce esta no topo ou sem ranking"} />
            </div>
          </section>
        ) : null}

        {activeTab === "audit" && audit ? (
          <section className="space-y-5">
            <div className="overflow-hidden rounded-lg border border-cyan-900 bg-cyan-950 p-5 text-white shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-cyan-100">Extrato de performance</p>
                  <h2 className="mt-1 text-2xl font-semibold">Entenda cada ponto do seu fechamento</h2>
                  <p className="mt-2 max-w-2xl text-sm text-cyan-100">Veja de onde vieram seus ganhos, onde houve impacto e quais O.S. sustentaram o resultado do período.</p>
                </div>
                <div className="rounded-lg border border-cyan-700 bg-cyan-900 px-4 py-3">
                  <p className="text-xs font-medium uppercase text-cyan-200">Resultado final</p>
                  <p className="mt-1 text-2xl font-semibold">{formatNumber(audit.final_points)} pts</p>
                  <p className="text-sm text-cyan-100">{formatMoney(audit.estimated_payment)}</p>
                </div>
              </div>
            </div>
            {audit.message ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{audit.message}</p> : null}
            <section className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
              <div className="rounded-lg border bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between gap-3"><h3 className="font-semibold">Composicao do resultado</h3><Badge className="border-cyan-200 bg-cyan-50 text-cyan-800">{audit.health_status}</Badge></div>
                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  <div><p className="text-xs font-medium uppercase text-slate-500">Pontos base</p><p className="mt-1 text-xl font-semibold">{formatNumber(audit.gross_points)}</p></div>
                  <div><p className="text-xs font-medium uppercase text-slate-500">Descontos</p><p className="mt-1 text-xl font-semibold text-rose-700">-{formatNumber(audit.penalty_points)}</p></div>
                  <div><p className="text-xs font-medium uppercase text-slate-500">Liquido</p><p className="mt-1 text-xl font-semibold text-emerald-700">{formatNumber(audit.net_points)}</p></div>
                </div>
                <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, Math.max(0, (audit.net_points / Math.max(audit.gross_points, 1)) * 100))}%` }} /></div>
                <p className="mt-2 text-sm text-slate-500">{formatNumber(audit.health_multiplier)}x de multiplicador aplicado sobre o resultado liquido.</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
                <p className="text-xs font-medium uppercase text-amber-800">Proximo movimento</p>
                <p className="mt-2 text-3xl font-semibold text-amber-950">{formatNumber(audit.points_to_next_position)} pts</p>
                <p className="mt-1 text-sm text-amber-900">Estimativa para alcancar a posicao imediatamente acima na regional.</p>
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-amber-200 pt-4 text-sm"><div><p className="text-amber-800">Pontuadas</p><p className="font-semibold text-amber-950">{audit.scored_service_orders}</p></div><div><p className="text-amber-800">Total de O.S.</p><p className="font-semibold text-amber-950">{audit.service_orders_count}</p></div></div>
              </div>
            </section>
            <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Sem regra" value={formatNumber(audit.unscored_service_orders)} detail="O.S. sem pontuacao configurada" />
              <StatCard label="Em revisao" value={formatNumber(audit.manual_review_service_orders)} detail="Aguardam validacao" />
              <StatCard label="Recorrencias" value={formatNumber(audit.recurrence_service_orders)} detail="Impactam o fechamento" />
              <StatCard label="SLA fora" value={formatNumber(audit.sla_out_service_orders)} detail="Exigem acompanhamento" />
            </section>
            <section className="rounded-lg border bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">O que mais pagou no periodo</h3><p className="mt-1 text-sm text-slate-500">Distribuicao dos pontos liquidos por origem.</p></div><div className="flex gap-2"><Button size="sm" variant={auditBreakdown === "groups" ? "default" : "outline"} onClick={() => setAuditBreakdown("groups")}>Grupos</Button><Button size="sm" variant={auditBreakdown === "subjects" ? "default" : "outline"} onClick={() => setAuditBreakdown("subjects")}>Assuntos</Button></div></div>
              <div className="mt-5 space-y-4">
                {auditBreakdowns.map((item) => <div key={item.label}><div className="mb-1 flex items-center justify-between gap-3 text-sm"><div className="min-w-0"><p className="truncate font-medium">{item.label}</p><p className="text-xs text-slate-500">{item.service_orders} O.S. · {formatNumber(item.base_points)} pts base</p></div><p className="whitespace-nowrap font-semibold text-emerald-700">{formatNumber(item.net_points)} pts</p></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-cyan-600" style={{ width: `${Math.max(3, (item.net_points / auditMaxBreakdownPoints) * 100)}%` }} /></div></div>)}
                {!auditBreakdowns.length ? <p className="text-sm text-slate-500">Ainda nao ha pontuacao para agrupar.</p> : null}
              </div>
            </section>
            <div className="grid gap-5 lg:grid-cols-2">
              <section className="rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">O.S. que mais geraram pontos</h3></div>
                <div className="divide-y">
                  {audit.top_positive_orders.map((order) => <div key={order.os_code} className="flex items-start justify-between gap-3 px-4 py-3"><div className="min-w-0"><p className="text-xs text-slate-500">O.S. {order.os_code}</p><p className="truncate font-medium">{order.os_subject}</p></div><p className="whitespace-nowrap font-semibold text-emerald-700">+{formatNumber(order.net_points)} pts</p></div>)}
                  {!audit.top_positive_orders.length ? <p className="px-4 py-3 text-sm text-slate-500">Nenhuma O.S. pontuada no periodo.</p> : null}
                </div>
              </section>
              <section className="rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">O.S. que pedem atencao</h3></div>
                <div className="divide-y">
                  {audit.attention_orders.map((order) => <div key={order.os_code} className="px-4 py-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs text-slate-500">O.S. {order.os_code}</p><p className="truncate font-medium">{order.os_subject}</p></div><p className="whitespace-nowrap font-semibold text-rose-700">{formatNumber(order.penalty_points)} pts</p></div><p className="mt-1 text-xs text-slate-500">{order.reason ?? order.status_label}</p></div>)}
                  {!audit.attention_orders.length ? <p className="px-4 py-3 text-sm text-slate-500">Nenhuma pendencia ou desconto relevante.</p> : null}
                </div>
              </section>
            </div>
            <section className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-4 py-3"><h3 className="font-semibold">Historico de fechamento</h3></div>
              <div className="grid divide-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                {audit.history.map((item) => <div key={`${item.reference_month}-${item.reference_year}`} className="p-4"><p className="text-xs text-slate-500">{String(item.reference_month).padStart(2, "0")}/{item.reference_year}</p><p className="mt-1 text-xl font-semibold">{formatNumber(item.final_points)} pts</p><p className="text-sm text-slate-500">{item.service_orders_count} O.S. · {formatMoney(item.estimated_payment)}</p></div>)}
                {!audit.history.length ? <p className="p-4 text-sm text-slate-500">Ainda nao ha historico de fechamentos.</p> : null}
              </div>
            </section>
            <section className="rounded-lg border bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3"><div><h3 className="font-semibold">Historico de O.S. do periodo</h3><p className="text-sm text-slate-500">Consulte a origem da sua pontuacao.</p></div><div className="relative w-full sm:w-72"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><Input className="pl-9" placeholder="Buscar O.S., assunto ou grupo" value={auditQuery} onChange={(event) => setAuditQuery(event.target.value)} /></div></div>
              <div className="max-h-[440px] overflow-auto">
                <table className="w-full min-w-[700px] text-left text-sm"><thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">O.S.</th><th className="px-4 py-3">Grupo e assunto</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Base</th><th className="px-4 py-3 text-right">Desconto</th><th className="px-4 py-3 text-right">Liquido</th></tr></thead><tbody className="divide-y">{auditOrders.map((order) => <tr key={order.os_code}><td className="px-4 py-3 font-medium">{order.os_code}<p className="mt-0.5 text-xs font-normal text-slate-500">{order.os_type}</p></td><td className="px-4 py-3"><p className="font-medium">{order.os_subject}</p><p className="text-xs text-slate-500">{order.group_name ?? "Sem regra"}</p></td><td className="px-4 py-3"><Badge className={statusClass(order.status_label)}>{order.status_label}</Badge></td><td className="px-4 py-3 text-right">{formatNumber(order.base_points)}</td><td className="px-4 py-3 text-right text-rose-700">{formatNumber(order.penalty_points)}</td><td className="px-4 py-3 text-right font-semibold text-emerald-700">{formatNumber(order.net_points)}</td></tr>)}</tbody></table>
                {!auditOrders.length ? <p className="p-4 text-sm text-slate-500">Nenhuma O.S. encontrada com esse filtro.</p> : null}
              </div>
            </section>
          </section>
        ) : null}

        {activeTab === "ranking" ? (
          <section className="space-y-3">
            {summary.ranking.map((item) => (
              <div
                key={item.collaborator_id}
                className={`rounded-lg border bg-white p-4 shadow-sm ${item.is_current_user ? "border-sky-300 ring-2 ring-sky-100" : ""}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-slate-500">#{item.position}</p>
                    <h2 className="truncate text-base font-semibold">{item.collaborator_name}</h2>
                    <p className="text-sm text-slate-500">{item.role ?? "Colaborador"}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-semibold">{formatNumber(item.final_points)} pts</p>
                    <p className="text-xs text-slate-500">{formatMoney(item.estimated_payment)}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
                  <Badge>{item.service_orders_count} O.S</Badge>
                  <Badge>{item.scored_service_orders} pontuadas</Badge>
                  <Badge>{formatNumber(item.penalty_points)} pts desconto</Badge>
                </div>
              </div>
            ))}
            {!summary.ranking.length ? <p className="rounded-lg border bg-white p-4 text-sm text-slate-500">Ranking regional vazio.</p> : null}
          </section>
        ) : null}

        {activeTab === "orders" ? (
          <section className="space-y-3">
            {filteredOrders.map((order) => (
              <div key={order.id} className="rounded-lg border bg-white p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-slate-500">O.S {order.os_code}</p>
                    <h2 className="mt-1 text-sm font-semibold">{order.os_subject}</h2>
                    <p className="mt-1 text-xs text-slate-500">{order.os_type} · {order.diagnosis ?? "Sem diagnostico"}</p>
                  </div>
                  <Badge className={statusClass(order.status_label)}>{order.status_label}</Badge>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                  <span><b>{formatNumber(order.base_points)}</b><br />base</span>
                  <span><b>{formatNumber(order.penalty_points)}</b><br />desconto</span>
                  <span><b>{formatNumber(order.net_points)}</b><br />liquido</span>
                </div>
                {order.reason ? <p className="mt-3 text-xs text-slate-500">{order.reason}</p> : null}
              </div>
            ))}
            {!filteredOrders.length ? <p className="rounded-lg border bg-white p-4 text-sm text-slate-500">Nenhuma O.S encontrada no periodo.</p> : null}
          </section>
        ) : null}

        {activeTab === "simulation" ? (
          <section className="space-y-4">
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <label className="text-sm font-medium text-slate-700" htmlFor="extra-points">Pontos extras</label>
              <div className="mt-2 flex gap-2">
                <Input id="extra-points" inputMode="decimal" value={extraPoints} onChange={(event) => setExtraPoints(event.target.value)} />
                <Button onClick={handleSimulation}>
                  <Sparkles className="h-4 w-4" />
                  Simular
                </Button>
              </div>
            </div>
            {simulation ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <StatCard label="Posicao atual" value={simulation.current_position ? `#${simulation.current_position}` : "--"} />
                <StatCard label="Com simulacao" value={simulation.simulated_position ? `#${simulation.simulated_position}` : "--"} />
                <StatCard label="Proximo lugar" value={`${formatNumber(simulation.points_to_next)} pts`} />
                <p className="rounded-lg border bg-white p-4 text-sm text-slate-500 sm:col-span-3">{simulation.disclaimer}</p>
              </div>
            ) : null}
          </section>
        ) : null}

        {activeTab === "rules" && rules ? (
          <section className="grid gap-5 lg:grid-cols-2">
            <RuleList title="Grupos" items={rules.groups} primaryKey="name" secondaryKey="description" />
            <RuleList title="Assuntos" items={rules.subjects} primaryKey="os_subject" secondaryKey="group_name" />
            <RuleList title="Diagnosticos" items={rules.diagnosis_rules} primaryKey="diagnosis_name" secondaryKey="action_type" />
            <RuleList title="SLA" items={rules.sla_rules} primaryKey="name" secondaryKey="penalty_type" />
            <RuleList title="Recorrencia" items={rules.recurrence_rules} primaryKey="name" secondaryKey="classification" />
          </section>
        ) : null}
      </div>

      <nav className={`fixed inset-x-0 bottom-0 z-30 grid border-t bg-white px-2 py-2 shadow-lg md:hidden ${availableTabs.length === 7 ? "grid-cols-7" : availableTabs.length === 6 ? "grid-cols-6" : "grid-cols-5"}`}>
        {availableTabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`flex min-w-0 flex-col items-center gap-1 rounded-md px-1 py-2 text-[11px] font-medium ${active ? "bg-sky-50 text-sky-700" : "text-slate-500"}`}
              type="button"
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon className="h-4 w-4" />
              <span className="truncate">{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </main>
  );
}
