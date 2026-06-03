"use client";

import { BarChart3, CalendarDays, Database, FileSpreadsheet, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { ChangeEvent, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime, formatInteger } from "@/lib/format";
import type { ImportPreview, ImportResult, ServiceOrderDeletePeriodResult, ServiceOrderPeriodSummary } from "@/lib/types";

type UpvalueImportPanelProps = {
  onImported: () => Promise<void>;
  onRecalculate: () => Promise<void>;
  onAnalyzePeriod: (month: number, year: number) => Promise<void>;
  currentPeriod?: {
    reference_month?: number | null;
    reference_year?: number | null;
  };
  busy?: boolean;
  canImport?: boolean;
  canCalculate?: boolean;
};

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function periodKey(period: ServiceOrderPeriodSummary) {
  return `${period.reference_year}-${String(period.reference_month).padStart(2, "0")}`;
}

function periodLabel(period: Pick<ServiceOrderPeriodSummary, "reference_month" | "reference_year">) {
  return `${String(period.reference_month).padStart(2, "0")}/${period.reference_year}`;
}

function periodConfirmation(period: Pick<ServiceOrderPeriodSummary, "reference_month" | "reference_year">) {
  return `APAGAR ${periodLabel(period)}`;
}

export function UpvalueImportPanel({
  onImported,
  onRecalculate,
  onAnalyzePeriod,
  currentPeriod,
  busy,
  canImport = false,
  canCalculate = false
}: UpvalueImportPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [periods, setPeriods] = useState<ServiceOrderPeriodSummary[]>([]);
  const [selectedPeriodKey, setSelectedPeriodKey] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteResult, setDeleteResult] = useState<ServiceOrderDeletePeriodResult | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [importing, setImporting] = useState(false);
  const [loadingPeriods, setLoadingPeriods] = useState(false);
  const [deletingPeriod, setDeletingPeriod] = useState(false);
  const [calculatingPeriodKey, setCalculatingPeriodKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [periodError, setPeriodError] = useState<string | null>(null);

  const activePeriodKey = useMemo(() => {
    if (!currentPeriod?.reference_month || !currentPeriod?.reference_year) {
      return null;
    }
    return `${currentPeriod.reference_year}-${String(currentPeriod.reference_month).padStart(2, "0")}`;
  }, [currentPeriod]);

  const selectedPeriod = useMemo(
    () => periods.find((period) => periodKey(period) === selectedPeriodKey) ?? null,
    [periods, selectedPeriodKey]
  );

  const sampleColumns = useMemo(() => {
    if (!preview?.sample_rows.length) {
      return [];
    }
    return Object.keys(preview.sample_rows[0]).slice(0, 8);
  }, [preview]);

  async function loadPeriodSummary() {
    setLoadingPeriods(true);
    setPeriodError(null);
    try {
      const data = await api.serviceOrderPeriodSummary();
      setPeriods(data);
    } catch (err) {
      setPeriodError(err instanceof Error ? err.message : "Não foi possível carregar os períodos importados.");
    } finally {
      setLoadingPeriods(false);
    }
  }

  useEffect(() => {
    void loadPeriodSummary();
  }, []);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
    setPreview(null);
    setResult(null);
    setError(null);

    if (!selected) {
      return;
    }

    setLoadingPreview(true);
    try {
      const previewData = await api.previewUpvalueServiceOrders(selected);
      setPreview(previewData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível ler a planilha.");
    } finally {
      setLoadingPreview(false);
    }
  }

  async function confirmImport() {
    if (!file) {
      return;
    }
    setImporting(true);
    setError(null);
    try {
      const importResult = await api.importUpvalueServiceOrders(file);
      setResult(importResult);
      await loadPeriodSummary();
      await onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível importar a planilha.");
    } finally {
      setImporting(false);
    }
  }

  async function deleteSelectedPeriod() {
    if (!selectedPeriod) {
      return;
    }

    setDeletingPeriod(true);
    setError(null);
    setPeriodError(null);
    setDeleteResult(null);
    try {
      const deleted = await api.deleteServiceOrdersPeriod({
        reference_month: selectedPeriod.reference_month,
        reference_year: selectedPeriod.reference_year,
        confirmation: deleteConfirmation
      });
      setDeleteResult(deleted);
      setSelectedPeriodKey(null);
      setDeleteConfirmation("");
      await loadPeriodSummary();
      await onImported();
    } catch (err) {
      setPeriodError(err instanceof Error ? err.message : "Não foi possível apagar o período.");
    } finally {
      setDeletingPeriod(false);
    }
  }

  async function analyzePeriod(period: ServiceOrderPeriodSummary) {
    const key = periodKey(period);
    setCalculatingPeriodKey(key);
    setPeriodError(null);
    setDeleteResult(null);
    try {
      await onAnalyzePeriod(period.reference_month, period.reference_year);
    } catch (err) {
      setPeriodError(err instanceof Error ? err.message : "Não foi possível analisar o período.");
    } finally {
      setCalculatingPeriodKey(null);
    }
  }

  return (
    <section className="panel">
      <div className="grid gap-4 border-b bg-gradient-to-r from-slate-50 via-white to-white p-5 lg:grid-cols-[1fr_auto] lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-md border bg-white px-2.5 py-1 text-xs font-semibold text-slate-700">
              <CalendarDays className="h-3.5 w-3.5" />
              Período de análise
            </span>
            {activePeriodKey ? (
              <span className="inline-flex rounded-md border border-teal-200 bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-700">
                Em uso: {currentPeriod?.reference_month && currentPeriod?.reference_year ? periodLabel({
                  reference_month: currentPeriod.reference_month,
                  reference_year: currentPeriod.reference_year
                }) : "-"}
              </span>
            ) : null}
          </div>
          <h2 className="mt-3 text-xl font-semibold text-slate-950">Escolha o mês que alimenta ranking, auditoria e gráficos</h2>
          <p className="mt-1 text-sm text-slate-500">
            Visualizadores podem trocar a análise. Importação, exclusão e recálculo ficam restritos aos perfis operacionais.
          </p>
        </div>
        {canImport && canCalculate ? (
          <Button variant="outline" onClick={onRecalculate}>
            <RefreshCw className="h-4 w-4" />
            Recalcular Pontuação
          </Button>
        ) : null}
      </div>

      <div className="grid gap-5 p-5">
        <div className="rounded-lg border bg-white">
          <div className="flex flex-col gap-2 border-b bg-slate-50/70 px-4 py-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                <Database className="h-4 w-4 text-teal-700" />
                Períodos importados
              </h3>
              <p className="text-xs text-slate-500">
                Selecione o mês que deve carregar ranking, auditoria e gráficos.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => void loadPeriodSummary()} disabled={loadingPeriods || deletingPeriod}>
              <RefreshCw className={loadingPeriods ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              Atualizar
            </Button>
          </div>

          {periodError ? (
            <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{periodError}</div>
          ) : null}

          {deleteResult ? (
            <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {formatInteger(deleteResult.deleted_service_orders)} O.S apagadas de {periodLabel(deleteResult)}.{" "}
              {formatInteger(deleteResult.deleted_calculation_runs)} apuração(ões) removida(s). Recalcule se quiser gerar um novo fechamento.
            </div>
          ) : null}

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Período</TableHead>
                  <TableHead>O.S na base</TableHead>
                  <TableHead>Primeira O.S</TableHead>
                  <TableHead>Última O.S</TableHead>
                  <TableHead className="text-right">Controle</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {periods.length ? (
                  periods.map((period) => {
                    const key = periodKey(period);
                    const selected = key === selectedPeriodKey;
                    const isActive = key === activePeriodKey;
                    const isCalculating = key === calculatingPeriodKey;
                    return (
                      <TableRow key={key} className={isActive ? "bg-teal-50/60" : undefined}>
                        <TableCell className="font-semibold">
                          <div className="flex flex-wrap items-center gap-2">
                            <span>{periodLabel(period)}</span>
                            {isActive ? (
                              <span className="rounded-full border border-teal-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-teal-700">
                                Em uso
                              </span>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>{formatInteger(period.total_service_orders)}</TableCell>
                        <TableCell>{formatDateTime(period.first_order_at)}</TableCell>
                        <TableCell>{formatDateTime(period.last_order_at)}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex flex-wrap justify-end gap-2">
                            <Button
                              type="button"
                              variant={isActive ? "default" : "outline"}
                              size="sm"
                              onClick={() => void analyzePeriod(period)}
                              disabled={busy || deletingPeriod || Boolean(calculatingPeriodKey)}
                            >
                              {isCalculating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <BarChart3 className="h-4 w-4" />}
                              {canCalculate ? "Recalcular período" : "Alterar período"}
                            </Button>
                            {canImport ? (
                              <Button
                                type="button"
                                variant={selected ? "destructive" : "outline"}
                                size="sm"
                                onClick={() => {
                                  setSelectedPeriodKey(selected ? null : key);
                                  setDeleteConfirmation("");
                                  setDeleteResult(null);
                                }}
                                disabled={deletingPeriod || Boolean(calculatingPeriodKey)}
                              >
                                <Trash2 className="h-4 w-4" />
                                Apagar período
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className="py-6 text-center text-sm text-slate-500">
                      {loadingPeriods ? "Carregando períodos..." : "Nenhuma O.S importada encontrada."}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          {canImport && selectedPeriod ? (
            <div className="grid gap-3 border-t bg-red-50/70 p-4 md:grid-cols-[1fr_auto] md:items-end">
              <div className="grid gap-2">
                <Label htmlFor="delete-period-confirmation">
                  Confirmar exclusão de {formatInteger(selectedPeriod.total_service_orders)} O.S de {periodLabel(selectedPeriod)}
                </Label>
                <Input
                  id="delete-period-confirmation"
                  value={deleteConfirmation}
                  onChange={(event) => setDeleteConfirmation(event.target.value)}
                  placeholder={periodConfirmation(selectedPeriod)}
                  disabled={deletingPeriod}
                />
                <p className="text-xs text-red-700">
                  Digite exatamente <span className="font-semibold">{periodConfirmation(selectedPeriod)}</span>. Esta ação remove apenas O.S e apurações desse período; regras e colaboradores permanecem.
                </p>
              </div>
              <Button
                type="button"
                variant="destructive"
                onClick={() => void deleteSelectedPeriod()}
                disabled={deleteConfirmation.trim().toUpperCase() !== periodConfirmation(selectedPeriod) || deletingPeriod}
              >
                {deletingPeriod ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Confirmar exclusão
              </Button>
            </div>
          ) : null}
        </div>

        {canImport && error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        ) : null}

        {canImport && loadingPreview ? (
          <div className="rounded-md border bg-slate-50 px-4 py-3 text-sm text-slate-600">
            Lendo primeiras linhas e detectando colunas...
          </div>
        ) : null}

        {canImport && result ? (
          <div className="grid gap-3 rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 sm:grid-cols-4">
            <div>
              <div className="text-xs font-medium uppercase">Importadas</div>
              <div className="text-lg font-semibold">{result.imported}</div>
            </div>
            <div>
              <div className="text-xs font-medium uppercase">Ignoradas</div>
              <div className="text-lg font-semibold">{result.ignored}</div>
            </div>
            <div>
              <div className="text-xs font-medium uppercase">Total de linhas</div>
              <div className="text-lg font-semibold">{result.summary.total_rows}</div>
            </div>
            <div>
              <div className="text-xs font-medium uppercase">Import ID</div>
              <div className="text-lg font-semibold">{result.import_id ?? "-"}</div>
            </div>
          </div>
        ) : null}

        {canImport ? (
          <div className="rounded-lg border bg-white">
            <div className="border-b bg-slate-50/70 px-4 py-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                <UploadCloud className="h-4 w-4 text-teal-700" />
                Incorporar nova base operacional
              </h3>
              <p className="text-xs text-slate-500">Área administrativa para validar e importar planilhas Excel ou CSV.</p>
            </div>
            <div className="grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-end">
              <div className="grid gap-2">
                <Label htmlFor="upvalue-file">Arquivo UpValue</Label>
                <Input
                  id="upvalue-file"
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  onChange={handleFileChange}
                  disabled={loadingPreview || importing}
                />
              </div>
              <Button onClick={confirmImport} disabled={!file || !preview || importing || loadingPreview}>
                {importing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                Confirmar Importação
              </Button>
            </div>
          </div>
        ) : null}

        {canImport && preview ? (
          <div className="grid gap-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-md border">
                <div className="flex items-center gap-2 border-b px-4 py-3 text-sm font-semibold">
                  <FileSpreadsheet className="h-4 w-4 text-teal-700" />
                  Colunas detectadas
                </div>
                <div className="max-h-56 overflow-auto p-3">
                  <div className="flex flex-wrap gap-2">
                    {preview.detected_columns.map((column) => (
                      <span key={column} className="rounded-md border bg-white px-2 py-1 text-xs text-slate-700">
                        {column}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="rounded-md border">
                <div className="border-b px-4 py-3 text-sm font-semibold">Mapeamento sugerido</div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Campo do sistema</TableHead>
                      <TableHead>Coluna UpValue</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(preview.mapped_columns).map(([field, column]) => (
                      <TableRow key={field}>
                        <TableCell className="font-medium">{field}</TableCell>
                        <TableCell>{column}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="rounded-md border">
              <div className="border-b px-4 py-3 text-sm font-semibold">Primeiras linhas</div>
              <Table>
                <TableHeader>
                  <TableRow>
                    {sampleColumns.map((column) => (
                      <TableHead key={column}>{column}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.sample_rows.slice(0, 8).map((row, index) => (
                    <TableRow key={index}>
                      {sampleColumns.map((column) => (
                        <TableCell key={column} className="max-w-48 truncate">
                          {formatValue(row[column])}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null}

        {canImport && result?.first_errors.length ? (
          <div className="rounded-md border">
            <div className="border-b px-4 py-3 text-sm font-semibold">Linhas ignoradas</div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Linha</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Dados</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.first_errors.map((item) => (
                  <TableRow key={`${item.row}-${item.reason}`}>
                    <TableCell>{item.row}</TableCell>
                    <TableCell>{item.reason}</TableCell>
                    <TableCell className="max-w-xl truncate">{JSON.stringify(item.data)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </div>
    </section>
  );
}


