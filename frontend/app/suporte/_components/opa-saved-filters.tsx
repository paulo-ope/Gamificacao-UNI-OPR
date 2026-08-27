"use client";

import { Bookmark, BookmarkPlus, Check, Globe, Loader2, Monitor, Trash2, User as UserIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { SupportOpaAttendanceFilters, SupportOpaSavedFilter, SupportOpaSavedFilterScope } from "@/lib/types";

const LOCAL_STORAGE_KEY = "sgp_suporte_filtros_locais";

/** Um filtro salvo só neste navegador. Convive com os do backend em vez de
 *  substituí-los: "local" é o rascunho rápido de quem está investigando algo
 *  agora; "pessoal"/"global" são recortes que devem sobreviver ao navegador. */
export type LocalSavedFilter = {
  id: string;
  name: string;
  filters: Record<string, string | number>;
};

function readLocal(): LocalSavedFilter[] {
  // localStorage pode lançar (janela anônima, cookies bloqueados) — nunca deixar
  // isso derrubar a tela inteira só por causa de um atalho de conveniência.
  try {
    const raw = window.localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as LocalSavedFilter[]) : [];
  } catch {
    return [];
  }
}

function writeLocal(items: LocalSavedFilter[]) {
  try {
    window.localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* sem persistência local disponível; o resto da tela segue normal */
  }
}

/** Só as chaves que representam RECORTE. Paginação e ordenação da tabela não
 *  fazem parte do filtro salvo — salvar "página 3" reabriria o recorte num
 *  estado arbitrário. */
const FILTER_KEYS = [
  "date_from",
  "date_to",
  "date_basis",
  "status",
  "channel",
  "attendant_id",
  "department_id",
  "reason_id",
  "customer",
  "search",
  "tag_id",
  "customer_id",
  "rating_min",
  "rating_max",
  "bot_human",
] as const;

export function extractSavableFilters(
  period: { date_from: string; date_to: string },
  filters: SupportOpaAttendanceFilters,
): Record<string, string | number> {
  const merged: Record<string, string | number> = {};
  const source: Record<string, unknown> = { ...filters, ...period };
  FILTER_KEYS.forEach((key) => {
    const value = source[key];
    if (value === undefined || value === null || value === "") return;
    merged[key] = typeof value === "number" ? value : String(value);
  });
  return merged;
}

