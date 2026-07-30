"use client";

import { Loader2, ShieldAlert, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppRadio } from "@/components/ui/radio";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatInteger, formatPercent } from "@/lib/format";
import type {
  OperationWarrantyAnalytics as OperationWarrantyAnalyticsData,
  OperationWarrantyDenominator,
  OperationWarrantyPeriodBasis,
} from "@/lib/operations-api";

const PERIOD_BASIS_OPTIONS: Array<{ value: OperationWarrantyPeriodBasis; label: string }> = [
  { value: "opened", label: "Data de abertura da manutenção" },
  { value: "closed", label: "Data de fechamento da manutenção" },
];

const DENOMINATOR_OPTIONS: Array<{
  value: OperationWarrantyDenominator;
  label: string;
  description: string;
}> = [
  {
    value: "active_origins",
    label: "Origens com garantia ativa no período",
    description: "Recomendado: mede a exposição real à garantia no período.",
  },
  {
    value: "closed_origins",
    label: "Origens fechadas no período",
    description: "Ativação/Mud. Endereço/Mud. Tecnologia fechadas dentro do período.",
  },
  {
    value: "maintenance_total",
    label: "Total de manutenções do período",
    description: "Participação da garantia dentro do volume geral de manutenção.",
  },
  {
    value: "activation_closed",
    label: "Ativações fechadas no período",
    description: "Ignora Mudança de Endereço/Tecnologia no denominador.",
  },
];

function rateTone(percentage: number | null): "success" | "warning" | "danger" | "neutral" {
  if (percentage === null) return "neutral";
  if (percentage <= 5) return "success";
  if (percentage <= 10) return "warning";
  return "danger";
}

