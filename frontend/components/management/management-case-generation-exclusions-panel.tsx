"use client";

import { Loader2, Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { ManagementCaseGenerationExclusion, ManagementOperationalMember } from "@/lib/types";

type ScopeType = "member" | "regional";

type Draft = {
  scope_type: ScopeType;
  member_id: number | null;
  member_search: string;
  member_options: ManagementOperationalMember[];
  regional: string;
  date_from: string;
  date_to: string;
  reason: string;
};

const EMPTY_DRAFT: Draft = {
  scope_type: "member",
  member_id: null,
  member_search: "",
  member_options: [],
  regional: "",
  date_from: "",
  date_to: "",
  reason: "",
};

function formatDate(value: string | null): string {
  if (!value) return "";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`));
}

export function ManagementCaseGenerationExclusionsPanel() {
  const [items, setItems] = useState<ManagementCaseGenerationExclusion[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [memberSearchLoading, setMemberSearchLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.managementCaseGenerationExclusions(includeInactive));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar as exclusões.");
    } finally {
      setLoading(false);
    }
  }, [includeInactive]);

  useEffect(() => {
    void load();
  }, [load]);

  async function searchMembers(search: string) {
    if (!draft) return;
    setDraft({ ...draft, member_search: search });
    if (search.trim().length < 2) {
      setDraft((current) => (current ? { ...current, member_options: [] } : current));
      return;
    }
    setMemberSearchLoading(true);
    try {
      const dashboard = await api.managementDashboard({ search: search.trim() });
      setDraft((current) => (current ? { ...current, member_options: dashboard.members.slice(0, 8) } : current));
    } catch {
      // Busca é só uma conveniência de UI - falha aqui não deve travar o formulário.
    } finally {
      setMemberSearchLoading(false);
    }
  }

  async function save() {
    if (!draft || !draft.reason.trim()) return;
    if (draft.scope_type === "member" && !draft.member_id) return;
    if (draft.scope_type === "regional" && !draft.regional.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.createManagementCaseGenerationExclusion({
        scope_type: draft.scope_type,
        member_id: draft.scope_type === "member" ? draft.member_id : null,
        regional: draft.scope_type === "regional" ? draft.regional.trim() : null,
        date_from: draft.date_from || null,
        date_to: draft.date_to || null,
        reason: draft.reason.trim(),
      });
      setMessage("Exclusão criada.");
      setDraft(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao criar a exclusão.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(item: ManagementCaseGenerationExclusion) {
    setSaving(true);
    setError(null);
    try {
      await api.updateManagementCaseGenerationExclusion(item.id, { active: !item.active });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar a exclusão.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4">
      <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-950">Exclusões de cobrança</h3>
          <p className="mt-1 text-sm text-slate-500">
            Suspende a geração de caso (automática E manual, via &quot;Justificar dia/mês&quot;) pra um colaborador
            específico ou uma regional inteira, num período opcional. Não muda o modelo de equipe nem desativa o
            cadastro do colaborador.
          </p>
        </div>
        <Button type="button" onClick={() => setDraft(EMPTY_DRAFT)}>
          <Plus className="h-4 w-4" /> Nova exclusão
        </Button>
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={includeInactive} onChange={(event) => setIncludeInactive(event.target.checked)} />
        Mostrar também as desativadas
      </label>

      {loading ? (
        <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
      ) : (
        <div className="grid gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-900">
                    {item.scope_type === "member"
                      ? `${item.member_responsible_name ?? "Colaborador removido"} (${item.member_regional ?? "—"})`
                      : `Regional: ${item.regional}`}
                  </p>
                  {!item.active ? <Badge className="border-slate-200 bg-slate-100 text-slate-500">Inativa</Badge> : null}
                  <Badge className="border-slate-200 bg-slate-50 text-slate-600">
                    {item.date_from || item.date_to
                      ? `${formatDate(item.date_from) || "início"} → ${formatDate(item.date_to) || "sem fim"}`
                      : "Permanente"}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-slate-500">{item.reason}</p>
                <p className="mt-1 text-xs text-slate-400">
                  Criada por {item.created_by_name ?? "—"} em {formatDate(item.created_at.slice(0, 10))}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => void toggleActive(item)}>
                  {item.active ? "Desativar" : "Reativar"}
                </Button>
              </div>
            </div>
          ))}
          {!items.length ? <p className="text-sm text-slate-400">Nenhuma exclusão cadastrada.</p> : null}
        </div>
      )}

      {draft
        ? createPortal(
            <div
              className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
              role="dialog"
              aria-modal="true"
            >
              <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
                <div className="flex items-start justify-between gap-4">
                  <h4 className="text-base font-semibold text-slate-950">Nova exclusão</h4>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-4 grid gap-3">
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={draft.scope_type === "member" ? "default" : "outline"}
                      onClick={() => setDraft({ ...draft, scope_type: "member", regional: "" })}
                    >
                      Colaborador
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={draft.scope_type === "regional" ? "default" : "outline"}
                      onClick={() => setDraft({ ...draft, scope_type: "regional", member_id: null })}
                    >
                      Regional inteira
                    </Button>
                  </div>

                  {draft.scope_type === "member" ? (
                    <div className="grid gap-1">
                      <Input
                        placeholder="Buscar colaborador por nome…"
                        value={draft.member_search}
                        onChange={(event) => void searchMembers(event.target.value)}
                      />
                      {memberSearchLoading ? <p className="text-xs text-slate-400">Buscando…</p> : null}
                      {draft.member_options.length ? (
                        <div className="grid gap-1 rounded-lg border border-slate-200 p-1">
                          {draft.member_options.map((member) => (
                            <button
                              key={member.id}
                              type="button"
                              className={`rounded-md px-2 py-1.5 text-left text-sm hover:bg-slate-50 ${
                                draft.member_id === member.id ? "bg-blue-50 text-blue-800" : "text-slate-700"
                              }`}
                              onClick={() =>
                                setDraft({
                                  ...draft,
                                  member_id: member.id,
                                  member_search: `${member.responsible_name} (${member.regional})`,
                                  member_options: [],
                                })
                              }
                            >
                              {member.responsible_name} — {member.regional}
                            </button>
                          ))}
                        </div>
                      ) : null}
                      {draft.member_id ? <p className="text-xs text-emerald-700">Colaborador selecionado.</p> : null}
                    </div>
                  ) : (
                    <Input
                      placeholder="Nome da regional (ex.: UNI JARU)"
                      value={draft.regional}
                      onChange={(event) => setDraft({ ...draft, regional: event.target.value })}
                    />
                  )}

                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1">
                      <label className="text-xs font-medium text-slate-500">De (opcional)</label>
                      <Input
                        type="date"
                        value={draft.date_from}
                        onChange={(event) => setDraft({ ...draft, date_from: event.target.value })}
                      />
                    </div>
                    <div className="grid gap-1">
                      <label className="text-xs font-medium text-slate-500">Até (vazio = permanente)</label>
                      <Input
                        type="date"
                        value={draft.date_to}
                        onChange={(event) => setDraft({ ...draft, date_to: event.target.value })}
                      />
                    </div>
                  </div>

                  <Textarea
                    rows={3}
                    placeholder="Motivo (obrigatório) - ex.: férias, atestado, filial nova sem estrutura validada."
                    value={draft.reason}
                    onChange={(event) => setDraft({ ...draft, reason: event.target.value })}
                  />

                  <div className="mt-2 flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={() => setDraft(null)}>
                      Cancelar
                    </Button>
                    <Button
                      type="button"
                      disabled={
                        saving ||
                        draft.reason.trim().length < 5 ||
                        (draft.scope_type === "member" ? !draft.member_id : !draft.regional.trim())
                      }
                      onClick={() => void save()}
                    >
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