export function OpaSavedFiltersBar({
  period,
  filters,
  canPublishGlobal,
  onApply,
}: {
  period: { date_from: string; date_to: string };
  filters: SupportOpaAttendanceFilters;
  canPublishGlobal: boolean;
  onApply: (saved: Record<string, string | number>) => void;
}) {
  const [remote, setRemote] = useState<SupportOpaSavedFilter[]>([]);
  const [local, setLocal] = useState<LocalSavedFilter[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"local" | SupportOpaSavedFilterScope>("local");

  useEffect(() => {
    setLocal(readLocal());
    setLoading(true);
    api
      .supportOpaSavedFilters()
      .then(setRemote)
      .catch(() => setRemote([]))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    const trimmed = name.trim();
    if (!trimmed) return;
    const payload = extractSavableFilters(period, filters);
    setError(null);

    if (scope === "local") {
      const next = [
        ...local.filter((item) => item.name !== trimmed),
        { id: `local-${trimmed}`, name: trimmed, filters: payload },
      ];
      setLocal(next);
      writeLocal(next);
      setName("");
      setFormOpen(false);
      return;
    }

    setSaving(true);
    try {
      const created = await api.createSupportOpaSavedFilter({ name: trimmed, scope, filters: payload });
      setRemote((current) => [...current, created]);
      setName("");
      setFormOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar o filtro.");
    } finally {
      setSaving(false);
    }
  }

  function removeLocal(id: string) {
    const next = local.filter((item) => item.id !== id);
    setLocal(next);
    writeLocal(next);
  }

  async function removeRemote(id: number) {
    setError(null);
    try {
      await api.deleteSupportOpaSavedFilter(id);
      setRemote((current) => current.filter((item) => item.id !== id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao remover o filtro.");
    }
  }

  const hasAny = remote.length > 0 || local.length > 0;

  return (
    <div className="border-b border-slate-100 bg-white px-4 pb-3 lg:px-7">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
          <Bookmark className="h-3 w-3 text-blue-600" />
          Filtros salvos
        </span>

        {loading ? <Loader2 className="h-3 w-3 animate-spin text-slate-400" /> : null}

        {!loading && !hasAny ? (
          <span className="text-[11px] text-slate-400">nenhum ainda</span>
        ) : null}

        {remote.map((item) => (
          <SavedChip
            key={`r-${item.id}`}
            label={item.name}
            scope={item.scope}
            onApply={() => onApply(item.filters)}
            onRemove={item.scope === "global" && !canPublishGlobal ? undefined : () => void removeRemote(item.id)}
          />
        ))}
        {local.map((item) => (
          <SavedChip
            key={item.id}
            label={item.name}
            scope="local"
            onApply={() => onApply(item.filters)}
            onRemove={() => removeLocal(item.id)}
          />
        ))}

        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 border-dashed px-2 text-[11px]"
          onClick={() => setFormOpen((current) => !current)}
          aria-expanded={formOpen}
        >
          <BookmarkPlus className="h-3 w-3" />
          Salvar recorte atual
        </Button>
      </div>

      {formOpen ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 p-2">
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Nome do recorte"
            className="h-8 w-full max-w-56 text-sm"
            onKeyDown={(event) => {
              if (event.key === "Enter") void save();
            }}
          />
          <div className="flex flex-wrap items-center gap-1">
            <ScopeOption active={scope === "local"} onClick={() => setScope("local")} icon={Monitor} label="Só neste navegador" />
            <ScopeOption active={scope === "personal"} onClick={() => setScope("personal")} icon={UserIcon} label="Minha conta" />
            {canPublishGlobal ? (
              <ScopeOption active={scope === "global"} onClick={() => setScope("global")} icon={Globe} label="Toda a operação" />
            ) : null}
          </div>
          <Button type="button" size="sm" className="h-8" disabled={saving || !name.trim()} onClick={() => void save()}>
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Salvar
          </Button>
          <Button type="button" variant="ghost" size="sm" className="h-8 text-slate-500" onClick={() => setFormOpen(false)}>
            Cancelar
          </Button>
        </div>
      ) : null}

      {error ? <p className="mt-1.5 text-[11px] text-red-600">{error}</p> : null}
    </div>
  );
}

const SCOPE_STYLE = {
  global: { icon: Globe, tone: "border-blue-200 bg-blue-50 text-blue-700", title: "Filtro da operação (todos veem)" },
  personal: { icon: UserIcon, tone: "border-slate-200 bg-slate-50 text-slate-700", title: "Filtro da sua conta (todos os dispositivos)" },
  local: { icon: Monitor, tone: "border-slate-200 bg-white text-slate-600", title: "Salvo só neste navegador" },
} as const;

function SavedChip({
  label,
  scope,
  onApply,
  onRemove,
}: {
  label: string;
  scope: "global" | "personal" | "local";
  onApply: () => void;
  onRemove?: () => void;
}) {
  const style = SCOPE_STYLE[scope];
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${style.tone}`} title={style.title}>
      <Icon className="h-3 w-3 shrink-0 opacity-70" />
      <button type="button" onClick={onApply} className="max-w-40 truncate font-medium hover:underline">
        {label}
      </button>
      {onRemove ? (
        <button type="button" onClick={onRemove} aria-label={`Remover filtro ${label}`} className="opacity-50 transition-opacity hover:opacity-100">
          <Trash2 className="h-3 w-3" />
        </button>
      ) : null}
    </span>
  );
}

function ScopeOption({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Globe;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] transition-colors ${
        active ? "border-blue-300 bg-blue-50 font-semibold text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
      }`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </button>
  );
}
