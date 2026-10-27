"use client";

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import type { SupportFeedbackDetails, SupportFeedbackRatedAttendance } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";
import { dateBr } from "./feedback-format";

// Análise detalhada do Feedback individual (pedido do usuário, 2026-10-27): notas boas/ruins do OPA e O.S. abertas
// indevidamente (IXC). Contagens, listas e motivos vêm prontos de `feedback_details.py`; aqui só se desenha.

const BAND_LABEL = { good: "Boas (4–5)", neutral: "Neutras (2–4)", bad: "Ruins (1–2)" } as const;
const BAND_BADGE = {
  good: "bg-emerald-100 text-emerald-800",
  neutral: "bg-slate-100 text-slate-700",
  bad: "bg-red-100 text-red-700",
} as const;

const percentLabel = (value: number | null) => (value === null ? "-" : `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value)}%`);
const dateOf = (iso: string) => dateBr(iso.slice(0, 10));
const dateTimeOf = (iso: string) => `${dateOf(iso)} ${iso.slice(11, 16)}`;

export function CollapsibleSection({
  id,
  eyebrow,
  title,
  summary,
  open,
  onToggle,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  summary: ReactNode;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
        <span>
          <span className="block text-[10px] font-semibold uppercase tracking-wide text-blue-600">{eyebrow}</span>
          <span className="block text-base font-bold text-slate-900">{title}</span>
          <span className="mt-1 block text-xs text-slate-600">{summary}</span>
        </span>
        <ChevronDown className={`h-5 w-5 shrink-0 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open ? <div className="grid gap-4 border-t border-slate-100 p-4">{children}</div> : null}
    </section>
  );
}

function BandBar({ good, neutral, bad }: { good: number; neutral: number; bad: number }) {
  const total = good + neutral + bad;
  if (!total) return null;
  const width = (value: number) => `${(value / total) * 100}%`;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${good} boas, ${neutral} neutras, ${bad} ruins`}>
      <span className="bg-emerald-500" style={{ width: width(good) }} />
      <span className="bg-slate-300" style={{ width: width(neutral) }} />
      <span className="bg-red-500" style={{ width: width(bad) }} />
    </div>
  );
}

