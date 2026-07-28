"use client";

import { CalendarClock, CheckCircle2, CircleDot, Clock3, Navigation, PlayCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { OperationsOrderTextPanels } from "@/components/operations/operations-order-text-panels";
import type { OperationOrder } from "@/lib/operations-api";

function dateTime(value: string | null) {
  if (!value) return "Não informado";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Porto_Velho"
  }).format(new Date(value));
}

function durationBetween(start: string | null, end: string | null) {
  if (!start || !end) return "Não mensurável";
  const minutes = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000);
  if (minutes < 0) return "Sequência inválida";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}min` : `${hours}h`;
}

function Info({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div><p className="text-[9px] font-semibold uppercase tracking-wide text-slate-400">{label}</p><p className="mt-0.5 text-xs font-medium text-slate-800">{value || "—"}</p></div>;
}

export function OperationsOrderDetailDialog({ order, onOpenChange }: { order: OperationOrder | null; onOpenChange: (open: boolean) => void }) {
  const finishedAt = order?.finished_at || order?.closed_at || null;
  const timeline = order ? [
    { label: "Abertura", value: order.opened_at, icon: CircleDot },
    { label: "Agendada", value: order.scheduled_at, icon: CalendarClock },
    { label: "Início do deslocamento", value: order.displacement_started_at, icon: Navigation },
    { label: "Início da execução", value: order.execution_started_at, icon: PlayCircle },
    { label: "Finalização", value: finishedAt, icon: CheckCircle2 }
  ] : [];

  return <Dialog open={Boolean(order)} onOpenChange={onOpenChange}><DialogContent className="left-0 top-0 h-dvh max-h-none max-w-none translate-x-0 translate-y-0 overflow-y-auto rounded-none border-0 p-4 sm:left-1/2 sm:top-1/2 sm:h-auto sm:max-h-[88vh] sm:max-w-3xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border sm:p-6"><DialogHeader><DialogTitle className="break-words pr-6">Detalhamento da O.S. {order?.order_code}</DialogTitle><DialogDescription>Timeline operacional, tempos, SLA e dimensões normalizadas do IXC.</DialogDescription></DialogHeader>{order ? <div className="space-y-4">
    <div className="flex flex-wrap items-center gap-2"><Badge className="border-slate-200 bg-slate-50 text-slate-700">{order.status || "Status não informado"}</Badge><Badge className={order.sla_status === "out_of_time" ? "border-red-200 bg-red-50 text-red-700" : order.sla_status === "on_time" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"}>{order.sla_status === "on_time" ? "No prazo" : order.sla_status === "out_of_time" ? "Fora do prazo" : "SLA não identificado"}</Badge></div>
    <section className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="mb-3 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Linha do tempo</p><div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">{timeline.map((item) => <div key={item.label} className="rounded-lg border bg-white p-3"><item.icon className="h-4 w-4 text-blue-600" /><p className="mt-2 text-[9px] font-semibold uppercase text-slate-400">{item.label}</p><p className="mt-0.5 text-xs font-semibold text-slate-800">{dateTime(item.value)}</p></div>)}</div><div className="mt-3 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4"><div className="rounded-lg bg-white p-3"><Clock3 className="h-4 w-4 text-amber-600" /><p className="mt-1 text-slate-400">Espera até deslocamento</p><strong>{durationBetween(order.opened_at, order.displacement_started_at)}</strong></div><div className="rounded-lg bg-white p-3"><Navigation className="h-4 w-4 text-cyan-600" /><p className="mt-1 text-slate-400">Deslocamento</p><strong>{durationBetween(order.displacement_started_at, order.execution_started_at)}</strong></div><div className="rounded-lg bg-white p-3"><Clock3 className="h-4 w-4 text-blue-600" /><p className="mt-1 text-slate-400">Atendimento</p><strong>{durationBetween(order.execution_started_at, finishedAt)}</strong></div><div className="rounded-lg bg-white p-3"><Clock3 className="h-4 w-4 text-slate-600" /><p className="mt-1 text-slate-400">Ciclo total</p><strong>{durationBetween(order.opened_at, finishedAt)}</strong></div></div></section>
    <section className="grid gap-4 rounded-xl border border-slate-200 p-4 sm:grid-cols-3"><Info label="Cliente" value={order.customer_name} /><Info label="Contrato" value={order.contract_id} /><Info label="Protocolo" value={order.protocol} /><Info label="Regional" value={order.regional} /><Info label="Cidade" value={order.city} /><Info label="Responsável" value={order.responsible} /><Info label="Criador" value={order.creator} /><Info label="Setor" value={order.sector} /><Info label="Prioridade" value={order.priority} /><Info label="Tipo" value={order.os_type} /><Info label="Assunto" value={order.os_subject} /><Info label="Diagnóstico" value={order.diagnosis} /></section>
    <section className="grid gap-3 rounded-xl border border-slate-200 p-4 sm:grid-cols-3"><Info label="Meta SLA" value={order.sla_target_hours === null ? "—" : `${order.sla_target_hours}h`} /><Info label="Tempo total calculado" value={order.elapsed_hours === null ? "—" : `${order.elapsed_hours}h`} /><Info label="Prazo limite" value={dateTime(order.deadline_at)} /></section>
    <OperationsOrderTextPanels order={order} />
    {order.normalization_notes ? <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><p className="font-semibold">Observações operacionais</p><p className="mt-1 whitespace-pre-wrap">{order.normalization_notes}</p></div> : null}
  </div> : null}</DialogContent></Dialog>;
}
