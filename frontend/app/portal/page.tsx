"use client";

import {
  BookOpen,
  Building2,
  ClipboardList,
  Loader2,
  LogOut,
  Search,
  ShieldCheck,
  Sparkles,
  Trophy,
  Users as Users2Icon,
  UserRound,
  CircleUserRound
} from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CollaboratorOverview } from "@/components/portal/collaborator-overview";
import { HowScoringWorks } from "@/components/portal/how-scoring-works";
import { ManagerTeamOverview } from "@/components/portal/manager-team-overview";
import { OrderAuditTags } from "@/components/portal/order-audit-tags";
import { ProfileSettings } from "@/components/portal/profile-settings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, setAuthToken } from "@/lib/api";
import type { PortalAudit, PortalOrder, PortalOverview, PortalRules, PortalSimulation, PortalSummary, PortalTeamSummary } from "@/lib/types";

type PortalTab = "overview" | "home" | "audit" | "ranking" | "orders" | "simulation" | "rules" | "team" | "profile";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const tabs: Array<{ id: PortalTab; label: string; icon: typeof Trophy; fullOnly?: boolean; teamOnly?: boolean }> = [
  { id: "overview", label: "Visão geral", icon: Building2, fullOnly: true },
  { id: "team", label: "Minha equipe", icon: Users2Icon, teamOnly: true },
  { id: "home", label: "Meu momento", icon: UserRound },
  { id: "orders", label: "Minhas O.S.", icon: ClipboardList },
  { id: "ranking", label: "Minha regional", icon: Trophy },
  { id: "rules", label: "Como pontuo", icon: BookOpen }
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

function periodKey(month: number, year: number) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function statusClass(label: string) {
  const value = label.toLowerCase();
  if (value.includes("sem regra") || value.includes("manual")) return "border-amber-200 bg-amber-50 text-amber-800";
  if (value.includes("anulada") || value.includes("desconto")) return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function slaLabel(value: string | null | undefined) {
  if (value === "NO_PRAZO") return "No prazo";
  if (value === "FORA_DO_PRAZO") return "Fora do prazo";
  return "Não identificado";
}

function externalStatusLabel(value: string | null | undefined) {
  if (!value) return "Não informado";
  return value
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

function orderEffectLabel(order: Pick<PortalOrder, "base_points" | "penalty_points" | "net_points">) {
  if (order.base_points <= 0) return "Sem pontos configurados para a base";
  if (order.net_points <= 0 && order.penalty_points > 0) return "Entrou na base, mas foi zerada por regra";
  if (order.penalty_points > 0) return "Entrou com redução por regra";
  return "Entrou integralmente no fechamento";
}

function multiplierEffect(points: number, multiplier: number | null | undefined) {
  return points * Number(multiplier ?? 1);
}

function regionalStats(summary: PortalSummary | null) {
  const ranking = summary?.ranking ?? [];
  const average = ranking.length
    ? ranking.reduce((total, item) => total + item.final_points, 0) / ranking.length
    : 0;
  const leader = ranking[0] ?? null;
  const current = summary?.score?.final_points ?? 0;
  return {
    average,
    leader,
    currentVsAverage: current - average
  };
}

function StatCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="min-w-0 rounded-lg border bg-white p-3 shadow-sm sm:p-4">
      <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
      <p className="mt-2 break-words text-xl font-semibold leading-tight text-slate-950 sm:text-2xl">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-500">{detail}</p> : null}
    </div>
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
  const [teamSummary, setTeamSummary] = useState<PortalTeamSummary | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [extraPoints, setExtraPoints] = useState("10");
  const [selectedPeriod, setSelectedPeriod] = useState<{ reference_month: number; reference_year: number } | null>(null);
  const [auditQuery, setAuditQuery] = useState("");
  const [orderQuery, setOrderQuery] = useState("");
  const [auditBreakdown, setAuditBreakdown] = useState<"groups" | "subjects">("groups");
  const [orderFilter, setOrderFilter] = useState<"all" | "scored" | "impact" | "recurrence">("all");
  const [loading, setLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPortal = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, orderData, ruleData, auditData] = await Promise.all([
        api.portalSummary(selectedPeriod ?? undefined),
        api.portalOrders(80, selectedPeriod ?? undefined),
        api.portalRules(),
        api.portalAudit(selectedPeriod ?? undefined)
      ]);
      setSummary(summaryData);
      const canReadOverview = summaryData.user.permissions.includes("portal:read_overview");
      const canReadTeam = summaryData.user.permissions.includes("portal:read_regional_summary");
      if (canReadOverview && !summaryData.collaborator) {
        setActiveTab("overview");
      } else if (canReadTeam && !summaryData.collaborator) {
        setActiveTab("team");
      }
      setOrders(orderData);
      setRules(ruleData);
      setAudit(auditData);
      setOverview(canReadOverview ? await api.portalOverview() : null);
      setTeamSummary(canReadTeam ? await api.portalTeamSummary() : null);
    } catch (err) {
      setSummary(null);
      setOrders([]);
      setRules(null);
      setAudit(null);
      setOverview(null);
      setTeamSummary(null);
      setError(err instanceof Error ? err.message : "Não foi possível carregar o portal.");
    } finally {
      setLoading(false);
    }
  }, [selectedPeriod]);

  useEffect(() => {
    loadPortal();
  }, [loadPortal]);

  const score = summary?.score ?? null;
  const periodOptions = useMemo(() => {
    const options = new Map<string, { reference_month: number; reference_year: number }>();
    if (summary?.period.reference_month && summary.period.reference_year) {
      options.set(periodKey(summary.period.reference_month, summary.period.reference_year), {
        reference_month: summary.period.reference_month,
        reference_year: summary.period.reference_year
      });
    }
    audit?.history.forEach((item) => {
      options.set(periodKey(item.reference_month, item.reference_year), {
        reference_month: item.reference_month,
        reference_year: item.reference_year
      });
    });
    return Array.from(options.values()).sort((left, right) =>
      right.reference_year - left.reference_year || right.reference_month - left.reference_month
    );
  }, [audit?.history, summary?.period.reference_month, summary?.period.reference_year]);
  const availableTabs = tabs.filter((tab) => {
    if (tab.fullOnly && !summary?.user.permissions.includes("portal:read_overview")) return false;
    if (tab.teamOnly && !summary?.user.permissions.includes("portal:read_regional_summary")) return false;
    return true;
  });
  const positionLabel = summary?.regional_position ? `${summary.regional_position} de ${summary.regional_total}` : "--";
  const regional = regionalStats(summary);
  const filteredOrders = useMemo(() => {
    const query = orderQuery.trim().toLowerCase();
    const byFilter = orders.filter((order) => {
      if (orderFilter === "scored") return order.net_points > 0;
      if (orderFilter === "impact") return order.penalty_points > 0 || order.status_label.toLowerCase().includes("sem regra") || order.status_label.toLowerCase().includes("revisao");
      if (orderFilter === "recurrence") return order.status_label.toLowerCase().includes("reincid");
      return true;
    });
    if (!query) return byFilter.slice(0, 80);
    return byFilter.filter((order) =>
      [order.os_code, order.customer_name, order.os_subject, order.os_type, order.group_name, order.status_label, order.status]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
    ).slice(0, 80);
  }, [orderFilter, orderQuery, orders]);
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
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    } finally {
      setLoginLoading(false);
    }
  }

  async function handleSimulation() {
    const parsed = Number(extraPoints.replace(",", "."));
    if (!Number.isFinite(parsed) || parsed < 0) {
      setError("Informe pontos extras válidos.");
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
    setTeamSummary(null);
    setSelectedPeriod(null);
  }

  if (loading && !summary) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="flex items-center gap-3 rounded-lg border bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          <Loader2 className="h-4 w-4 animate-spin text-[#2d5fff]" />
          Carregando portal
        </div>
      </main>
    );
  }

  if (!summary) {
    return (
      <main className="min-h-screen bg-background px-4 py-8">
        <section className="uni-surface mx-auto max-w-md rounded-lg p-5">
          <div className="mb-5 flex items-center gap-3">
            <Image alt="UNI Internet" className="h-10 w-16 object-contain object-left" height={40} priority src="/brand/uni-logo.png" width={64} />
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
    <main className="min-h-screen bg-background pb-[calc(5.5rem+env(safe-area-inset-bottom))] text-slate-950 md:pb-0">
      <header className="sticky top-0 z-20 border-b bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-3 py-3 sm:px-4">
          <div className="flex min-w-0 items-center gap-3">
            <Image alt="UNI Internet" className="h-9 w-14 shrink-0 object-contain object-left" height={36} priority src="/brand/uni-logo.png" width={56} />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase text-[#0028f3]">UNI OPR</p>
              <h1 className="truncate text-lg font-semibold">Portal do ranking</h1>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <label className="sr-only" htmlFor="portal-period">Fechamento</label>
            <select
              className="h-8 max-w-24 rounded-md border border-slate-200 bg-white px-2 text-sm font-medium text-slate-700 outline-none ring-offset-2 focus:ring-2 focus:ring-[#2d5fff]"
              id="portal-period"
              value={selectedPeriod
                ? periodKey(selectedPeriod.reference_month, selectedPeriod.reference_year)
                : summary.period.reference_month && summary.period.reference_year
                  ? periodKey(summary.period.reference_month, summary.period.reference_year)
                  : ""}
              onChange={(event) => {
                const [referenceYear, referenceMonth] = event.target.value.split("-").map(Number);
                if (referenceMonth && referenceYear) {
                  setSelectedPeriod({ reference_month: referenceMonth, reference_year: referenceYear });
                  if (activeTab === "overview" || activeTab === "team") setActiveTab("home");
                }
              }}
            >
              {!periodOptions.length ? <option value="">{periodLabel(summary)}</option> : null}
              {periodOptions.map((item) => (
                <option key={periodKey(item.reference_month, item.reference_year)} value={periodKey(item.reference_month, item.reference_year)}>
                  {String(item.reference_month).padStart(2, "0")}/{item.reference_year}
                </option>
              ))}
            </select>
            <Button aria-label="Meu perfil" className="px-2 sm:px-3" size="sm" variant={activeTab === "profile" ? "default" : "outline"} onClick={() => setActiveTab("profile")}>
              <CircleUserRound className="h-4 w-4" />
              <span className="hidden sm:inline">Perfil</span>
            </Button>
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

      <div className="mx-auto max-w-6xl space-y-4 px-3 py-4 sm:space-y-5 sm:px-4 sm:py-5">
        {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}
        {summary.message ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{summary.message}</p> : null}

        {activeTab === "overview" && overview ? (
          <section className="space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm text-slate-500">Acompanhamento executivo de todas as regionais</p>
                <h2 className="text-xl font-semibold leading-tight sm:text-2xl">Visão geral do fechamento</h2>
              </div>
              <Badge className="border-[#2d5fff]/25 bg-[#2d5fff]/10 text-[#0028f3]">{overview.total_regionals} regionais</Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Colaboradores" value={formatNumber(overview.total_collaborators)} detail={`${formatNumber(overview.total_service_orders)} O.S. no período`} />
              <StatCard label="Pontuação total" value={`${formatNumber(overview.final_points)} pts`} detail={`${formatNumber(overview.scored_service_orders)} O.S. pontuadas`} />
              <StatCard label="Pagamento estimado" value={formatMoney(overview.estimated_payment)} detail={`${formatNumber(overview.penalty_points)} pts em descontos`} />
              <StatCard label="Pendências" value={formatNumber(overview.unscored_service_orders + overview.manual_review_service_orders)} detail={`${overview.unscored_service_orders} sem regra, ${overview.manual_review_service_orders} em revisão`} />
            </div>
            {overview.alerts.length ? <div className="rounded-lg border border-amber-200 bg-amber-50 p-4"><h3 className="text-sm font-semibold text-amber-900">Pontos de atenção</h3><ul className="mt-2 space-y-1 text-sm text-amber-800">{overview.alerts.map((alert) => <li key={alert}>{alert}</li>)}</ul></div> : null}
            <div className="grid gap-5 lg:grid-cols-2">
              <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">Desempenho por regional</h3></div>
                <div className="divide-y">
                  {overview.regional_summary.map((regional) => <div key={regional.regional} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:gap-3"><div className="min-w-0"><p className="font-medium">{regional.regional}</p><p className="text-xs text-slate-500">{regional.collaborators} colaboradores · {regional.service_orders} O.S. · saúde {formatNumber(regional.health_average)}x</p></div><div className="sm:text-right"><p className="font-semibold">{formatNumber(regional.final_points)} pts</p><p className="text-xs text-slate-500">{formatMoney(regional.estimated_payment)}</p></div></div>)}
                </div>
              </section>
              <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">Ranking geral</h3></div>
                <div className="divide-y">
                  {overview.ranking.slice(0, 10).map((item) => <div key={item.collaborator_id} className="grid grid-cols-[auto_1fr] gap-3 px-4 py-3 sm:grid-cols-[auto_1fr_auto] sm:items-center"><span className="text-sm font-semibold text-slate-500">#{item.position}</span><div className="min-w-0"><p className="truncate font-medium">{item.collaborator_name}</p><p className="truncate text-xs text-slate-500">{item.regional} · {item.role ?? "Colaborador"}</p></div><div className="col-span-2 text-left sm:col-span-1 sm:text-right"><p className="font-semibold">{formatNumber(item.final_points)} pts</p><p className="text-xs text-slate-500">{item.service_orders_count} O.S.</p></div></div>)}
                </div>
              </section>
            </div>
          </section>
        ) : null}

        {activeTab === "team" ? (
          teamSummary ? <ManagerTeamOverview team={teamSummary} /> : null
        ) : null}

        {activeTab === "home" ? (
          !summary.collaborator ? (
            <section className="mx-auto max-w-xl rounded-lg border border-amber-200 bg-amber-50 p-5">
              <h2 className="text-lg font-semibold text-amber-950">Seu acesso ainda não está vinculado</h2>
              <p className="mt-2 text-sm text-amber-900">
                {summary.user.permissions.includes("portal:read_regional_summary")
                  ? "Este acesso acompanha uma regional inteira, veja a aba \"Minha equipe\"."
                  : "Peça ao responsável para associar seu usuário ao seu cadastro de colaborador. Assim que o vínculo for feito, apenas suas O.S., pontos e ranking regional aparecerão aqui."}
              </p>
            </section>
          ) : audit ? <CollaboratorOverview audit={audit} summary={summary} onOpenOrders={() => { setOrderFilter("all"); setActiveTab("orders"); }} /> : null
        ) : null}

        {activeTab === "audit" && audit ? (
          <section className="space-y-5">
            <div className="uni-gradient overflow-hidden rounded-lg border p-5 text-white shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm text-white/80">Extrato de performance</p>
                  <h2 className="mt-1 text-xl font-semibold leading-tight sm:text-2xl">Entenda cada ponto do seu fechamento</h2>
                  <p className="mt-2 max-w-2xl text-sm text-white/80">Veja de onde vieram seus ganhos, onde houve impacto e quais O.S. sustentaram o resultado do período.</p>
                </div>
                <div className="w-full rounded-lg border border-white/25 bg-white/15 px-4 py-3 sm:w-auto">
                  <p className="text-xs font-medium uppercase text-white/70">Resultado final</p>
                  <p className="mt-1 text-2xl font-semibold">{formatNumber(audit.final_points)} pts</p>
                  <p className="text-sm text-white/80">{formatMoney(audit.estimated_payment)}</p>
                </div>
              </div>
            </div>
            {audit.message ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{audit.message}</p> : null}
            <section className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
              <div className="rounded-lg border bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Composição do resultado</h3><Badge className="border-[#2d5fff]/25 bg-[#2d5fff]/10 text-[#0028f3]">{audit.health_status}</Badge></div>
                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  <div><p className="text-xs font-medium uppercase text-slate-500">Pontos base</p><p className="mt-1 text-xl font-semibold">{formatNumber(audit.gross_points)}</p></div>
                  <div><p className="text-xs font-medium uppercase text-slate-500">Descontos</p><p className="mt-1 text-xl font-semibold text-rose-700">-{formatNumber(audit.penalty_points)}</p></div>
                  <div><p className="text-xs font-medium uppercase text-slate-500">Líquido</p><p className="mt-1 text-xl font-semibold text-emerald-700">{formatNumber(audit.net_points)}</p></div>
                </div>
                <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, Math.max(0, (audit.net_points / Math.max(audit.gross_points, 1)) * 100))}%` }} /></div>
                <p className="mt-2 text-sm text-slate-500">{formatNumber(audit.health_multiplier)}x de multiplicador aplicado sobre o resultado líquido.</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
                <p className="text-xs font-medium uppercase text-amber-800">Próximo movimento</p>
                <p className="mt-2 text-3xl font-semibold text-amber-950">{formatNumber(audit.points_to_next_position)} pts</p>
                <p className="mt-1 text-sm text-amber-900">Estimativa para alcançar a posição imediatamente acima na regional.</p>
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-amber-200 pt-4 text-sm"><div><p className="text-amber-800">Pontuadas</p><p className="font-semibold text-amber-950">{audit.scored_service_orders}</p></div><div><p className="text-amber-800">Total de O.S.</p><p className="font-semibold text-amber-950">{audit.service_orders_count}</p></div></div>
              </div>
            </section>
            <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Sem regra" value={formatNumber(audit.unscored_service_orders)} detail="O.S. sem pontuação configurada" />
              <StatCard label="Em revisão" value={formatNumber(audit.manual_review_service_orders)} detail="Aguardam validação" />
              <StatCard label="Recorrências" value={formatNumber(audit.recurrence_service_orders)} detail="Impactam o fechamento" />
              <StatCard label="SLA fora" value={formatNumber(audit.sla_out_service_orders)} detail="Exigem acompanhamento" />
            </section>
            <section className="rounded-lg border bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3"><div className="min-w-0"><h3 className="font-semibold">O que mais pagou no período</h3><p className="mt-1 text-sm text-slate-500">Distribuição dos pontos líquidos por origem.</p></div><div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto"><Button size="sm" variant={auditBreakdown === "groups" ? "default" : "outline"} onClick={() => setAuditBreakdown("groups")}>Grupos</Button><Button size="sm" variant={auditBreakdown === "subjects" ? "default" : "outline"} onClick={() => setAuditBreakdown("subjects")}>Assuntos</Button></div></div>
              <div className="mt-5 space-y-4">
                {auditBreakdowns.map((item) => <div key={item.label}><div className="mb-1 grid gap-1 text-sm sm:grid-cols-[1fr_auto] sm:items-center sm:gap-3"><div className="min-w-0"><p className="truncate font-medium">{item.label}</p><p className="text-xs text-slate-500">{item.service_orders} O.S. · {formatNumber(item.base_points)} pts base</p></div><p className="font-semibold text-[#0028f3] sm:whitespace-nowrap">{formatNumber(item.net_points)} pts</p></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#2d5fff]" style={{ width: `${Math.max(3, (item.net_points / auditMaxBreakdownPoints) * 100)}%` }} /></div></div>)}
                {!auditBreakdowns.length ? <p className="text-sm text-slate-500">Ainda não há pontuação para agrupar.</p> : null}
              </div>
            </section>
            <div className="grid gap-5 lg:grid-cols-2">
              <section className="rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">O.S. que mais geraram pontos</h3></div>
                <div className="divide-y">
                  {audit.top_positive_orders.map((order) => <div key={order.os_code} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-start sm:gap-3"><div className="min-w-0"><p className="text-xs text-slate-500">O.S. {order.os_code}</p><p className="truncate font-medium">{order.os_subject}</p></div><p className="font-semibold text-emerald-700 sm:whitespace-nowrap">+{formatNumber(order.net_points)} pts</p></div>)}
                  {!audit.top_positive_orders.length ? <p className="px-4 py-3 text-sm text-slate-500">Nenhuma O.S. pontuada no período.</p> : null}
                </div>
              </section>
              <section className="rounded-lg border bg-white shadow-sm">
                <div className="border-b px-4 py-3"><h3 className="font-semibold">O.S. que pedem atenção</h3></div>
                <div className="divide-y">
                  {audit.attention_orders.map((order) => <div key={order.os_code} className="px-4 py-3"><div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-start sm:gap-3"><div className="min-w-0"><p className="text-xs text-slate-500">O.S. {order.os_code}</p><p className="truncate font-medium">{order.os_subject}</p></div><p className="font-semibold text-rose-700 sm:whitespace-nowrap">{formatNumber(order.penalty_points)} pts</p></div><p className="mt-1 text-xs text-slate-500">{order.reason ?? order.status_label}</p></div>)}
                  {!audit.attention_orders.length ? <p className="px-4 py-3 text-sm text-slate-500">Nenhuma pendência ou desconto relevante.</p> : null}
                </div>
              </section>
            </div>
            <section className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-4 py-3"><h3 className="font-semibold">Histórico de fechamento</h3></div>
              <div className="grid divide-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                {audit.history.map((item) => <div key={`${item.reference_month}-${item.reference_year}`} className="p-4"><p className="text-xs text-slate-500">{String(item.reference_month).padStart(2, "0")}/{item.reference_year}</p><p className="mt-1 text-xl font-semibold">{formatNumber(item.final_points)} pts</p><p className="text-sm text-slate-500">{item.service_orders_count} O.S. · {formatMoney(item.estimated_payment)}</p></div>)}
                {!audit.history.length ? <p className="p-4 text-sm text-slate-500">Ainda não há histórico de fechamentos.</p> : null}
              </div>
            </section>
            <section className="rounded-lg border bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3"><div className="min-w-0"><h3 className="font-semibold">Histórico de O.S. do período</h3><p className="text-sm text-slate-500">Consulte a origem da sua pontuação.</p></div><div className="relative w-full sm:w-72"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><Input className="pl-9" placeholder="Buscar O.S., assunto ou grupo" value={auditQuery} onChange={(event) => setAuditQuery(event.target.value)} /></div></div>
              <div className="max-h-[440px] overflow-auto">
                <table className="w-full min-w-[700px] text-left text-sm"><thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">O.S.</th><th className="px-4 py-3">Grupo e assunto</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Base</th><th className="px-4 py-3 text-right">Desconto</th><th className="px-4 py-3 text-right">Líquido</th></tr></thead><tbody className="divide-y">{auditOrders.map((order) => <tr key={order.os_code}><td className="px-4 py-3 font-medium">{order.os_code}<p className="mt-0.5 text-xs font-normal text-slate-500">{order.os_type}</p></td><td className="px-4 py-3"><p className="font-medium">{order.os_subject}</p><p className="text-xs text-slate-500">{order.group_name ?? "Sem regra"}</p></td><td className="px-4 py-3"><Badge className={statusClass(order.status_label)}>{order.status_label}</Badge></td><td className="px-4 py-3 text-right">{formatNumber(order.base_points)}</td><td className="px-4 py-3 text-right text-rose-700">{formatNumber(order.penalty_points)}</td><td className="px-4 py-3 text-right font-semibold text-emerald-700">{formatNumber(order.net_points)}</td></tr>)}</tbody></table>
                {!auditOrders.length ? <p className="p-4 text-sm text-slate-500">Nenhuma O.S. encontrada com esse filtro.</p> : null}
              </div>
            </section>
          </section>
        ) : null}

        {activeTab === "ranking" ? (
          <section className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard label="Sua posição" value={positionLabel} detail={summary.collaborator?.regional ?? "Regional"} />
              <StatCard label="Média regional" value={`${formatNumber(regional.average)} pts`} detail={regional.currentVsAverage >= 0 ? `${formatNumber(regional.currentVsAverage)} pts acima da média` : `${formatNumber(Math.abs(regional.currentVsAverage))} pts abaixo da média`} />
              <StatCard label="Líder da regional" value={regional.leader ? `${formatNumber(regional.leader.final_points)} pts` : "--"} detail={regional.leader?.collaborator_name ?? "Sem ranking"} />
            </div>
            {summary.ranking.map((item) => (
              <div
                key={item.collaborator_id}
              className={`rounded-lg border bg-white p-4 shadow-sm ${item.is_current_user ? "border-[#2d5fff] ring-2 ring-[#27d9bf]/40" : ""}`}
              >
                <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-start">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase text-slate-500">#{item.position}</p>
                    <h2 className="truncate text-base font-semibold">{item.collaborator_name}</h2>
                    <p className="text-sm text-slate-500">{item.role ?? "Colaborador"}</p>
                  </div>
                  <div className="sm:text-right">
                    <p className="text-lg font-semibold">{formatNumber(item.final_points)} pts</p>
                    <p className="text-xs text-slate-500">{formatMoney(item.estimated_payment)}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
                  <Badge>{item.service_orders_count} O.S.</Badge>
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
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input className="pl-9" placeholder="Buscar por cliente, O.S., assunto, grupo ou status" value={orderQuery} onChange={(event) => setOrderQuery(event.target.value)} />
            </div>
            <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
              {[
                ["all", "Todas"],
                ["scored", "Pontuadas"],
                ["impact", "Com impacto"],
                ["recurrence", "Reincidências"]
              ].map(([value, label]) => <Button key={value} className="shrink-0" size="sm" variant={orderFilter === value ? "default" : "outline"} onClick={() => setOrderFilter(value as typeof orderFilter)}>{label}</Button>)}
            </div>
            {filteredOrders.map((order) => (
              <details key={order.id} className="group rounded-lg border bg-white shadow-sm">
                <summary className="grid cursor-pointer list-none gap-3 p-4 [&::-webkit-details-marker]:hidden sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-semibold text-slate-950">{order.customer_name ?? "Cliente não informado"}</h2>
                    <p className="mt-1 truncate text-sm text-slate-700">{order.os_subject}</p>
                    <p className="mt-1 text-xs text-slate-500">O.S. {order.os_code} · {order.os_type}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                    <p className={`text-sm font-semibold ${order.net_points > 0 ? "text-emerald-700" : "text-rose-700"}`}>{formatNumber(order.net_points)} pts</p>
                    <Badge className={`${statusClass(order.status_label)} w-fit`}>{order.status_label}</Badge>
                    <span className="text-xs font-medium text-[#0028f3] group-open:hidden">Detalhes</span>
                    <span className="hidden text-xs font-medium text-[#0028f3] group-open:inline">Fechar</span>
                  </div>
                </summary>
                <div className="border-t p-4">
                <div className="grid gap-2 text-sm sm:grid-cols-4">
                  <div className="rounded-lg border bg-slate-50 p-3">
                    <p className="text-xs font-medium uppercase text-slate-500">Base da O.S.</p>
                    <p className="mt-1 text-lg font-semibold text-slate-950">{formatNumber(order.base_points)} pts</p>
                    <p className="text-xs text-slate-500">{order.group_name ?? "Sem regra configurada"}</p>
                  </div>
                  <div className="rounded-lg border bg-slate-50 p-3">
                    <p className="text-xs font-medium uppercase text-slate-500">Status externo</p>
                    <p className="mt-1 font-semibold text-slate-950">{externalStatusLabel(order.status)}</p>
                    <p className="text-xs text-slate-500">SLA: {slaLabel(order.sla_status_normalized)}</p>
                  </div>
                  <div className="rounded-lg border bg-slate-50 p-3">
                    <p className="text-xs font-medium uppercase text-slate-500">Regra aplicada</p>
                    <p className="mt-1 text-lg font-semibold text-rose-700">-{formatNumber(order.penalty_points)} pts</p>
                    <p className="text-xs text-slate-500">{order.status_label}</p>
                  </div>
                  <div className="rounded-lg border bg-emerald-50 p-3">
                    <p className="text-xs font-medium uppercase text-emerald-700">Vale no fechamento</p>
                    <p className="mt-1 text-lg font-semibold text-emerald-800">{formatNumber(order.net_points)} pts</p>
                    <p className="text-xs text-emerald-700">Com multiplicador: {formatNumber(multiplierEffect(order.net_points, score?.health_multiplier ?? audit?.health_multiplier))} pts</p>
                  </div>
                </div>
                <div className="mt-3 rounded-lg border border-[#2d5fff]/15 bg-[#2d5fff]/5 p-3 text-sm text-slate-700">
                  <p className="font-medium text-slate-950">{orderEffectLabel(order)}</p>
                  <p className="mt-1 text-xs text-slate-600">
                    No ranking: esta O.S. ajuda com {formatNumber(order.net_points)} pts líquidos antes do multiplicador de saúde operacional.
                  </p>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge className="border-[#2d5fff]/20 bg-[#2d5fff]/5 text-[#0028f3]">SLA: {slaLabel(order.sla_status_normalized)}</Badge>
                  {order.diagnosis ? <Badge className="border-slate-200 bg-slate-50 text-slate-700">Diagnóstico: {order.diagnosis}</Badge> : null}
                </div>
                {order.reason ? <p className="mt-3 text-xs text-slate-600">{order.reason}</p> : null}
                <OrderAuditTags order={order} />
                </div>
              </details>
            ))}
            {!filteredOrders.length ? <p className="rounded-lg border bg-white p-4 text-sm text-slate-500">Nenhuma O.S. encontrada no período.</p> : null}
          </section>
        ) : null}

        {activeTab === "simulation" ? (
          <section className="space-y-4">
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <label className="text-sm font-medium text-slate-700" htmlFor="extra-points">Pontos extras</label>
              <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto]">
                <Input id="extra-points" inputMode="decimal" value={extraPoints} onChange={(event) => setExtraPoints(event.target.value)} />
                <Button className="w-full sm:w-auto" onClick={handleSimulation}>
                  <Sparkles className="h-4 w-4" />
                  Simular
                </Button>
              </div>
            </div>
            {simulation ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <StatCard label="Posição atual" value={simulation.current_position ? `#${simulation.current_position}` : "--"} />
                <StatCard label="Com simulação" value={simulation.simulated_position ? `#${simulation.simulated_position}` : "--"} />
                <StatCard label="Próximo lugar" value={`${formatNumber(simulation.points_to_next)} pts`} />
                <p className="rounded-lg border bg-white p-4 text-sm text-slate-500 sm:col-span-3">{simulation.disclaimer}</p>
              </div>
            ) : null}
          </section>
        ) : null}

        {activeTab === "rules" && rules ? <HowScoringWorks rules={rules} /> : null}
        {activeTab === "profile" ? <ProfileSettings /> : null}
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t bg-white px-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2 shadow-lg md:hidden">
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${availableTabs.length}, minmax(64px, 1fr))` }}>
        {availableTabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`flex min-w-0 flex-col items-center gap-1 rounded-md px-1 py-2 text-[11px] font-medium ${active ? "bg-[#2d5fff]/10 text-[#0028f3]" : "text-slate-500"}`}
              type="button"
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon className="h-4 w-4" />
              <span className="truncate">{tab.label}</span>
            </button>
          );
        })}
        </div>
      </nav>
    </main>
  );
}
