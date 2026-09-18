"use client";

import { Bookmark, BookmarkPlus, Check, Loader2, Star, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { SupportIxcTicketSavedFilter, SupportIxcTicketSavedFilterValues } from "@/lib/types";

// Item 10 do plano de evolução analítica do Atendimento IXC (2026-09-17): "poder salvar visão e
// ela ser padrão ou não" - SEMPRE pessoal (decisão do usuário, sem escopo "global" aqui, diferente
// de `OpaSavedFiltersBar`). Chama `onDefaultLoaded` uma vez, na carga inicial, se existir uma
// visão marcada como padrão - quem usa este componente decide o que fazer com ela (normalmente
// aplicar os filtros automaticamente).
export function IxcTicketSavedFiltersBar({
  current,
  onApply,
  onDefaultLoaded,
}: {
  current: SupportIxcTicketSavedFilterValues;
  onApply: (filters: SupportIxcTicketSavedFilterValues) => void;
  onDefaultLoaded?: (filters: SupportIxcTicketSavedFilterValues) => void;
}) {
  const [items, setItems] = useState<SupportIxcTicketSavedFilter[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .supportIxcSavedFilters()
      .then((list) => {
        setItems(list);
        const defaultFilter = list.find((item) => item.is_default);
        if (defaultFilter) onDefaultLoaded?.(defaultFilter.filters);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
    // Só na montagem - aplicar o padrão de novo a cada troca de filtro criaria um loop
    // (o próprio onApply chamado pelo usuário mudaria `current`, o que re-disparia o efeito).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.createSupportIxcSavedFilter({ name: trimmed, filters: current });
      setItems((existing) => [...existing, created]);
      setName("");
      setFormOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar a visão.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleDefault(item: SupportIxcTicketSavedFilter) {
    setError(null);
    try {
      const updated = await api.setSupportIxcSavedFilterDefault(item.id, !item.is_default);
      setItems((existing) => existing.map((current) => ({ ...current, is_default: current.id === updated.id ? updated.is_default : false })));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao definir a visão padrão.");
    }
  }

  async function remove(id: number) {
    setError(null);
    try {
      await api.deleteSupportIxcSavedFilter(id);
      setItems((existing) => existing.filter((item) => item.id !== id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao remover a visão.");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
        <Bookmark className="h-3 w-3 text-blue-600" />
        Visões salvas
      </span>

      {loading ? <Loader2 className="h-3 w-3 animate-spin text-slate-400" /> : null}
      {!loading && !items.length ? <span className="text-[11px] text-slate-400">nenhuma ainda</span> : null}

      {items.map((item) => (
        <span
          key={item.id}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
            item.is_default ? "border-amber-300 bg-amber-50 text-amber-800" : "border-slate-200 bg-slate-50 text-slate-700"
          }`}
        >
          <button type="button" onClick={() => onApply(item.filters)} className="max-w-40 truncate font-medium hover:underline">
            {item.name}
          </button>
          <button
            type="button"
            onClick={() => void toggleDefault(item)}
            aria-label={item.is_default ? `Remover ${item.name} como padrão` : `Definir ${item.name} como padrão`}
            title={item.is_default ? "Padrão ao abrir a tela" : "Definir como padrão ao abrir a tela"}
            className={item.is_default ? "text-amber-500" : "text-slate-400 hover:text-amber-500"}
          >
            <Star className="h-3 w-3" fill={item.is_default ? "currentColor" : "none"} />
          </button>
          <button type="button" onClick={() => void remove(item.id)} aria-label={`Remover visão ${item.name}`} className="text-slate-400 hover:text-slate-700">
            <Trash2 className="h-3 w-3" />
          </button>
        </span>
      ))}

      <Button type="button" variant="outline" size="sm" className="h-7 border-dashed px-2 text-[11px]" onClick={() => setFormOpen((current) => !current)} aria-expanded={formOpen}>
        <BookmarkPlus className="h-3 w-3" />
        Salvar filtro atual
      </Button>

      {formOpen ? (
        <div className="mt-1 flex w-full flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 p-2">
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Nome da visão"
            className="h-8 w-full max-w-56 text-sm"
            onKeyDown={(event) => {
              if (event.key === "Enter") void save();
            }}
          />
          <Button type="button" size="sm" className="h-8" disabled={saving || !name.trim()} onClick={() => void save()}>
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Salvar
          </Button>
          <Button type="button" variant="ghost" size="sm" className="h-8 text-slate-500" onClick={() => setFormOpen(false)}>
            Cancelar
          </Button>
        </div>
      ) : null}

      {error ? <p className="w-full text-[11px] text-red-600">{error}</p> : null}
    </div>
  );
}