function rateBadgeClass(tone: ReturnType<typeof rateTone>) {
  switch (tone) {
    case "success":
      return "bg-emerald-100 text-emerald-700";
    case "warning":
      return "bg-amber-100 text-amber-700";
    case "danger":
      return "bg-red-100 text-red-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

export function OperationsWarrantyAnalytics({
  data,
  isLoading,
  periodBasis,
  denominator,
  onPeriodBasisChange,
  onDenominatorChange,
}: {
  data: OperationWarrantyAnalyticsData;
  isLoading: boolean;
  periodBasis: OperationWarrantyPeriodBasis;
  denominator: OperationWarrantyDenominator;
  onPeriodBasisChange: (basis: OperationWarrantyPeriodBasis) => void;
  onDenominatorChange: (denominator: OperationWarrantyDenominator) => void;
}) {
  const tone = rateTone(data.percentage);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4 text-uni-royal" />
            Garantias de ativação
            {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" /> : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Contar a manutenção pela
              </span>
              <div className="flex flex-col gap-1.5">
                {PERIOD_BASIS_OPTIONS.map((option) => (
                  <label key={option.value} className="flex items-center gap-1.5 text-sm text-slate-700">
                    <AppRadio
                      checked={periodBasis === option.value}
                      disabled={isLoading}
                      onSelect={() => onPeriodBasisChange(option.value)}
                      ariaLabel={option.label}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Denominador do percentual
              </span>
              <div className="flex flex-col gap-1.5">
                {DENOMINATOR_OPTIONS.map((option) => (
                  <label key={option.value} className="flex items-start gap-1.5 text-sm text-slate-700">
                    <AppRadio
                      checked={denominator === option.value}
                      disabled={isLoading}
                      onSelect={() => onDenominatorChange(option.value)}
                      ariaLabel={option.label}
                      className="mt-0.5"
                    />
                    <span>
                      {option.label}
                      <span className="block text-xs font-normal text-slate-400">{option.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border bg-white p-3">
              <div className="text-xs text-slate-500">Garantias encontradas</div>
              <div className="text-2xl font-semibold text-slate-900">{formatInteger(data.numerator)}</div>
            </div>
            <div className="rounded-xl border bg-white p-3">
              <div className="text-xs text-slate-500">% Garantia</div>
              <Badge className={rateBadgeClass(tone)}>
                {data.percentage === null ? (
                  <span className="inline-flex items-center gap-1">
                    <ShieldAlert className="h-3.5 w-3.5" /> —
                  </span>
                ) : (
                  formatPercent(data.percentage)
                )}
              </Badge>
              <div className="mt-1 text-[11px] text-slate-400">
                {formatInteger(data.numerator)} / {formatInteger(data.denominator_count)}
              </div>
            </div>
            <div className="rounded-xl border bg-white p-3">
              <div className="text-xs text-slate-500">Contratos com garantia</div>
              <div className="text-2xl font-semibold text-slate-900">
                {formatInteger(data.contracts_with_warranty)}
              </div>
            </div>
            <div className="rounded-xl border bg-white p-3">
              <div className="text-xs text-slate-500">Clientes com garantia</div>
              <div className="text-2xl font-semibold text-slate-900">
                {formatInteger(data.customers_with_warranty)}
              </div>
            </div>
          </div>

          {data.breakdown.length > 0 ? (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo de origem no denominador</TableHead>
                    <TableHead className="text-center">Quantidade</TableHead>
                    <TableHead className="text-center">%</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.breakdown.map((item) => (
                    <TableRow key={item.label}>
                      <TableCell>{item.label}</TableCell>
                      <TableCell className="text-center tabular-nums">{formatInteger(item.quantity)}</TableCell>
                      <TableCell className="text-center tabular-nums">{formatPercent(item.percentage)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ranking de garantias por filial</CardTitle>
          <p className="text-xs font-normal text-slate-400">
            % Garantia de cada filial sobre o próprio denominador selecionado acima — não é a
            fatia da filial sobre o total de garantias.
          </p>
        </CardHeader>
        <CardContent>
          {data.by_regional.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-center text-sm text-slate-400">
              Nenhuma garantia ou denominador encontrado com os filtros atuais.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>Filial</TableHead>
                    <TableHead className="text-center">Garantias</TableHead>
                    <TableHead className="text-center">Denominador</TableHead>
                    <TableHead className="text-center">% Garantia</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.by_regional.map((item, index) => (
                    <TableRow key={item.label}>
                      <TableCell className="tabular-nums text-slate-400">{index + 1}</TableCell>
                      <TableCell>{item.label}</TableCell>
                      <TableCell className="text-center tabular-nums font-semibold">
                        {formatInteger(item.quantity)}
                      </TableCell>
                      <TableCell className="text-center tabular-nums">
                        {formatInteger(item.denominator_count)}
                      </TableCell>
                      <TableCell className="text-center tabular-nums">
                        {item.percentage === null ? "—" : formatPercent(item.percentage)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Garantias encontradas no período</CardTitle>
        </CardHeader>
        <CardContent>
          {data.items_truncated ? (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Exibindo as {data.items.length} garantias mais recentes. Reduza o período ou aplique
              mais filtros para ver a lista completa.
            </div>
          ) : null}
          {data.items.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-center text-sm text-slate-400">
              Nenhuma garantia encontrada com os filtros atuais.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>Contrato</TableHead>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Regional</TableHead>
                    <TableHead>O.S. origem</TableHead>
                    <TableHead>Tipo de origem</TableHead>
                    <TableHead>O.S. retorno</TableHead>
                    <TableHead>Diagnóstico</TableHead>
                    <TableHead>Fechamento origem</TableHead>
                    <TableHead>Abertura retorno</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((item) => (
                    <TableRow key={`${item.origin_order_code}-${item.return_order_code}`}>
                      <TableCell>{item.contract_id || "—"}</TableCell>
                      <TableCell>{item.customer_name || "—"}</TableCell>
                      <TableCell>{item.regional || "—"}</TableCell>
                      <TableCell>{item.origin_order_code}</TableCell>
                      <TableCell>{item.origin_os_type || "—"}</TableCell>
                      <TableCell>{item.return_order_code}</TableCell>
                      <TableCell>{item.diagnosis || "—"}</TableCell>
                      <TableCell>{formatDateTime(item.origin_closed_at)}</TableCell>
                      <TableCell>{formatDateTime(item.return_opened_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