export function RatingsSection({ details, open, onToggle }: { details: SupportFeedbackDetails; open: boolean; onToggle: () => void }) {
  const ratings = details.ratings;
  const [filter, setFilter] = useState<"all" | SupportFeedbackRatedAttendance["band"]>("all");
  const rows = useMemo(() => ratings.attendances.filter((row) => filter === "all" || row.band === filter), [ratings.attendances, filter]);
  return (
    <CollapsibleSection
      id="feedback-ratings"
      eyebrow="Avaliação individual"
      title="Notas boas e ruins (OPA)"
      open={open}
      onToggle={onToggle}
      summary={
        ratings.rated_count
          ? `${ratings.rated_count} avaliações · ${ratings.good.count} boas · ${ratings.neutral.count} neutras · ${ratings.bad.count} ruins`
          : "Nenhum atendimento avaliado no período."
      }
    >
      {ratings.rated_count ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {(["good", "neutral", "bad"] as const).map((band) => (
              <button
                key={band}
                type="button"
                onClick={() => setFilter(filter === band ? "all" : band)}
                aria-pressed={filter === band}
                className={`rounded-xl border p-3 text-left ${filter === band ? "border-sky-400 ring-1 ring-sky-300" : "border-slate-200"} ${BAND_BADGE[band]}`}
              >
                <span className="block text-[11px] font-semibold uppercase tracking-wide">{BAND_LABEL[band]}</span>
                <span className="block text-2xl font-bold tabular-nums">{ratings[band].count}</span>
                <span className="block text-xs">{percentLabel(ratings[band].percent)} das avaliações</span>
              </button>
            ))}
          </div>
          <BandBar good={ratings.good.count} neutral={ratings.neutral.count} bad={ratings.bad.count} />

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Por dia</p>
              <ul className="grid gap-1.5">
                {ratings.by_day.map((point) => (
                  <li key={point.day} className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-2 text-xs">
                    <span className="font-semibold text-slate-700">{dateBr(point.day).slice(0, 5)}</span>
                    <BandBar good={point.good} neutral={point.neutral} bad={point.bad} />
                    <span className="tabular-nums text-slate-600">
                      {point.good}/{point.neutral}/{point.bad}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Por canal</p>
              <ul className="grid gap-1.5">
                {ratings.by_channel.map((point) => (
                  <li key={point.channel} className="grid grid-cols-[5rem_1fr_auto] items-center gap-2 text-xs">
                    <span className="truncate font-semibold capitalize text-slate-700">{point.channel}</span>
                    <BandBar good={point.good} neutral={point.neutral} bad={point.bad} />
                    <span className="tabular-nums text-slate-600">
                      {point.good}/{point.neutral}/{point.bad}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[10px] text-slate-500">Boas / neutras / ruins.</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border border-slate-200 text-sm">
              <thead>
                <tr className="bg-sky-100 text-left text-[10px] uppercase tracking-wide text-slate-600">
                  <th className="px-3 py-2 font-semibold">Data</th>
                  <th className="px-3 py-2 font-semibold">Protocolo</th>
                  <th className="px-3 py-2 font-semibold">Canal</th>
                  <th className="px-3 py-2 font-semibold">Motivo</th>
                  <th className="px-3 py-2 font-semibold">TMR</th>
                  <th className="px-3 py-2 font-semibold">TMA</th>
                  <th className="px-3 py-2 font-semibold">Nota</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.protocol}-${index}`} className="border-t border-slate-100 odd:bg-white even:bg-slate-50">
                    <td className="px-3 py-1.5 tabular-nums">{dateOf(row.opened_at)}</td>
                    <td className="px-3 py-1.5 tabular-nums">{row.protocol ?? "-"}</td>
                    <td className="px-3 py-1.5 capitalize">{row.channel ?? "-"}</td>
                    <td className="px-3 py-1.5">{row.reason ?? "Sem motivo registrado"}</td>
                    <td className="px-3 py-1.5 tabular-nums">{formatCardValue({ unit: "seconds" }, row.tmr_seconds)}</td>
                    <td className="px-3 py-1.5 tabular-nums">{formatCardValue({ unit: "seconds" }, row.tma_seconds)}</td>
                    <td className="px-3 py-1.5">
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-bold ${BAND_BADGE[row.band]}`}>{row.rating}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {ratings.truncated ? <p className="mt-1 text-[11px] text-slate-500">Mostrando os 200 atendimentos avaliados mais recentes.</p> : null}
          </div>
        </>
      ) : null}
    </CollapsibleSection>
  );
}

export function ImproperOrdersSection({ details, open, onToggle }: { details: SupportFeedbackDetails; open: boolean; onToggle: () => void }) {
  const orders = details.improper_orders;
  if (!orders) {
    return (
      <CollapsibleSection id="feedback-improper" eyebrow="O.S. aberta a campo" title="O.S. abertas indevidamente (IXC)" open={open} onToggle={onToggle} summary="Colaborador não encontrado no IXC pelo nome.">
        <p className="text-sm text-slate-600">Sem o usuário no IXC não há como ligar as O.S. a este colaborador.</p>
      </CollapsibleSection>
    );
  }
  return (
    <CollapsibleSection
      id="feedback-improper"
      eyebrow="O.S. aberta a campo"
      title="O.S. abertas indevidamente (IXC)"
      open={open}
      onToggle={onToggle}
      summary={
        orders.total_orders
          ? `${orders.improper_count} de ${orders.total_orders} O.S. abertas (${percentLabel(orders.improper_percent)}) foram indevidas`
          : "Nenhuma O.S. a campo aberta no período."
      }
    >
      {orders.improper_count ? (
        <>
          <ul className="flex flex-wrap gap-2">
            {orders.by_reason.map((item) => (
              <li key={item.reason} className="rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
                {item.reason}: {item.count}
              </li>
            ))}
          </ul>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border border-slate-200 text-sm">
              <thead>
                <tr className="bg-sky-100 text-left text-[10px] uppercase tracking-wide text-slate-600">
                  <th className="px-3 py-2 font-semibold">O.S.</th>
                  <th className="px-3 py-2 font-semibold">Aberta em</th>
                  <th className="px-3 py-2 font-semibold">Cliente</th>
                  <th className="px-3 py-2 font-semibold">Diagnóstico</th>
                  <th className="px-3 py-2 font-semibold">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {orders.orders.map((order) => (
                  <tr key={order.order_code} className="border-t border-slate-100 odd:bg-white even:bg-slate-50">
                    <td className="px-3 py-1.5 font-semibold tabular-nums text-slate-900">{order.order_code}</td>
                    <td className="px-3 py-1.5 tabular-nums">{dateTimeOf(order.opened_at)}</td>
                    <td className="px-3 py-1.5">{order.customer_name ?? "-"}</td>
                    <td className="px-3 py-1.5">{order.diagnosis ?? `Sem diagnóstico (${order.status ?? "sem status"})`}</td>
                    <td className="px-3 py-1.5">
                      <span className="flex flex-wrap gap-1">
                        {order.reasons.map((reason) => (
                          <span key={reason} className="rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-700">
                            {reason}
                          </span>
                        ))}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {orders.truncated ? <p className="mt-1 text-[11px] text-slate-500">Mostrando as 200 primeiras O.S. indevidas.</p> : null}
          </div>
          <p className="text-[11px] text-slate-500">
            Indevida = diagnóstico de desistência, assunto errado, improdutiva ou duplicada, ou outra O.S. a campo do mesmo cliente aberta nas 72 h anteriores.
          </p>
        </>
      ) : null}
    </CollapsibleSection>
  );
}
