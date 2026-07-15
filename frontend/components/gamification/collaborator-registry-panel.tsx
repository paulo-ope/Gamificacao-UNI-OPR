"use client";

import { Building2, CircleAlert, Link2, Save, Trash2, UserPlus, Users2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { AppCombobox, AppInput, AppModal, AppSwitch, RowActionMenu, StatusBadge } from "@/components/gamification/config-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { normalizeRegional, regionalName } from "@/lib/regional";
import { cn } from "@/lib/utils";
import type { CollaboratorRegistry, CollaboratorRegistryItem } from "@/lib/types";

type Props = {
  registry: CollaboratorRegistry;
  regionalOptions: string[];
  onCreate: (payload: { name: string; role: string; regional: string; active: boolean; is_registered: boolean }) => Promise<void>;
  onSave: (item: CollaboratorRegistryItem) => Promise<void>;
  onDelete: (item: CollaboratorRegistryItem) => Promise<void>;
  onDeleteMany: (items: CollaboratorRegistryItem[]) => Promise<void>;
};

function replaceById(items: CollaboratorRegistryItem[], id: number, patch: Partial<CollaboratorRegistryItem>) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

function effectiveRegional(item: CollaboratorRegistryItem) {
  return normalizeRegional(item.regional || item.suggested_regional || "");
}

function statusBadge(item: CollaboratorRegistryItem) {
  if (!item.is_registered) return <StatusBadge tone="warning">Pendente</StatusBadge>;
  if (!item.active) return <StatusBadge>Inativo</StatusBadge>;
  return <StatusBadge tone="success">Cadastrado</StatusBadge>;
}

function SummaryCard({
  icon,
  label,
  value,
  hint,
  accent = "default",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
  accent?: "default" | "highlight" | "warning";
}) {
  const accentClass =
    accent === "highlight"
      ? "text-teal-700"
      : accent === "warning"
        ? "text-amber-700"
        : "text-slate-950";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        {icon}
        {label}
      </div>
      <div className={cn("mt-3 text-2xl font-semibold", accentClass)}>{value}</div>
      <div className="mt-1 text-sm text-slate-500">{hint}</div>
    </div>
  );
}

function RegionalSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const displayValue = value ? regionalName(value) : "";
  const selectOptions = Array.from(new Set([displayValue, ...options].filter(Boolean)));
  return (
    <AppCombobox
      value={displayValue}
      onChange={onChange}
      placeholder="Selecionar filial"
      ariaLabel="Selecionar filial"
      options={selectOptions.map((option) => ({
        value: option,
        label: regionalName(option),
        description: option ? `Código ${option}` : "Sem filial definida",
      }))}
    />
  );
}

