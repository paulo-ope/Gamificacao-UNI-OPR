"use client";

import { useState } from "react";
import { RotateCcw, Save, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { AdminWorkspaceModuleSettingsPatch } from "@/lib/types";

import type { VisibleModuleRow } from "./admin-shared";

type Props = {
  module: VisibleModuleRow;
  saving: boolean;
  onClose: () => void;
  onSave: (patch: AdminWorkspaceModuleSettingsPatch) => Promise<void>;
};

const STATUS_OPTIONS = [
  { value: "active", label: "Ativo", hint: "Aparece na navegação de quem tem a permissão mínima." },
  { value: "planned", label: "Planejado", hint: "Fica fora da navegação, sem sumir da Administração." },
  { value: "disabled", label: "Desativado", hint: "Sai da navegação de todos, inclusive de quem tem a permissão." },
] as const;

/**
 * Parametrização de um módulo do ecossistema.
 *
 * O que NÃO está aqui é intencional (ver `backend/app/modules/admin/modules_service.py`): rota web,
 * prefixo de API e permissão mínima continuam vindo do código. As rotas do backend validam as
 * próprias permissões, escritas em código, então trocar a permissão mínima por aqui deixaria o
 * módulo visível para quem vai levar 403 em tudo lá dentro.
 */
export function ModuleSettingsDrawer({ module, saving, onClose, onSave }: Props) {
  const [name, setName] = useState(module.name);
  const [description, setDescription] = useState(module.description);
  const [status, setStatus] = useState(module.status);
  const [sortOrder, setSortOrder] = useState(String(module.sort_order ?? 0));
  const [error, setError] = useState<string | null>(null);

  const usesDefaultName = name.trim() === module.default_name;
  const usesDefaultDescription = description.trim() === module.default_description;

  async function submit(patch: AdminWorkspaceModuleSettingsPatch) {
    setError(null);
    try {
      await onSave(patch);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar o módulo.");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="module-settings-title"
    >
      <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 id="module-settings-title" className="text-lg font-semibold text-slate-950">
              Parametrizar módulo
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              {module.key} · {module.web_path} · permissão mínima {module.required_permission}
            </p>
          </div>
          <Button type="button" size="icon" variant="ghost" aria-label="Fechar parametrização do módulo" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        <div className="mt-4 grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="module-name">Nome exibido</Label>
            <Input id="module-name" value={name} onChange={(event) => setName(event.target.value)} />
            {!usesDefaultName ? (
              <button
                type="button"
                className="justify-self-start text-xs font-medium text-blue-600 hover:underline"
                onClick={() => setName(module.default_name)}
              >
                Voltar ao padrão: {module.default_name}
              </button>
            ) : null}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="module-description">Descrição</Label>
            <Textarea
              id="module-description"
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            {!usesDefaultDescription ? (
              <button
                type="button"
                className="justify-self-start text-left text-xs font-medium text-blue-600 hover:underline"
                onClick={() => setDescription(module.default_description)}
              >
                Voltar ao padrão do código
              </button>
            ) : null}
          </div>

          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium text-slate-800">Status</legend>
            {STATUS_OPTIONS.map((option) => (
              <label
                key={option.value}
                className="flex items-start gap-2 rounded-md border border-slate-200 p-3 text-sm hover:bg-slate-50"
              >
                <input
                  type="radio"
                  name="module-status"
                  className="mt-1"
                  checked={status === option.value}
                  onChange={() => setStatus(option.value)}
                />
                <span>
                  <span className="font-medium text-slate-800">{option.label}</span>
                  <span className="block text-xs text-slate-500">{option.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>

          <div className="grid gap-2">
            <Label htmlFor="module-order">Ordem na navegação</Label>
            <Input
              id="module-order"
              type="number"
              min={0}
              max={999}
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
            />
            <p className="text-xs text-slate-500">
              Menor número aparece primeiro, na barra lateral e na grade de módulos. Empate mantém a ordem
              do código.
            </p>
          </div>
        </div>

        {error ? (
          <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={saving || !module.customized}
            title={module.customized ? undefined : "Este módulo já está com os valores do código."}
            onClick={() =>
              void submit({ name: null, description: null, status: null, sort_order: null })
            }
          >
            <RotateCcw className="h-4 w-4" /> Restaurar tudo do padrão
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={saving}
              onClick={() =>
                void submit({
                  name,
                  description,
                  status,
                  sort_order: Number.isNaN(Number(sortOrder)) ? null : Number(sortOrder),
                })
              }
            >
              <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar módulo"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
