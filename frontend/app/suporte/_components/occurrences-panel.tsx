"use client";

import { AlertCircle, ChevronLeft, ChevronRight, ClipboardList, LayoutDashboard, ListChecks, Loader2, RefreshCw, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { SupportOccurrencePage } from "@/lib/types";

import { IxcPeriodBar, useIxcPeriod } from "./ixc-n1-panel";
import { OccurrencesOverview } from "./occurrences-overview";
import { durationLabel, ixcDateTime, number, regionalLabel } from "./occurrences-format";

// Ocorrências (assunto 211 do IXC): Visão geral (análises) e Registros (lista com relato, diagnóstico
// e finalização). Só leitura - o filtro do assunto, o escopo regional do usuário e os cálculos vivem
// no backend (`occurrences_service.py`).

const PAGE_SIZE = 25;
const DIAGNOSIS_NONE = "Sem diagnóstico";

type View = "overview" | "records";
type StatusFilter = "all" | "open" | "finalized";

function Report({ text, fallback }: { text: string | null; fallback: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return <span className="text-slate-400">{fallback}</span>;
  return (
    <button
      type="button"
      className={`w-full whitespace-pre-line text-left text-sm text-slate-800 ${expanded ? "" : "line-clamp-3"}`}
      aria-expanded={expanded}
      title={expanded ? "Recolher" : "Ver completo"}
      onClick={() => setExpanded((current) => !current)}
    >
      {text}
    </button>
  );
}

type RecordsProps = {
  dateFrom: string;
  dateTo: string;
  regional: string;
  onRegionalChange: (value: string) => void;
  revision: number;
};

function OccurrencesRecords({ dateFrom, dateTo, regional, onRegionalChange, revision }: RecordsProps) {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [diagnosis, setDiagnosis] = useState("");
  const [page, setPage] = useState(0);
  const [retry, setRetry] = useState(0);
  const [data, setData] = useState<SupportOccurrencePage | null>(null);
  const [diagnoses, setDiagnoses] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  // Lista de diagnósticos do período para o filtro (vem da visão geral, já agregada no backend).
  useEffect(() => {
    if (!dateFrom || !dateTo || dateFrom > dateTo) return;
    let cancelled = false;
    api
      .supportOccurrencesOverview({ date_from: dateFrom, date_to: dateTo })
      .then((result) => {
        if (!cancelled) setDiagnoses(result.by_diagnosis.map((row) => row.name ?? DIAGNOSIS_NONE));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, revision]);

  useEffect(() => {
    if (!dateFrom || !dateTo || dateFrom > dateTo) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .supportOccurrences({ date_from: dateFrom, date_to: dateTo, regional, q: search, status, diagnosis, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar as ocorrências. Tente novamente ou contate o administrador.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, regional, search, status, diagnosis, page, revision, retry]);

  const total = data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const items = data?.items ?? [];

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-2xl bg-white p-4 shadow-sm">
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          Situação
          <Select value={status} onChange={(event) => { setStatus(event.target.value as StatusFilter); setPage(0); }}>
            <option value="all">Todas</option>
            <option value="open">Em aberto</option>
            <option value="finalized">Finalizadas</option>
          </Select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          Diagnóstico
          <Select value={diagnosis} onChange={(event) => { setDiagnosis(event.target.value); setPage(0); }}>
            <option value="">Todos</option>
            {diagnosis && !diagnoses.includes(diagnosis) ? <option value={diagnosis}>{diagnosis}</option> : null}
            {diagnoses.map((name) => <option key={name} value={name}>{name}</option>)}
          </Select>
        </label>
        <label className="grid min-w-[220px] flex-1 gap-1 text-xs font-medium text-slate-600">
          Buscar no relato
          <span className="relative">
            <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <Input className="pl-8" value={searchInput} placeholder="Relato, finalização, protocolo ou cliente" maxLength={120} onChange={(event) => setSearchInput(event.target.value)} />
          </span>
        </label>
      </div>

      {data?.by_regional.length ? (
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" aria-label="Ocorrências por regional">
          {data.by_regional.map((item) => (
            <li key={item.regional}>
              <button
                type="button"
                className={`w-full rounded-2xl bg-white p-3 text-left shadow-sm transition hover:shadow ${regional === item.regional ? "ring-2 ring-sky-500" : ""}`}
                aria-pressed={regional === item.regional}
                onClick={() => { onRegionalChange(regional === item.regional ? "" : item.regional); setPage(0); }}
              >
                <p className="truncate text-xs font-medium uppercase tracking-wide text-slate-500" title={item.regional}>{regionalLabel(item.regional)}</p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-slate-950">{number(item.count)}</p>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {error && !loading ? (
        <div className="flex items-center gap-3 rounded-2xl bg-rose-50 p-4 text-sm text-rose-800" role="alert">
          <AlertCircle size={20} aria-hidden="true" />
          <p className="mr-auto">{error}</p>
          <Button variant="outline" size="sm" onClick={() => setRetry((current) => current + 1)}>Tentar novamente</Button>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-2xl bg-white p-2 shadow-sm">
        <Table>
          <caption className="sr-only">Registros de ocorrências do IXC com relato, diagnóstico e finalização</caption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Abertura</TableHead>
              <TableHead scope="col">Protocolo</TableHead>
              <TableHead scope="col">Regional</TableHead>
              <TableHead scope="col">Situação</TableHead>
              <TableHead scope="col">Diagnóstico</TableHead>
              <TableHead scope="col" className="min-w-[280px]">Relato</TableHead>
              <TableHead scope="col" className="min-w-[280px]">Finalização</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="py-12 text-center text-slate-500">
                  <Loader2 className="mx-auto mb-2 animate-spin" size={20} aria-hidden="true" />
                  Carregando ocorrências…
                </TableCell>
              </TableRow>
            ) : null}
            {!loading && !error && !items.length ? (
              <TableRow>
                <TableCell colSpan={7} className="py-12 text-center text-slate-500">Nenhuma ocorrência encontrada com esses filtros.</TableCell>
              </TableRow>
            ) : null}
            {!loading && items.map((item) => (
              <TableRow key={item.id} className="align-top">
                <TableCell className="whitespace-nowrap">{ixcDateTime(item.created_at)}</TableCell>
                <TableCell className="whitespace-nowrap tabular-nums">{item.protocol ?? item.source_id}</TableCell>
                <TableCell>
                  {regionalLabel(item.regional)}
                  {item.city ? <p className="text-xs text-slate-500">{item.city}</p> : null}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  {item.is_open ? (
                    <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-semibold text-orange-700">Em aberto · {durationLabel(item.open_minutes)}</span>
                  ) : (
                    <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700">Finalizada</span>
                  )}
                </TableCell>
                <TableCell>
                  {item.is_open ? (
                    <span className="text-slate-400">Aguardando finalização</span>
                  ) : (
                    (item.diagnosis_name ?? <span className="text-slate-400">{DIAGNOSIS_NONE}</span>)
                  )}
                </TableCell>
                <TableCell>
                  <Report text={item.report} fallback="Sem relato" />
                  {item.customer_name ? <p className="mt-1 text-xs text-slate-500">{item.customer_name}</p> : null}
                </TableCell>
                <TableCell>
                  {item.is_open ? (
                    <span className="text-slate-400">Ainda não finalizada</span>
                  ) : (
                    <>
                      <p className="text-xs font-semibold text-slate-700">
                        {item.finalized_at ? `${ixcDateTime(item.finalized_at)} · resolvida em ${durationLabel(item.resolution_minutes)}` : "Horário não registrado"}
                      </p>
                      <Report text={item.finalization_report} fallback="Finalizada sem relato" />
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-600">
        <span>{number(total)} {total === 1 ? "ocorrência" : "ocorrências"}</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={loading || page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))}>
            <ChevronLeft size={14} aria-hidden="true" />
            Anterior
          </Button>
          <span className="tabular-nums">Página {page + 1} de {lastPage + 1}</span>
          <Button variant="outline" size="sm" disabled={loading || page >= lastPage} onClick={() => setPage((current) => Math.min(lastPage, current + 1))}>
            Próxima
            <ChevronRight size={14} aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}

const VIEWS: { value: View; label: string; icon: typeof ClipboardList }[] = [
  { value: "overview", label: "Visão geral", icon: LayoutDashboard },
  { value: "records", label: "Registros", icon: ListChecks },
];

export function OccurrencesPanel() {
  const [view, setView] = useState<View>("overview");
  // Mesmo período compartilhado dos Indicadores do Suporte e do Atendimento N1/N2.
  const [period, setPeriod] = useIxcPeriod();
  const { date_from: dateFrom, date_to: dateTo } = period;
  const [regional, setRegional] = useState("");
  const [revision, setRevision] = useState(0);
  const [regionalOptions, setRegionalOptions] = useState<string[]>([]);

  const invalidPeriod = !dateFrom || !dateTo || dateTo < dateFrom;

  // Regionais do período para o filtro (a lista é a mesma da visão geral, sem filtrar por regional).
  useEffect(() => {
    if (invalidPeriod) return;
    let cancelled = false;
    api
      .supportOccurrencesOverview({ date_from: dateFrom, date_to: dateTo })
      .then((result) => {
        if (!cancelled) setRegionalOptions(result.by_regional.map((row) => row.regional ?? ""));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, invalidPeriod, revision]);

  return (
    <section className="grid gap-3" aria-label="Registros de Ocorrências">
      <IxcPeriodBar period={period} onChange={setPeriod} />

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <ClipboardList className="h-4 w-4 text-slate-400" aria-hidden="true" />
        <Select className="h-8 w-56 text-xs" aria-label="Regional" value={regional} onChange={(event) => setRegional(event.target.value)}>
          <option value="">Todas as regionais</option>
          {regional && !regionalOptions.includes(regional) ? <option value={regional}>{regionalLabel(regional)}</option> : null}
          {regionalOptions.map((name) => <option key={name} value={name}>{regionalLabel(name)}</option>)}
        </Select>
        <p className="mr-auto text-xs text-slate-500">Atendimentos do IXC com o assunto 211 (Registro de Ocorrências): relato, filial, diagnóstico e finalização.</p>
        <Button variant="outline" size="sm" onClick={() => setRevision((current) => current + 1)}>
          <RefreshCw size={14} aria-hidden="true" />
          Atualizar
        </Button>
      </div>

      <div role="tablist" aria-label="Visões das ocorrências" className="flex gap-2">
        {VIEWS.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={view === value}
            className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition ${view === value ? "bg-slate-900 text-white" : "bg-white text-slate-700 shadow-sm hover:bg-slate-50"}`}
            onClick={() => setView(value)}
          >
            <Icon size={15} aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {invalidPeriod ? <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800" role="alert">Informe um período válido: a data inicial não pode ser maior que a final.</p> : null}

      {!invalidPeriod && view === "overview" ? <OccurrencesOverview dateFrom={dateFrom} dateTo={dateTo} regional={regional} revision={revision} /> : null}
      {!invalidPeriod && view === "records" ? (
        <OccurrencesRecords dateFrom={dateFrom} dateTo={dateTo} regional={regional} onRegionalChange={setRegional} revision={revision} />
      ) : null}
    </section>
  );
}
