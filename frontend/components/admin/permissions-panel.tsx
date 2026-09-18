"use client";

import { useMemo, useState } from "react";
import { KeyRound, Pencil, Plus, Search, ShieldAlert, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { workspaceModules } from "@/lib/module-registry";
import type { EcosystemPermission, EcosystemPermissionDraft } from "@/lib/types";

type Props = {
  permissions: EcosystemPermission[];
  canWritePermissions: boolean;
  saving: boolean;
  onCreate: (draft: EcosystemPermissionDraft) => Promise<void>;
  onUpdate: (key: string, draft: EcosystemPermissionDraft) => Promise<void>;
  onDelete: (permission: EcosystemPermission) => Promise<void>;
};

type OriginFilter = "all" | "system" | "custom";

function blankDraft(): EcosystemPermissionDraft {
  return { key: "", label: "", module_key: "", description: "", sensitive: false };
}

/**
 * Catálogo de permissões do ecossistema, com o uso de cada uma e o ciclo de vida das permissões
 * próprias.
 *
 * A tela é explícita sobre a fronteira que o backend impõe (ver `permissions_service.py`):
 * permissão **do sistema** vem do código, é o que as rotas exigem, e por isso pode ser revogada
 * dos perfis mas não excluída do catálogo; permissão **própria** é criada aqui e é excluível
 * enquanto nenhum perfil a usar. Sem dizer isso na tela, "não consigo excluir" volta como bug.
 */
export function PermissionsPanel({ permissions, canWritePermissions, saving, onCreate, onUpdate, onDelete }: Props) {
  const [search, setSearch] = useState("");
  const [origin, setOrigin] = useState<OriginFilter>("all");
  const [draft, setDraft] = useState<EcosystemPermissionDraft | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const customCount = permissions.filter((item) => item.custom).length;
  const unusedCount = permissions.filter((item) => item.profile_count === 0).length;

  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    return permissions.filter((item) => {
      const matchesOrigin =
        origin === "all" || (origin === "custom" ? item.custom : !item.custom);
      const matchesTerm =
        !term || `${item.key} ${item.label} ${item.module}`.toLocaleLowerCase("pt-BR").includes(term);
      return matchesOrigin && matchesTerm;
    });
  }, [permissions, search, origin]);

  const grouped = useMemo(() => {
    return filtered.reduce<Record<string, EcosystemPermission[]>>((groups, item) => {
      groups[item.module] = [...(groups[item.module] || []), item];
      return groups;
    }, {});
  }, [filtered]);

  function openCreate() {
    setFormError(null);
    setEditingKey(null);
    setDraft(blankDraft());
  }

  function openEdit(permission: EcosystemPermission) {
    setFormError(null);
    setEditingKey(permission.key);
    setDraft({
      key: permission.key,
      label: permission.label,
      module_key: permission.module_key || "",
      description: permission.description || "",
      sensitive: permission.sensitive,
    });
  }

  async function submitDraft() {
    if (!draft) return;
    setFormError(null);
    try {
      if (editingKey) await onUpdate(editingKey, draft);
      else await onCreate(draft);
      setDraft(null);
      setEditingKey(null);
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Não foi possível salvar a permissão.");
    }
  }

  return (
    // `min-w-0` em toda a cadeia até o contêiner que rola: item de grid nasce com
    // `min-width: auto`, ou seja, não encolhe abaixo da largura do próprio conteúdo. Sem isto, a
    // tabela de 860px esticava o card e a PÁGINA rolava de lado no celular em vez de a tabela
    // rolar dentro do card (achado real medido em 375px: `body.scrollWidth` 918 contra 375 de tela).
    <div className="grid min-w-0 gap-4">
      <div className="min-w-0 rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-blue-600" />
              <h3 className="text-lg font-semibold text-slate-950">Catálogo de permissões</h3>
            </div>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              Toda permissão do ecossistema, com quantos perfis e quantas pessoas dependem dela hoje —
              para você saber quem é afetado antes de revogar ou excluir.
            </p>
          </div>
          {canWritePermissions ? (
            <Button type="button" onClick={openCreate}>
              <Plus className="h-4 w-4" /> Nova permissão própria
            </Button>
          ) : null}
        </div>

        <div className="grid border-b border-slate-200 bg-slate-50 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Permissões no catálogo", value: permissions.length },
            { label: "Do sistema (em código)", value: permissions.length - customCount },
            { label: "Próprias (criadas aqui)", value: customCount },
            { label: "Sem nenhum perfil", value: unusedCount },
          ].map((item) => (
            <div
              key={item.label}
              className="border-b border-slate-200 px-5 py-4 last:border-b-0 sm:[&:nth-child(odd)]:border-r xl:border-b-0 xl:border-r xl:last:border-r-0"
            >
              <p className="text-2xl font-semibold text-slate-950">{item.value}</p>
              <p className="text-xs text-slate-500">{item.label}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-3 border-b border-slate-200 p-5 md:flex-row md:items-center md:justify-between">
          <div className="relative w-full md:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={search}
              className="pl-9"
              placeholder="Buscar chave, rótulo ou módulo"
              aria-label="Buscar permissão"
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por origem">
            {(
              [
                { value: "all", label: "Todas" },
                { value: "system", label: "Do sistema" },
                { value: "custom", label: "Próprias" },
              ] as Array<{ value: OriginFilter; label: string }>
            ).map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={origin === option.value ? "default" : "outline"}
                onClick={() => setOrigin(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid min-w-0 gap-5 p-5">
          {Object.entries(grouped).map(([module, items]) => (
            <section key={module} className="min-w-0" aria-labelledby={`permission-group-${module}`}>
              <div className="flex items-center justify-between gap-3">
                <h4 id={`permission-group-${module}`} className="font-semibold text-slate-950">
                  {module}
                </h4>
                <span className="text-xs text-slate-500">{items.length} permissões</span>
              </div>
              <div className="mt-3 overflow-x-auto">
                <Table className="min-w-[860px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Permissão</TableHead>
                      <TableHead>Origem</TableHead>
                      <TableHead>Perfis</TableHead>
                      <TableHead>Pessoas</TableHead>
                      <TableHead className="text-right">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((permission) => (
                      <TableRow key={permission.key}>
                        <TableCell>
                          <div className="flex items-center gap-1.5 font-medium text-slate-950">
                            {permission.label}
                            {permission.sensitive ? (
                              <span
                                className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700"
                                title="Fica fora do 'Selecionar módulo' em lote: exige marcar individualmente no perfil."
                              >
                                <ShieldAlert className="h-3 w-3" aria-hidden="true" /> Sensível
                              </span>
                            ) : null}
                          </div>
                          <div className="break-all text-[11px] text-slate-400">{permission.key}</div>
                          {permission.description ? (
                            <div className="mt-1 text-xs text-slate-500">{permission.description}</div>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          {permission.custom ? (
                            <Badge className="bg-blue-50 text-blue-700">Própria</Badge>
                          ) : (
                            <Badge className="border border-slate-200 bg-white text-slate-600">Do sistema</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-slate-600">
                          {permission.profile_count === 0 ? (
                            <span className="text-slate-400">nenhum</span>
                          ) : (
                            <span title={permission.profile_names.join(", ")}>{permission.profile_count}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-slate-600">{permission.user_count}</TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            {permission.custom && canWritePermissions ? (
                              <>
                                <Button type="button" size="sm" variant="outline" onClick={() => openEdit(permission)}>
                                  <Pencil className="h-3.5 w-3.5" /> Editar
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="text-red-600"
                                  disabled={saving}
                                  onClick={() => void onDelete(permission)}
                                >
                                  <Trash2 className="h-3.5 w-3.5" /> Excluir
                                </Button>
                              </>
                            ) : (
                              <span className="text-xs text-slate-400">
                                {permission.custom ? "sem permissão para editar" : "definida em código"}
                              </span>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          ))}
          {Object.keys(grouped).length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-500">
              Nenhuma permissão encontrada para a busca informada.
            </div>
          ) : null}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
        <p className="font-semibold text-slate-800">Como as duas origens se comportam</p>
        <ul className="mt-2 grid gap-1.5">
          <li>
            <strong>Do sistema</strong>: declarada no código e exigida pelas rotas do backend. Pode ser
            concedida e revogada de qualquer perfil, mas não pode ser excluída do catálogo — apagar o
            rótulo não apagaria a exigência da rota, só deixaria a tela sem explicação.
          </li>
          <li>
            <strong>Própria</strong>: criada aqui. Serve para marcar acesso que os perfis concedem e que
            integrações e telas podem ler. Não passa a proteger uma rota do backend por si só, porque
            rota é código. É excluível enquanto nenhum perfil a estiver usando.
          </li>
        </ul>
      </div>

      {draft ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 p-0 sm:items-center sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="permission-form-title"
        >
          <div className="w-full max-w-xl rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl">
            <div className="flex items-start justify-between gap-3">
              <h3 id="permission-form-title" className="text-lg font-semibold text-slate-950">
                {editingKey ? `Editar permissão: ${editingKey}` : "Nova permissão própria"}
              </h3>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label="Fechar formulário de permissão"
                onClick={() => setDraft(null)}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>

            <div className="mt-4 grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="permission-key">Chave</Label>
                <Input
                  id="permission-key"
                  value={draft.key}
                  disabled={Boolean(editingKey)}
                  placeholder="localiza:exportar"
                  onChange={(event) => setDraft({ ...draft, key: event.target.value })}
                />
                <p className="text-xs text-slate-500">
                  {editingKey
                    ? "A chave não muda: os perfis já a referenciam por texto. Se estiver errada, exclua e crie de novo."
                    : "Formato modulo:acao, só letras minúsculas, números e _ (exemplo: localiza:exportar)."}
                </p>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="permission-label">Rótulo na tela</Label>
                <Input
                  id="permission-label"
                  value={draft.label}
                  placeholder="UNI Localiza: exportar solicitações"
                  onChange={(event) => setDraft({ ...draft, label: event.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="permission-module">Agrupar no módulo</Label>
                <select
                  id="permission-module"
                  value={draft.module_key}
                  onChange={(event) => setDraft({ ...draft, module_key: event.target.value })}
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
                >
                  <option value="">Sem módulo (agrupa pelo prefixo da chave)</option>
                  {workspaceModules.map((module) => (
                    <option key={module.key} value={module.key}>
                      {module.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="permission-description">Para que serve (opcional)</Label>
                <Textarea
                  id="permission-description"
                  value={draft.description}
                  rows={2}
                  placeholder="Quem tem esta permissão pode..."
                  onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                />
              </div>
              <label className="flex items-start gap-2 rounded-md border border-slate-200 p-3 text-sm">
                <AppCheckbox
                  checked={draft.sensitive}
                  onCheckedChange={(checked) => setDraft({ ...draft, sensitive: checked })}
                  ariaLabel="Permissão sensível"
                />
                <span>
                  <span className="font-medium text-slate-800">Permissão sensível</span>
                  <span className="block text-xs text-slate-500">
                    Fica fora do botão &quot;Selecionar módulo&quot; na tela de Perfis — só entra num perfil
                    com clique individual.
                  </span>
                </span>
              </label>
            </div>

            {formError ? (
              <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {formError}
              </p>
            ) : null}

            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setDraft(null)}>
                Cancelar
              </Button>
              <Button type="button" disabled={saving} onClick={() => void submitDraft()}>
                {saving ? "Salvando..." : "Salvar permissão"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
