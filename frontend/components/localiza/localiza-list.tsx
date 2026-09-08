"use client";

import { Check, Copy, Search, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { commonDateRangePresets, DateRangePicker } from "@/components/ui/date-range-picker";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { distanceClassificationLabel, distanceClassificationTone, formatDistanceMeters, googleMapsUrl } from "@/lib/geo-distance";
import type { LocationRequest, LocationRequestStatus } from "@/lib/localiza-api";
import { LOCALIZA_STATUS_LABELS, LOCALIZA_STATUS_TONE, formatPortoVelho, localizaRequestLabel } from "./localiza-format";

const STATUS_FILTER_OPTIONS: Array<{ value: LocationRequestStatus | ""; label: string }> = [
  { value: "", label: "Todos os status" },
  { value: "pending", label: "Pendente" },
  { value: "confirmed", label: "Confirmado" },
  { value: "invalidated", label: "Invalidado" },
  { value: "expired", label: "Expirado" },
];

export type LocalizaListScope = "mine" | "all";

export function LocalizaList({
  items,
  loading,
  scope,
  onScopeChange,
  search,
  onSearchChange,
  dateFrom,
  dateTo,
  onDateChange,
  status,
  onStatusChange,
  onSelect,
}: {
  items: LocationRequest[];
  loading: boolean;
  scope: LocalizaListScope;
  onScopeChange: (scope: LocalizaListScope) => void;
  search: string;
  onSearchChange: (value: string) => void;
  dateFrom: string;
  dateTo: string;
  onDateChange: (key: "date_from" | "date_to", value: string) => void;
  status: LocationRequestStatus | "";
  onStatusChange: (value: LocationRequestStatus | "") => void;
  onSelect: (item: LocationRequest) => void;
}) {
  // Pedido do usuário (2026-09-08): copiar a localização sem precisar abrir o painel de detalhe -
  // um botão direto na linha, com o mesmo link pronto pro Google Maps/WhatsApp que o painel usa.
  const [copiedId, setCopiedId] = useState<number | null>(null);

  async function copyLocation(event: React.MouseEvent, item: LocationRequest) {
    event.stopPropagation();
    if (item.confirmed_latitude === null || item.confirmed_longitude === null) return;
    try {
      await navigator.clipboard.writeText(googleMapsUrl(item.confirmed_latitude, item.confirmed_longitude));
      setCopiedId(item.id);
      setTimeout(() => setCopiedId((current) => (current === item.id ? null : current)), 2000);
    } catch {
      // Falha de permissão de clipboard é rara e não crítica aqui - o painel de detalhe tem o
      // mesmo botão como caminho alternativo, sem precisar duplicar tratamento de erro na linha.
    }
  }

  const hasActiveFilters = Boolean(search || dateFrom || dateTo || status);
  function clearFilters() {
    onSearchChange("");
    onDateChange("date_from", "");
    onDateChange("date_to", "");
    onStatusChange("");
  }

  // "Solicitado por" é sempre a mesma pessoa em "Meus links" - some a coluna nesse caso, ela só
  // ajuda a distinguir quando o recorte é "Todos" (pedido do usuário: evitar informação redundante
  // poluindo a tabela).
  const showRequesterColumn = scope === "all";
  const columnCount = showRequesterColumn ? 8 : 7;

  return (
    <Card className="min-w-0 rounded-2xl border-slate-200 shadow-sm">
      <CardHeader className="grid gap-3 border-b border-slate-100 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Solicitações de localização</CardTitle>
          <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
            <Button
              type="button"
              size="sm"
              variant={scope === "mine" ? "default" : "ghost"}
              className="h-8 px-3 text-xs"
              onClick={() => onScopeChange("mine")}
            >
              Meus links
            </Button>
            <Button
              type="button"
              size="sm"
              variant={scope === "all" ? "default" : "ghost"}
              className="h-8 px-3 text-xs"
              onClick={() => onScopeChange("all")}
            >
              Todos
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div className="grid min-w-[220px] flex-1 gap-1">
            <label className="text-[11px] font-medium text-slate-500">Buscar</label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
              <Input
                className="pl-8"
                placeholder="O.S., protocolo OPA, cliente ou código"
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
              />
            </div>
          </div>
          <DateRangePicker label="Período" dateFrom={dateFrom} dateTo={dateTo} presets={commonDateRangePresets()} onChange={onDateChange} />
          <div className="grid gap-1">
            <label className="text-[11px] font-medium text-slate-500">Status</label>
            <select
              value={status}
              onChange={(event) => onStatusChange(event.target.value as LocationRequestStatus | "")}
              className="h-10 rounded-md border border-input bg-white px-3 text-sm text-slate-700"
            >
              {STATUS_FILTER_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          {hasActiveFilters ? (
            <Button type="button" variant="ghost" size="sm" className="h-8 px-2 text-xs text-blue-700" onClick={clearFilters}>
              <X className="h-3.5 w-3.5" aria-hidden="true" /> Limpar filtros
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="min-w-0 overflow-x-auto p-0">
        <Table className="min-w-[820px]">
          <TableHeader>
            <TableRow>
              <TableHead>Solicitação</TableHead>
              <TableHead>Cliente</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Divergência</TableHead>
              {showRequesterColumn ? <TableHead>Solicitado por</TableHead> : null}
              <TableHead>Criado em</TableHead>
              <TableHead>Expira em</TableHead>
              <TableHead>Localização</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="py-8 text-center text-sm text-slate-400">
                  Carregando...
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columnCount} className="py-8 text-center text-sm text-slate-400">
                  {scope === "mine" ? "Você ainda não gerou nenhum link nesse recorte." : "Nenhuma solicitação encontrada."}
                </TableCell>
              </TableRow>
            ) : (
              items.map((item) => (
                <TableRow key={item.id} className="cursor-pointer hover:bg-slate-50" onClick={() => onSelect(item)}>
                  <TableCell className="font-medium text-slate-950">{localizaRequestLabel(item)}</TableCell>
                  <TableCell>{item.customer_name || "-"}</TableCell>
                  <TableCell>
                    <StatusBadge tone={LOCALIZA_STATUS_TONE[item.status]} dot>
                      {LOCALIZA_STATUS_LABELS[item.status]}
                    </StatusBadge>
                  </TableCell>
                  <TableCell>
                    {item.distance_from_registered_meters !== null && item.distance_classification ? (
                      <span className="inline-flex items-center gap-1.5 text-xs">
                        {formatDistanceMeters(item.distance_from_registered_meters)}
                        <StatusBadge tone={distanceClassificationTone(item.distance_classification)} dot>
                          {distanceClassificationLabel(item.distance_classification)}
                        </StatusBadge>
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">-</span>
                    )}
                  </TableCell>
                  {showRequesterColumn ? (
                    <TableCell className="whitespace-nowrap text-xs text-slate-500">{item.requested_by_name || "-"}</TableCell>
                  ) : null}
                  <TableCell className="whitespace-nowrap text-xs text-slate-500">{formatPortoVelho(item.created_at)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-slate-500">{formatPortoVelho(item.expires_at)}</TableCell>
                  <TableCell>
                    {item.confirmed_latitude !== null && item.confirmed_longitude !== null ? (
                      <button
                        type="button"
                        title="Copiar link do Google Maps"
                        onClick={(event) => copyLocation(event, item)}
                        className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
                      >
                        {copiedId === item.id ? (
                          <>
                            <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> Copiado!
                          </>
                        ) : (
                          <>
                            <Copy className="h-3.5 w-3.5" aria-hidden="true" /> Copiar
                          </>
                        )}
                      </button>
                    ) : (
                      <span className="text-xs text-slate-400">-</span>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
