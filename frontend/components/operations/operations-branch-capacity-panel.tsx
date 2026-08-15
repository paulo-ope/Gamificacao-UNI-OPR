"use client";

import { Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import {
  operationsApi,
  type OperationBranchCapacity,
  type OperationBranchCapacityUpdate,
} from "@/lib/operations-api";

// Valores usados quando a filial ainda não tem capacidade cadastrada - só um ponto de partida
// editável antes do primeiro "Salvar", não um registro real no banco ainda.
const DEFAULT_DRAFT: OperationBranchCapacityUpdate = {
  good_threshold: 2500,
  great_threshold: 3000,
  excellent_threshold: 3500,
  good_color: "#dcfce7",
  great_color: "#dbeafe",
  excellent_color: "#ede9fe",
};

type Draft = {
  good_threshold: number;
  great_threshold: number;
  excellent_threshold: number;
  good_color: string;
  great_color: string;
  excellent_color: string;
};

export function OperationsBranchCapacityPanel({
  regionals,
  canManage,
}: {
  regionals: string[];
  canManage: boolean;
}) {
  const [saved, setSaved] = useState<Record<string, OperationBranchCapacity>>({});
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [savingRegional, setSavingRegional] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    operationsApi
      .branchCapacities()
      .then((items) => {
        if (!active) return;
        const byRegional: Record<string, OperationBranchCapacity> = {};
        for (const item of items) byRegional[item.regional] = item;
        setSaved(byRegional);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Falha ao carregar capacidades por filial.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const sortedRegionals = useMemo(() => [...regionals].sort((a, b) => a.localeCompare(b, "pt-BR")), [regionals]);

  function draftFor(regional: string): Draft {
    if (drafts[regional]) return drafts[regional];
    const existing = saved[regional];
    return existing
      ? {
          good_threshold: existing.good_threshold,
          great_threshold: existing.great_threshold,
          excellent_threshold: existing.excellent_threshold,
          good_color: existing.good_color,
          great_color: existing.great_color,
          excellent_color: existing.excellent_color,
        }
      : { ...DEFAULT_DRAFT };
  }

  function updateDraft(regional: string, patch: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [regional]: { ...draftFor(regional), ...patch } }));
  }

  async function saveRegional(regional: string) {
    const draft = draftFor(regional);
    // Limiares podem estar vazios (NaN) se o usuário limpou o campo pra digitar de novo - nunca
    // mandar isso pra API, cai no valor já salvo (ou no padrão, se ainda não existe nenhum).
    const fallback = saved[regional] ?? DEFAULT_DRAFT;
    const payload: OperationBranchCapacityUpdate = {
      good_threshold: Number.isFinite(draft.good_threshold) ? draft.good_threshold : fallback.good_threshold,
      great_threshold: Number.isFinite(draft.great_threshold) ? draft.great_threshold : fallback.great_threshold,
      excellent_threshold: Number.isFinite(draft.excellent_threshold)
        ? draft.excellent_threshold
        : fallback.excellent_threshold,
      good_color: draft.good_color,
      great_color: draft.great_color,
      excellent_color: draft.excellent_color,
    };
    setSavingRegional(regional);
    setError(null);
    setMessage(null);
    try {
      const result = await operationsApi.updateBranchCapacity(regional, payload);
      setSaved((current) => ({ ...current, [regional]: result }));
      setMessage(`Capacidade de "${regional}" salva.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Falha ao salvar a capacidade de "${regional}".`);
    } finally {
      setSavingRegional(null);
    }
  }

  if (loading) {
    return <p className="p-4 text-sm text-slate-500">Carregando capacidades por filial…</p>;
  }

  return (
    <div className="grid min-w-0 gap-3 p-4">
      <p className="text-xs text-slate-500">
        Configure, por filial, a partir de quantos serviços no período ela é considerada Capacidade Boa, Ótima ou
        Excelente. É um indicador gerencial da filial inteira - independente das metas por modelo de equipe que já
        pintam cada célula do calendário.
      </p>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {message && <p className="text-xs text-emerald-600">{message}</p>}
      {sortedRegionals.length === 0 ? (
        <p className="text-sm text-slate-400">Nenhuma filial encontrada nos vínculos de colaborador atuais.</p>
      ) : (
        <div className="grid gap-3">
          {sortedRegionals.map((regional) => {
            const draft = draftFor(regional);
            const isNew = !saved[regional];
            return (
              <div key={regional} className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">
                    {regional}
                    {isNew && <span className="ml-2 text-[10px] font-normal text-slate-400">(sem capacidade cadastrada)</span>}
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    disabled={!canManage || savingRegional === regional}
                    onClick={() => void saveRegional(regional)}
                  >
                    <Save className="h-3.5 w-3.5" />
                    {savingRegional === regional ? "Salvando…" : "Salvar"}
                  </Button>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  <label
                    className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                    style={{ backgroundColor: draft.good_color }}
                  >
                    <span className="block">Capacidade Boa</span>
                    <Input
                      type="number"
                      min={0}
                      disabled={!canManage}
                      value={numericInputValue(draft.good_threshold)}
                      onChange={(event) => updateDraft(regional, { good_threshold: parseNumericInput(event.target.value) })}
                      className="mt-1 h-8 bg-white/70"
                    />
                    <input
                      aria-label={`Cor capacidade boa - ${regional}`}
                      type="color"
                      value={draft.good_color}
                      disabled={!canManage}
                      onChange={(event) => updateDraft(regional, { good_color: event.target.value })}
                      className="mt-2 h-7 w-full cursor-pointer rounded border bg-white p-1"
                    />
                  </label>
                  <label
                    className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                    style={{ backgroundColor: draft.great_color }}
                  >
                    <span className="block">Capacidade Ótima</span>
                    <Input
                      type="number"
                      min={0}
                      disabled={!canManage}
                      value={numericInputValue(draft.great_threshold)}
                      onChange={(event) => updateDraft(regional, { great_threshold: parseNumericInput(event.target.value) })}
                      className="mt-1 h-8 bg-white/70"
                    />
                    <input
                      aria-label={`Cor capacidade ótima - ${regional}`}
                      type="color"
                      value={draft.great_color}
                      disabled={!canManage}
                      onChange={(event) => updateDraft(regional, { great_color: event.target.value })}
                      className="mt-2 h-7 w-full cursor-pointer rounded border bg-white p-1"
                    />
                  </label>
                  <label
                    className="rounded-lg border p-2 text-[10px] font-semibold text-slate-600"
                    style={{ backgroundColor: draft.excellent_color }}
                  >
                    <span className="block">Capacidade Excelente</span>
                    <Input
                      type="number"
                      min={0}
                      disabled={!canManage}
                      value={numericInputValue(draft.excellent_threshold)}
                      onChange={(event) =>
                        updateDraft(regional, { excellent_threshold: parseNumericInput(event.target.value) })
                      }
                      className="mt-1 h-8 bg-white/70"
                    />
                    <input
                      aria-label={`Cor capacidade excelente - ${regional}`}
                      type="color"
                      value={draft.excellent_color}
                      disabled={!canManage}
                      onChange={(event) => updateDraft(regional, { excellent_color: event.target.value })}
                      className="mt-2 h-7 w-full cursor-pointer rounded border bg-white p-1"
                    />
                  </label>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