export function CollaboratorRegistryPanel({ registry, regionalOptions, onCreate, onSave, onDelete, onDeleteMany }: Props) {
  const [search, setSearch] = useState("");
  const [selectedRegional, setSelectedRegional] = useState("");
  const [activeList, setActiveList] = useState("registered");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleteSelectionOpen, setDeleteSelectionOpen] = useState(false);
  const [pendingDeleteItem, setPendingDeleteItem] = useState<CollaboratorRegistryItem | null>(null);
  const [draft, setDraft] = useState({
    name: "",
    role: "Importado UpValue",
    regional: "",
    active: true,
    is_registered: true,
  });
  const [registered, setRegistered] = useState(registry.registered);
  const [unregistered, setUnregistered] = useState(registry.unregistered);
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());

  async function saveItem(item: CollaboratorRegistryItem) {
    if (savingIds.has(item.id)) return;
    setSavingIds((current) => new Set(current).add(item.id));
    try {
      await onSave(item);
    } finally {
      setSavingIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
  }

  useEffect(() => {
    setRegistered(registry.registered);
    setUnregistered(registry.unregistered);
    setSelectedIds(new Set());
  }, [registry]);

  const normalizedRegionalOptions = useMemo(
    () =>
      Array.from(
        new Set(
          regionalOptions
            .map((regional) => normalizeRegional(regional))
            .filter((regional) => regional && regional !== "NAO IDENTIFICADO" && regional !== "0" && regional !== "1")
        )
      ).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [regionalOptions]
  );

  useEffect(() => {
    if (selectedRegional && !normalizedRegionalOptions.includes(selectedRegional)) {
      setSelectedRegional("");
    }
  }, [normalizedRegionalOptions, selectedRegional]);

  const filteredRegistered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return registered.filter((item) => {
      const itemRegional = effectiveRegional(item);
      const matchesRegional = !selectedRegional || itemRegional === selectedRegional;
      const matchesSearch = !term || [item.name, item.role, itemRegional].join(" ").toLowerCase().includes(term);
      return matchesRegional && matchesSearch;
    });
  }, [registered, search, selectedRegional]);

  const filteredUnregistered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return unregistered.filter((item) => {
      const itemRegional = effectiveRegional(item);
      const suggestedRegional = normalizeRegional(item.suggested_regional || item.regional || "");
      const matchesRegional = !selectedRegional || itemRegional === selectedRegional || suggestedRegional === selectedRegional;
      const matchesSearch = !term || [item.name, item.role, itemRegional, suggestedRegional].join(" ").toLowerCase().includes(term);
      return matchesRegional && matchesSearch;
    });
  }, [search, selectedRegional, unregistered]);

  const selectedRegisteredTotal = selectedRegional
    ? registered.filter((item) => effectiveRegional(item) === selectedRegional).length
    : registered.length;
  const selectedUnregisteredTotal = selectedRegional
    ? unregistered.filter((item) => effectiveRegional(item) === selectedRegional || normalizeRegional(item.suggested_regional || item.regional || "") === selectedRegional).length
    : unregistered.length;
  const visibleItems = activeList === "registered" ? filteredRegistered : filteredUnregistered;
  const visibleSelectedItems = visibleItems.filter((item) => selectedIds.has(item.id));
  const allVisibleSelected = visibleItems.length > 0 && visibleItems.every((item) => selectedIds.has(item.id));

  function toggleSelected(id: number, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }

  function toggleAllVisible(checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      visibleItems.forEach((item) => {
        if (checked) {
          next.add(item.id);
        } else {
          next.delete(item.id);
        }
      });
      return next;
    });
  }

  async function deleteSelected() {
    if (visibleSelectedItems.length === 0) return;
    await onDeleteMany(visibleSelectedItems);
    setSelectedIds(new Set());
    setDeleteSelectionOpen(false);
  }

  return (
    <section className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          icon={<Users2 className="h-4 w-4" />}
          label="Cadastrados"
          value={String(selectedRegisteredTotal)}
          hint="Colaboradores ativos no filtro atual."
        />
        <SummaryCard
          icon={<CircleAlert className="h-4 w-4" />}
          label="Pendentes"
          value={String(selectedUnregisteredTotal)}
          hint="Nomes aguardando conferência e aprovação."
          accent={selectedUnregisteredTotal > 0 ? "warning" : "default"}
        />
        <SummaryCard
          icon={<Building2 className="h-4 w-4" />}
          label="Filiais no filtro"
          value={selectedRegional ? "1" : String(normalizedRegionalOptions.length)}
          hint={selectedRegional ? regionalName(selectedRegional) : "Cobertura total disponível para cadastro."}
        />
        <SummaryCard
          icon={<Link2 className="h-4 w-4" />}
          label="Selecionados"
          value={String(visibleSelectedItems.length)}
          hint="Itens marcados para ação em lote nesta visão."
          accent={visibleSelectedItems.length > 0 ? "highlight" : "default"}
        />
      </div>

      <div className="rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
        <div className="border-b border-slate-200 px-5 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">Colaboradores e filiais</h3>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                Defina a filial oficial do colaborador, aprove pendências importadas e mantenha o vínculo operacional consistente para os cálculos.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="border-red-200 text-red-700 hover:bg-red-50"
              onClick={() => setDeleteSelectionOpen(true)}
              disabled={visibleSelectedItems.length === 0}
            >
              <Trash2 className="h-4 w-4" />
              Apagar selecionados ({visibleSelectedItems.length})
            </Button>
          </div>
        </div>

        <div className="grid gap-4 border-b border-slate-200 bg-slate-50/80 px-5 py-5">
          <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
            <div className="grid gap-2">
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Filtrar filial</label>
              <AppCombobox
                value={selectedRegional}
                onChange={setSelectedRegional}
                placeholder="Todas as filiais"
                ariaLabel="Filtrar filial"
                options={[
                  { value: "", label: "Todas as filiais", description: "Exibe toda a base disponível." },
                  ...normalizedRegionalOptions.map((regional) => ({
                    value: regional,
                    label: regionalName(regional),
                    description: `Código ${regional}`,
                  })),
                ]}
              />
            </div>
            <div className="grid gap-2">
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Buscar colaborador</label>
              <AppInput className="h-11" placeholder="Nome ou filial" value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
          </div>

          <div className="grid gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Cadastrar novo colaborador</label>
            <div className="grid gap-3 md:grid-cols-[1.3fr_1fr_auto]">
              <AppInput className="h-11" placeholder="Nome do colaborador" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
              <RegionalSelect
                value={draft.regional || selectedRegional}
                options={normalizedRegionalOptions}
                onChange={(value) => setDraft((current) => ({ ...current, regional: value }))}
              />
              <Button
                className="h-11"
                onClick={async () => {
                  await onCreate({ ...draft, regional: draft.regional || selectedRegional });
                  setDraft({ name: "", role: "Importado UpValue", regional: "", active: true, is_registered: true });
                }}
                disabled={!draft.name.trim() || !(draft.regional || selectedRegional).trim()}
              >
                <UserPlus className="h-4 w-4" />
                Cadastrar
              </Button>
            </div>
          </div>
        </div>

        <div className="p-5">
          <Tabs
            value={activeList}
            onValueChange={(value) => {
              setActiveList(value);
              setSelectedIds(new Set());
            }}
            className="grid gap-4"
          >
            <TabsList className="grid h-auto grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-1 md:grid-cols-2">
              <TabsTrigger value="registered" className="rounded-xl px-4 py-2.5">
                Cadastrados ({filteredRegistered.length})
              </TabsTrigger>
              <TabsTrigger value="unregistered" className="rounded-xl px-4 py-2.5">
                Não cadastrados ({filteredUnregistered.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="registered" className="mt-0">
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50/80">
                      <TableHead className="w-10">
                        <AppSwitch checked={allVisibleSelected} onCheckedChange={toggleAllVisible} label={allVisibleSelected ? "Todos" : "Selecionar"} />
                      </TableHead>
                      <TableHead>Colaborador</TableHead>
                      <TableHead>Filial oficial</TableHead>
                      <TableHead>O.S vinculadas</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-40">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredRegistered.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <AppSwitch checked={selectedIds.has(item.id)} onCheckedChange={(checked) => toggleSelected(item.id, checked)} label="" />
                        </TableCell>
                        <TableCell className="min-w-56">
                          <AppInput value={item.name} onChange={(event) => setRegistered(replaceById(registered, item.id, { name: event.target.value }))} />
                        </TableCell>
                        <TableCell className="min-w-52">
                          <RegionalSelect
                            value={item.regional}
                            options={normalizedRegionalOptions}
                            onChange={(value) => setRegistered(replaceById(registered, item.id, { regional: value }))}
                          />
                        </TableCell>
                        <TableCell>{item.service_orders_count} O.S</TableCell>
                        <TableCell>{statusBadge(item)}</TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={savingIds.has(item.id)}
                              onClick={() => saveItem({ ...item, regional: regionalName(item.regional) })}
                            >
                              <Save className="h-4 w-4" />
                              {savingIds.has(item.id) ? "Salvando..." : "Salvar"}
                            </Button>
                            <RowActionMenu
                              ariaLabel={`Ações do colaborador ${item.name}`}
                              items={[
                                { label: "Apagar", onSelect: () => setPendingDeleteItem(item), tone: "danger" },
                              ]}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                    {filteredRegistered.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-6 text-center text-sm text-slate-500">
                          Nenhum colaborador cadastrado para os filtros atuais.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            <TabsContent value="unregistered" className="mt-0">
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50/80">
                      <TableHead className="w-10">
                        <AppSwitch checked={allVisibleSelected} onCheckedChange={toggleAllVisible} label={allVisibleSelected ? "Todos" : "Selecionar"} />
                      </TableHead>
                      <TableHead>Colaborador</TableHead>
                      <TableHead>Filial sugerida</TableHead>
                      <TableHead>Filial oficial</TableHead>
                      <TableHead>O.S vinculadas</TableHead>
                      <TableHead className="w-40">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredUnregistered.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <AppSwitch checked={selectedIds.has(item.id)} onCheckedChange={(checked) => toggleSelected(item.id, checked)} label="" />
                        </TableCell>
                        <TableCell className="min-w-56">
                          <AppInput value={item.name} onChange={(event) => setUnregistered(replaceById(unregistered, item.id, { name: event.target.value }))} />
                        </TableCell>
                        <TableCell className="min-w-52 text-sm text-slate-600">
                          <div className="font-medium text-slate-950">{regionalName(item.suggested_regional || item.regional || "-")}</div>
                          <div>{item.suggested_regional || item.regional || "-"}</div>
                        </TableCell>
                        <TableCell className="min-w-52">
                          <RegionalSelect
                            value={item.regional || item.suggested_regional || ""}
                            options={normalizedRegionalOptions}
                            onChange={(value) => setUnregistered(replaceById(unregistered, item.id, { regional: value }))}
                          />
                        </TableCell>
                        <TableCell>{item.service_orders_count} O.S</TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              disabled={savingIds.has(item.id)}
                              onClick={() =>
                                saveItem({
                                  ...item,
                                  is_registered: true,
                                  active: true,
                                  role: item.role || item.suggested_role || "Não informado",
                                  regional: regionalName(item.regional || item.suggested_regional || item.regional),
                                })
                              }
                            >
                              <Save className="h-4 w-4" />
                              {savingIds.has(item.id) ? "Salvando..." : "Aprovar"}
                            </Button>
                            <RowActionMenu
                              ariaLabel={`Ações do colaborador ${item.name}`}
                              items={[
                                { label: "Apagar", onSelect: () => setPendingDeleteItem(item), tone: "danger" },
                              ]}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                    {filteredUnregistered.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-6 text-center text-sm text-slate-500">
                          Nenhum colaborador pendente de cadastro.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
      <AppModal
        open={deleteSelectionOpen}
        onOpenChange={setDeleteSelectionOpen}
        title="Apagar colaboradores selecionados?"
        description="Essa ação remove os registros selecionados desta lista."
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setDeleteSelectionOpen(false)}>
              Cancelar
            </Button>
            <Button type="button" variant="destructive" onClick={() => void deleteSelected()}>
              Apagar selecionados
            </Button>
          </>
        }
      >
        <div className="text-sm text-slate-600">
          {visibleSelectedItems.length} colaborador(es) serão removidos da visão atual.
        </div>
      </AppModal>
      <AppModal
        open={pendingDeleteItem != null}
        onOpenChange={(open) => setPendingDeleteItem(open ? pendingDeleteItem : null)}
        title="Apagar colaborador?"
        description={pendingDeleteItem ? `O registro de ${pendingDeleteItem.name} será removido.` : undefined}
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setPendingDeleteItem(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => {
                if (!pendingDeleteItem) return;
                void onDelete(pendingDeleteItem);
                setPendingDeleteItem(null);
              }}
            >
              Apagar
            </Button>
          </>
        }
      >
        <div className="text-sm text-slate-600">A ação remove o vínculo deste colaborador na base atual.</div>
      </AppModal>
    </section>
  );
}
