"use client";

import { Check, Pencil, Settings2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { localizaApi } from "@/lib/localiza-api";

// Pedido do usuário: parametrizar a validade do link sem precisar editar `.env`/reiniciar o
// backend, mas SEM ocupar um card inteiro do tamanho do formulário (achado de UX: "ficou com cara
// de sistema amador") - vira uma linha compacta, só um número e um lápis, que expande pra editar.
// Só quem tem `localiza:manage` chega até aqui (gate já feito na página).
export function LocalizaSettingsPanel() {
  const [ttlHours, setTtlHours] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    localizaApi
      .getSettings()
      .then((settings) => {
        if (active) setTtlHours(settings.link_ttl_hours);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  function startEditing() {
    setDraft(String(ttlHours ?? ""));
    setError(null);
    setEditing(true);
  }

  async function save() {
    const hours = Number(draft);
    if (!Number.isFinite(hours) || hours < 1 || hours > 720) {
      setError("Entre 1 e 720 horas (30 dias).");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await localizaApi.updateSettings({ link_ttl_hours: hours });
      setTtlHours(updated.link_ttl_hours);
      setEditing(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600">
      <Settings2 className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
      {editing ? (
        <>
          <span>Validade do link:</span>
          <Input
            type="number"
            min={1}
            max={720}
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void save();
              if (event.key === "Escape") setEditing(false);
            }}
            className="h-7 w-16 px-2 py-0 text-xs"
          />
          <span>horas</span>
          <button type="button" onClick={save} disabled={saving} className="text-emerald-600 hover:text-emerald-700" title="Salvar">
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button type="button" onClick={() => setEditing(false)} className="text-slate-400 hover:text-slate-600" title="Cancelar">
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </>
      ) : (
        <>
          <span>
            Validade do link: <span className="font-medium text-slate-950">{ttlHours ?? "..."}h</span>
          </span>
          <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-slate-500" onClick={startEditing}>
            <Pencil className="h-3 w-3" aria-hidden="true" />
          </Button>
        </>
      )}
      {error ? <span className="text-rose-600">{error}</span> : null}
    </div>
  );
}
