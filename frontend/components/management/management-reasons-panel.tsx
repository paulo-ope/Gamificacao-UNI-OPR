"use client";

import { Loader2, Pencil, Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { ManagementCaseReason } from "@/lib/types";

type ReasonDraft = {
  id: number | "new";
  name: string;
  description: string;
  active: boolean;
  requires_description: boolean;
};

const EMPTY_DRAFT: ReasonDraft = { id: "new", name: "", description: "", active: true, requires_description: false };

export function ManagementReasonsPanel() {
  const [reasons, setReasons] = useState<ManagementCaseReason[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<ReasonDraft | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReasons(await api.managementCaseReasons(true));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar os motivos.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (!draft || !draft.name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        active: draft.active,
        requires_description: draft.requires_description,
      };
      if (draft.id === "new") {
        await api.createManagementCaseReason(payload);
        setMessage("Motivo criado.");
      } else {
        await api.updateManagementCaseReason(draft.id, payload);
        setMessage("Motivo atualizado.");
      }
      setDraft(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar o motivo.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(reason: ManagementCaseReason) {
    setSaving(true);
    setError(null);
    try {
      await api.updateManagementCaseReason(reason.id, { active: !reason.active });
      await load();
    } catch (reason_) {
      setError(reason_ instanceof Error ? reason_.message : "Falha ao atualizar o motivo.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4">
      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-950">Motivos de justificativa</h3>
          <p className="mt-1 text-sm text-slate-500">
            Opções que o supervisor vê ao justificar um caso (dia vermelho do calendário ou produtividade abaixo da meta).
          </p>
        </div>
        <Button type="button" onClick={() => setDraft(EMPTY_DRAFT)}>
          <Plus className="h-4 w-4" /> Novo motivo
        </Button>
      </div>

      {loading ? (
        <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
      ) : (
        <div className="grid gap-2">
          {reasons.map((reason) => (
            <div
              key={reason.id}
              className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-900">{reason.name}</p>
                  {!reason.active ? <Badge className="border-slate-200 bg-slate-100 text-slate-500">Inativo</Badge> : null}
                  {reason.requires_description ? (
                    <Badge className="border-amber-200 bg-amber-50 text-amber-700">Exige descrição (min. 15 caracteres)</Badge>
                  ) : null}
                </div>
                {reason.description ? <p className="mt-1 text-sm text-slate-500">{reason.description}</p> : null}
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setDraft({
                      id: reason.id,
                      name: reason.name,
                      description: reason.description ?? "",
                      active: reason.active,
                      requires_description: reason.requires_description,
                    })
                  }
                >
                  <Pencil className="h-3.5 w-3.5" /> Editar
                </Button>
                <Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => void toggleActive(reason)}>
                  {reason.active ? "Desativar" : "Ativar"}
                </Button>
              </div>
            </div>
          ))}
          {!reasons.length ? <p className="text-sm text-slate-400">Nenhum motivo cadastrado ainda.</p> : null}
        </div>
      )}

      {draft
        ? createPortal(
            <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <h4 className="text-base font-semibold text-slate-950">{draft.id === "new" ? "Novo motivo" : "Editar motivo"}</h4>
              <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="mt-4 grid gap-3">
              <Input
                placeholder="Nome do motivo"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
              <Textarea
                rows={3}
                placeholder="Descrição (opcional) - aparece como ajuda abaixo do motivo na tela de justificativa."
                value={draft.description}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              />
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={draft.requires_description}
                  onChange={(event) => setDraft({ ...draft, requires_description: event.target.checked })}
                />
                Exige justificativa detalhada (mínimo de 15 caracteres)
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={draft.active}
                  onChange={(event) => setDraft({ ...draft, active: event.target.checked })}
                />
                Ativo (aparece na lista de motivos)
              </label>
              <div className="mt-2 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setDraft(null)}>
                  Cancelar
                </Button>
                <Button type="button" disabled={saving || !draft.name.trim()} onClick={() => void save()}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Salvar
                </Button>
              </div>
            </div>
          </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
