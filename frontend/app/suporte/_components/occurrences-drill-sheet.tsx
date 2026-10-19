"use client";

import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import type { SupportOccurrence } from "@/lib/types";

import { dayLabel, durationLabel, ixcDateTime, number, regionalLabel } from "./occurrences-format";

// Painel lateral aberto por qualquer clique da visão geral (KPI, destaque, gráfico, mapa de calor ou
// item de lista): mostra as ocorrências por trás do número, com o relato e a finalização completos.

const PAGE_SIZE = 50;

export type OccurrenceSelection = {
  title: string;
  regional?: string;
  diagnosis?: string;
  status?: "open" | "finalized";
  day?: string;
  hour?: number;
  q?: string;
};

type Props = {
  selection: OccurrenceSelection | null;
  dateFrom: string;
  dateTo: string;
  /** Regional escolhida no filtro da tela; o clique pode sobrescrever. */
  regional: string;
  onClose: () => void;
};

function filterSummary(selection: OccurrenceSelection, dateFrom: string, dateTo: string) {
  const parts: string[] = [];
  if (selection.day) parts.push(`Dia ${dayLabel(selection.day)}`);
  else parts.push(`${dayLabel(dateFrom)} a ${dayLabel(dateTo)}`);
  if (selection.hour != null) parts.push(`Abertas às ${String(selection.hour).padStart(2, "0")}h`);
  if (selection.regional) parts.push(regionalLabel(selection.regional));
  if (selection.diagnosis) parts.push(selection.diagnosis);
  if (selection.status) parts.push(selection.status === "open" ? "Em aberto" : "Finalizadas");
  return parts.join(" · ");
}

function OccurrenceCard({ item }: { item: SupportOccurrence }) {
  return (
    <li className="rounded-xl border border-slate-200 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
        {item.is_open ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-700">Em aberto há {durationLabel(item.open_minutes)}</span>
        ) : (
          <span className="rounded-full bg-sky-100 px-2 py-0.5 font-semibold text-sky-700">Finalizada</span>
        )}
        <span className="font-semibold text-slate-800">{regionalLabel(item.regional)}</span>
        {item.city ? <span>{item.city}</span> : null}
        <span className="tabular-nums">Protocolo {item.protocol ?? item.source_id}</span>
        <span>{item.is_open ? "Aguardando finalização" : (item.diagnosis_name ?? "Sem diagnóstico")}</span>
      </div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Relato · aberta em {ixcDateTime(item.created_at)}</p>
      <p className="mb-3 mt-1 whitespace-pre-line text-sm text-slate-800">{item.report ?? "Sem relato"}</p>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {item.is_open
          ? "Finalização"
          : `Finalização · ${item.finalized_at ? `${ixcDateTime(item.finalized_at)} · resolvida em ${durationLabel(item.resolution_minutes)}` : "horário não registrado"}`}
      </p>
      <p className="mt-1 whitespace-pre-line text-sm text-slate-800">
        {item.is_open ? <span className="text-slate-400">Ainda não finalizada.</span> : (item.finalization_report ?? <span className="text-slate-400">Finalizada sem relato.</span>)}
      </p>
      {item.customer_name ? <p className="mt-2 text-xs text-slate-500">Cliente: {item.customer_name}</p> : null}
    </li>
  );
}

export function OccurrencesDrillSheet({ selection, dateFrom, dateTo, regional, onClose }: Props) {
  const [items, setItems] = useState<SupportOccurrence[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [offset, setOffset] = useState(0);

  // Nova seleção: recomeça do início.
  useEffect(() => {
    setItems([]);
    setTotal(0);
    setOffset(0);
  }, [selection]);

  useEffect(() => {
    if (!selection) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportOccurrences({
        date_from: selection.day ?? dateFrom,
        date_to: selection.day ?? dateTo,
        regional: selection.regional ?? regional,
        diagnosis: selection.diagnosis,
        status: selection.status,
        hour: selection.hour,
        q: selection.q,
        limit: PAGE_SIZE,
        offset,
      })
      .then((page) => {
        if (cancelled) return;
        setTotal(page.total);
        setItems((current) => (offset === 0 ? page.items : [...current, ...page.items]));
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar as ocorrências. Tente novamente.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selection, dateFrom, dateTo, regional, offset, retry]);

  return (
    <Sheet open={selection !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent className="sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{selection?.title ?? "Ocorrências"}</SheetTitle>
          <SheetDescription>
            {selection ? filterSummary(selection, dateFrom, dateTo) : ""}
            {!loading && !error ? ` · ${number(total)} ${total === 1 ? "ocorrência" : "ocorrências"}` : ""}
          </SheetDescription>
        </SheetHeader>
        <div className="grid gap-3 p-6">
          {error ? (
            <div className="flex items-center gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
              <AlertCircle size={18} aria-hidden="true" />
              <p className="mr-auto">{error}</p>
              <Button variant="outline" size="sm" onClick={() => setRetry((current) => current + 1)}>Tentar novamente</Button>
            </div>
          ) : null}
          {!loading && !error && !items.length ? (
            <p className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
              <CheckCircle2 size={18} aria-hidden="true" />Nenhuma ocorrência neste recorte.
            </p>
          ) : null}
          <ul className="grid gap-3">{items.map((item) => <OccurrenceCard key={item.id} item={item} />)}</ul>
          {loading ? (
            <p className="flex items-center justify-center gap-2 py-6 text-sm text-slate-500" role="status">
              <Loader2 className="animate-spin" size={16} aria-hidden="true" />Carregando…
            </p>
          ) : null}
          {!loading && items.length < total ? (
            <Button variant="outline" onClick={() => setOffset(items.length)}>Carregar mais ({number(total - items.length)} restantes)</Button>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
