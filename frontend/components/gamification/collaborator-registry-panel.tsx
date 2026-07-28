"use client";

import { Building2, CircleAlert, KeyRound, Link2, Mail, Phone, Save, Trash2, Upload, UserPlus, Users2, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppCheckbox, AppCombobox, AppDrawer, AppInput, AppModal, AppSwitch, Avatar, RowActionMenu, StatusBadge } from "@/components/gamification/config-ui";
import { InfoHint } from "@/components/gamification/info-hint";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { normalizeRegional, regionalName } from "@/lib/regional";
import { cn } from "@/lib/utils";
import type { AuthUser, CollaboratorRegistry, CollaboratorRegistryItem } from "@/lib/types";

type CreatePayload = {
  name: string;
  role: string;
  regional: string;
  phone: string;
  email: string;
  active: boolean;
  is_registered: boolean;
};

type Props = {
  registry: CollaboratorRegistry;
  regionalOptions: string[];
  onCreate: (payload: CreatePayload) => Promise<number | undefined>;
  onSave: (item: CollaboratorRegistryItem) => Promise<void>;
  onDelete: (item: CollaboratorRegistryItem) => Promise<void>;
  onDeleteMany: (items: CollaboratorRegistryItem[]) => Promise<void>;
  onBulkSetActive?: (items: CollaboratorRegistryItem[], active: boolean) => Promise<void>;
  // Vínculo de acesso ao portal - só o admin (permissão users:manage) enxerga essa seção. Opcional
  // pra não quebrar quem ainda monta este painel sem essas props (ex: testes de componente).
  canManagePortalAccess?: boolean;
  unlinkedUsers?: AuthUser[];
  onCreatePortalUser?: (payload: { collaboratorId: number; email: string; password: string }) => Promise<void>;
  onLinkPortalUser?: (payload: { userId: number; collaboratorId: number }) => Promise<void>;
  onUnlinkPortalUser?: (userId: number) => Promise<void>;
};

type EditDraft = {
  id: number | null;
  name: string;
  role: string;
  regional: string;
  phone: string;
  email: string;
  active: boolean;
  is_registered: boolean;
};

const BLANK_DRAFT: EditDraft = {
  id: null,
  name: "",
  role: "",
  regional: "",
  phone: "",
  email: "",
  active: true,
  is_registered: true,
};

function effectiveRegional(item: CollaboratorRegistryItem) {
  return normalizeRegional(item.regional || item.suggested_regional || "");
}

function statusBadge(item: CollaboratorRegistryItem) {
  if (!item.is_registered) return <StatusBadge tone="warning">Pendente</StatusBadge>;
  if (!item.active) return <StatusBadge>Inativo</StatusBadge>;
  return <StatusBadge tone="success">Cadastrado</StatusBadge>;
}

function draftFromItem(item: CollaboratorRegistryItem): EditDraft {
  return {
    id: item.id,
    name: item.name,
    role: item.role || "",
    regional: effectiveRegional(item),
    phone: item.phone || "",
    email: item.email || "",
    active: item.active,
    is_registered: item.is_registered,
  };
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
      ? "text-uni-royal"
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

export function CollaboratorRegistryPanel({
  registry,
  regionalOptions,
  onCreate,
  onSave,
  onDelete,
  onDeleteMany,
  onBulkSetActive,
  canManagePortalAccess = false,
  unlinkedUsers = [],
  onCreatePortalUser,
  onLinkPortalUser,
  onUnlinkPortalUser,
}: Props) {
  const [search, setSearch] = useState("");
  const [selectedRegional, setSelectedRegional] = useState("");
  const [activeList, setActiveList] = useState("registered");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleteSelectionOpen, setDeleteSelectionOpen] = useState(false);
  const [pendingDeleteItem, setPendingDeleteItem] = useState<CollaboratorRegistryItem | null>(null);
  const [registered, setRegistered] = useState(registry.registered);
  const [unregistered, setUnregistered] = useState(registry.unregistered);
  const [savingId, setSavingId] = useState<number | "new" | null>(null);

  // Drawer único de criar/editar - substitui a antiga linha de cadastro espremida entre os filtros
  // e a edição direto na célula da tabela. `editingId` guia tudo: "new" = drawer vazio (criar),
  // number = editando aquele colaborador (funciona igual pra "Cadastrados" e "Não cadastrados" -
  // aprovar um pendente é só abrir o mesmo drawer, ligar "Cadastrado" e salvar).
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<EditDraft>(BLANK_DRAFT);

  // Foto: cache de object URLs por colaborador (busca autenticada como blob, não <img src> direto -
  // toda rota deste app exige Bearer token). Guardado também em ref pra revogar de forma confiável
  // no unmount (o valor de `photoUrls` capturado no closure do cleanup ficaria desatualizado).
  const [photoUrls, setPhotoUrls] = useState<Record<number, string>>({});
  const photoUrlsRef = useRef<Record<number, string>>({});
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);

  // Vínculo de acesso ao portal - form inline pra criar um usuário novo já vinculado ao
  // colaborador em edição, ou selecionar um usuário existente sem colaborador vinculado ainda.
  const [portalEmail, setPortalEmail] = useState("");
  const [portalPassword, setPortalPassword] = useState("");
  const [portalLinkUserId, setPortalLinkUserId] = useState("");
  const [portalBusy, setPortalBusy] = useState(false);
  const [portalError, setPortalError] = useState<string | null>(null);

  useEffect(() => {
    setRegistered(registry.registered);
    setUnregistered(registry.unregistered);
    setSelectedIds(new Set());
  }, [registry]);

  useEffect(() => {
    let cancelled = false;
    const idsToFetch = [...registered, ...unregistered]
      .filter((item) => item.has_photo && !photoUrlsRef.current[item.id])
      .map((item) => item.id);
    if (!idsToFetch.length) return;
    (async () => {
      for (const id of idsToFetch) {
        try {
          const blob = await api.collaboratorPhoto(id);
          if (cancelled) return;
          const url = URL.createObjectURL(blob);
          photoUrlsRef.current = { ...photoUrlsRef.current, [id]: url };
          setPhotoUrls(photoUrlsRef.current);
        } catch {
          // sem foto ou erro de rede - cai no avatar de iniciais, sem travar a lista.
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [registered, unregistered]);

  useEffect(
    () => () => {
      Object.values(photoUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
    },
    []
  );

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

  const editingItem = typeof editingId === "number" ? [...registered, ...unregistered].find((item) => item.id === editingId) ?? null : null;
  const drawerOpen = editingId !== null;

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

  async function bulkSetActive(active: boolean) {
    if (visibleSelectedItems.length === 0 || !onBulkSetActive) return;
    await onBulkSetActive(visibleSelectedItems, active);
    setSelectedIds(new Set());
  }

  function resetPortalForm() {
    setPortalEmail("");
    setPortalPassword("");
    setPortalLinkUserId("");
    setPortalError(null);
  }

  function openCreateDrawer() {
    setDraft({ ...BLANK_DRAFT, regional: selectedRegional });
    setPhotoError(null);
    resetPortalForm();
    setEditingId("new");
  }

  function openEditDrawer(item: CollaboratorRegistryItem) {
    setDraft(draftFromItem(item));
    setPhotoError(null);
    setPortalEmail(item.email || "");
    setPortalLinkUserId("");
    setPortalError(null);
    setEditingId(item.id);
  }

  function closeDrawer() {
    setEditingId(null);
    setDraft(BLANK_DRAFT);
    setPhotoError(null);
    resetPortalForm();
  }

  async function handleCreatePortalUser() {
    if (typeof editingId !== "number" || !onCreatePortalUser) return;
    if (!portalEmail.trim() || !portalPassword.trim()) return;
    setPortalBusy(true);
    setPortalError(null);
    try {
      await onCreatePortalUser({ collaboratorId: editingId, email: portalEmail.trim(), password: portalPassword });
      resetPortalForm();
    } catch (err) {
      setPortalError(err instanceof Error ? err.message : "Erro ao criar acesso ao portal.");
    } finally {
      setPortalBusy(false);
    }
  }

  async function handleLinkPortalUser() {
    if (typeof editingId !== "number" || !onLinkPortalUser || !portalLinkUserId) return;
    setPortalBusy(true);
    setPortalError(null);
    try {
      await onLinkPortalUser({ userId: Number(portalLinkUserId), collaboratorId: editingId });
      resetPortalForm();
    } catch (err) {
      setPortalError(err instanceof Error ? err.message : "Erro ao vincular usuário.");
    } finally {
      setPortalBusy(false);
    }
  }

  async function handleUnlinkPortalUser(userId: number) {
    if (!onUnlinkPortalUser) return;
    setPortalBusy(true);
    setPortalError(null);
    try {
      await onUnlinkPortalUser(userId);
    } catch (err) {
      setPortalError(err instanceof Error ? err.message : "Erro ao desvincular acesso ao portal.");
    } finally {
      setPortalBusy(false);
    }
  }

  function updateDraft(patch: Partial<EditDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  async function saveDraft() {
    if (!draft.name.trim() || !draft.regional.trim()) return;
    setSavingId(editingId);
    try {
      if (editingId === "new") {
        const newId = await onCreate({
          name: draft.name,
          role: draft.role || "Importado UpValue",
          regional: draft.regional,
          phone: draft.phone,
          email: draft.email,
          active: draft.active,
          is_registered: draft.is_registered,
        });
        if (typeof newId === "number") {
          // Continua no drawer, agora em modo edição do recém-criado - habilita a seção de foto
          // (não dá pra anexar arquivo a um registro que ainda não existia até este ponto).
          setEditingId(newId);
        } else {
          closeDrawer();
        }
      } else if (editingItem) {
        await onSave({
          ...editingItem,
          name: draft.name,
          role: draft.role,
          regional: draft.regional,
          phone: draft.phone,
          email: draft.email,
          active: draft.active,
          is_registered: draft.is_registered,
        });
        closeDrawer();
      }
    } finally {
      setSavingId(null);
    }
  }

  async function handlePhotoChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || typeof editingId !== "number") return;
    setUploadingPhoto(true);
    setPhotoError(null);
    try {
      await api.uploadCollaboratorPhoto(editingId, file);
      const url = URL.createObjectURL(file);
      if (photoUrlsRef.current[editingId]) URL.revokeObjectURL(photoUrlsRef.current[editingId]);
      photoUrlsRef.current = { ...photoUrlsRef.current, [editingId]: url };
      setPhotoUrls(photoUrlsRef.current);
      setRegistered((current) => current.map((item) => (item.id === editingId ? { ...item, has_photo: true } : item)));
      setUnregistered((current) => current.map((item) => (item.id === editingId ? { ...item, has_photo: true } : item)));
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : "Erro ao enviar a foto.");
    } finally {
      setUploadingPhoto(false);
    }
  }

  async function handlePhotoRemove() {
    if (typeof editingId !== "number") return;
    setUploadingPhoto(true);
    setPhotoError(null);
    try {
      await api.deleteCollaboratorPhoto(editingId);
      if (photoUrlsRef.current[editingId]) {
        URL.revokeObjectURL(photoUrlsRef.current[editingId]);
        const next = { ...photoUrlsRef.current };
        delete next[editingId];
        photoUrlsRef.current = next;
        setPhotoUrls(next);
      }
      setRegistered((current) => current.map((item) => (item.id === editingId ? { ...item, has_photo: false } : item)));
      setUnregistered((current) => current.map((item) => (item.id === editingId ? { ...item, has_photo: false } : item)));
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : "Erro ao remover a foto.");
    } finally {
      setUploadingPhoto(false);
    }
  }

  function contactLine(item: CollaboratorRegistryItem) {
    if (!item.phone && !item.email) return <span className="text-slate-400">Sem contato</span>;
    return (
      <div className="grid gap-0.5 text-xs text-slate-600">
        {item.phone ? (
          <span className="flex items-center gap-1">
            <Phone className="h-3 w-3 text-slate-400" />
            {item.phone}
          </span>
        ) : null}
        {item.email ? (
          <span className="flex items-center gap-1">
            <Mail className="h-3 w-3 text-slate-400" />
            {item.email}
          </span>
        ) : null}
      </div>
    );
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
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={openCreateDrawer}>
                <UserPlus className="h-4 w-4" />
                Cadastrar colaborador
              </Button>
              {onBulkSetActive && activeList === "registered" ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    className="border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                    onClick={() => bulkSetActive(true)}
                    disabled={visibleSelectedItems.length === 0}
                  >
                    Ativar selecionados
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    className="border-slate-200 text-slate-700 hover:bg-slate-50"
                    onClick={() => bulkSetActive(false)}
                    disabled={visibleSelectedItems.length === 0}
                  >
                    Desativar selecionados
                  </Button>
                </>
              ) : null}
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
        </div>

        <div className="grid gap-4 border-b border-slate-200 bg-slate-50/80 px-5 py-5 md:grid-cols-2">
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
            <AppInput className="h-11" placeholder="Nome, cargo ou filial" value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
        </div>

        <div className="p-5">
          <div className="mb-4 grid h-auto grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-1 md:grid-cols-2">
            <button
              type="button"
              onClick={() => {
                setActiveList("registered");
                setSelectedIds(new Set());
              }}
              className={cn(
                "rounded-xl px-4 py-2.5 text-sm font-medium transition",
                activeList === "registered" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-800"
              )}
            >
              Cadastrados ({filteredRegistered.length})
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveList("unregistered");
                setSelectedIds(new Set());
              }}
              className={cn(
                "rounded-xl px-4 py-2.5 text-sm font-medium transition",
                activeList === "unregistered" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-800"
              )}
            >
              Não cadastrados ({filteredUnregistered.length})
            </button>
          </div>

          {activeList === "registered" ? (
            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                  <TableRow className="border-slate-700 hover:bg-slate-900">
                    <TableHead className="w-10">
                      <AppCheckbox checked={allVisibleSelected} onCheckedChange={toggleAllVisible} ariaLabel="Selecionar todos os colaboradores listados" />
                    </TableHead>
                    <TableHead>Colaborador</TableHead>
                    <TableHead>Filial oficial</TableHead>
                    <TableHead>Contato</TableHead>
                    <TableHead>O.S vinculadas</TableHead>
                    <TableHead>
                      <span className="inline-flex items-center gap-1">
                        Status
                        <InfoHint
                          ariaLabel="O que significa cada status"
                          description={'"Cadastrado" = ativo e formalizado, entra na apuração normalmente. "Inativo" = formalizado mas desligado, não entra na apuração. "Pendente" = apareceu com produção mas ainda não foi formalizado (aba Não cadastrados).'}
                        />
                      </span>
                    </TableHead>
                    <TableHead className="w-32">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredRegistered.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <AppCheckbox
                          checked={selectedIds.has(item.id)}
                          onCheckedChange={(checked) => toggleSelected(item.id, checked)}
                          ariaLabel={`Selecionar ${item.name}`}
                        />
                      </TableCell>
                      <TableCell className="min-w-56">
                        <div className="flex items-center gap-2.5">
                          <Avatar name={item.name} photoUrl={item.has_photo ? photoUrls[item.id] : null} />
                          <div>
                            <div className="font-medium text-slate-950">{item.name}</div>
                            {item.role ? <div className="text-xs text-slate-500">{item.role}</div> : null}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-slate-700">{regionalName(effectiveRegional(item))}</TableCell>
                      <TableCell>{contactLine(item)}</TableCell>
                      <TableCell>{item.service_orders_count} O.S</TableCell>
                      <TableCell>{statusBadge(item)}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => openEditDrawer(item)}>
                            Editar
                          </Button>
                          <RowActionMenu
                            ariaLabel={`Ações do colaborador ${item.name}`}
                            items={[{ label: "Apagar", onSelect: () => setPendingDeleteItem(item), tone: "danger" }]}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {filteredRegistered.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="py-6 text-center text-sm text-slate-500">
                        Nenhum colaborador cadastrado para os filtros atuais.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                  <TableRow className="border-slate-700 hover:bg-slate-900">
                    <TableHead className="w-10">
                      <AppCheckbox checked={allVisibleSelected} onCheckedChange={toggleAllVisible} ariaLabel="Selecionar todos os colaboradores listados" />
                    </TableHead>
                    <TableHead>Colaborador</TableHead>
                    <TableHead>Filial sugerida</TableHead>
                    <TableHead>O.S vinculadas</TableHead>
                    <TableHead className="w-32">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredUnregistered.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <AppCheckbox
                          checked={selectedIds.has(item.id)}
                          onCheckedChange={(checked) => toggleSelected(item.id, checked)}
                          ariaLabel={`Selecionar ${item.name}`}
                        />
                      </TableCell>
                      <TableCell className="min-w-56">
                        <div className="flex items-center gap-2.5">
                          <Avatar name={item.name} photoUrl={item.has_photo ? photoUrls[item.id] : null} />
                          <div className="font-medium text-slate-950">{item.name}</div>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-slate-600">
                        {regionalName(item.suggested_regional || item.regional || "-")}
                      </TableCell>
                      <TableCell>{item.service_orders_count} O.S</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          <Button size="sm" onClick={() => openEditDrawer(item)}>
                            Editar
                          </Button>
                          <RowActionMenu
                            ariaLabel={`Ações do colaborador ${item.name}`}
                            items={[{ label: "Apagar", onSelect: () => setPendingDeleteItem(item), tone: "danger" }]}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {filteredUnregistered.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-6 text-center text-sm text-slate-500">
                        Nenhum colaborador pendente de cadastro.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </div>

      <AppDrawer
        open={drawerOpen}
        onOpenChange={(open) => !open && closeDrawer()}
        title={editingId === "new" ? "Cadastrar colaborador" : `Editar ${editingItem?.name ?? "colaborador"}`}
        description="Nome e filial são obrigatórios. Contato e foto são opcionais."
      >
        <div className="grid gap-5">
          {typeof editingId === "number" ? (
            <div className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
              <Avatar name={draft.name || "?"} photoUrl={photoUrls[editingId] ?? null} size="lg" />
              <div className="grid gap-2">
                <div className="flex flex-wrap gap-2">
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                    <Upload className="h-4 w-4" />
                    {uploadingPhoto ? "Enviando..." : "Alterar foto"}
                    <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" disabled={uploadingPhoto} onChange={(event) => void handlePhotoChange(event)} />
                  </label>
                  {photoUrls[editingId] ? (
                    <Button type="button" variant="ghost" size="sm" disabled={uploadingPhoto} onClick={() => void handlePhotoRemove()}>
                      <X className="h-4 w-4" />
                      Remover foto
                    </Button>
                  ) : null}
                </div>
                <p className="text-xs text-slate-500">JPEG, PNG ou WEBP, até 2MB.</p>
                {photoError ? <p className="text-xs text-red-600">{photoError}</p> : null}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
              Salve o cadastro primeiro para poder enviar uma foto de perfil.
            </div>
          )}

          {canManagePortalAccess && typeof editingId === "number" ? (
            <div className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
                <KeyRound className="h-4 w-4 text-slate-500" />
                Acesso ao portal
              </div>
              {editingItem?.portal_user_email ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm text-slate-700">
                    Vinculado a <span className="font-medium">{editingItem.portal_user_email}</span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={portalBusy}
                    onClick={() => editingItem.portal_user_id != null && void handleUnlinkPortalUser(editingItem.portal_user_id)}
                  >
                    <X className="h-4 w-4" />
                    Desvincular
                  </Button>
                </div>
              ) : (
                <div className="grid gap-3">
                  <p className="text-xs text-slate-500">
                    Sem acesso ao portal ainda. Crie um usuário novo já vinculado a este colaborador, ou vincule um usuário existente sem colaborador.
                  </p>
                  <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <AppInput type="email" placeholder="E-mail de acesso" value={portalEmail} onChange={(event) => setPortalEmail(event.target.value)} />
                    <AppInput type="password" placeholder="Senha inicial" value={portalPassword} onChange={(event) => setPortalPassword(event.target.value)} />
                    <Button type="button" size="sm" disabled={portalBusy || !portalEmail.trim() || !portalPassword.trim()} onClick={() => void handleCreatePortalUser()}>
                      Criar acesso
                    </Button>
                  </div>
                  {unlinkedUsers.length > 0 ? (
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                      <AppCombobox
                        value={portalLinkUserId}
                        onChange={setPortalLinkUserId}
                        placeholder="Ou vincular usuário existente"
                        ariaLabel="Vincular usuário existente ao colaborador"
                        options={unlinkedUsers.map((item) => ({ value: String(item.id), label: item.email, description: item.name }))}
                      />
                      <Button type="button" variant="outline" size="sm" disabled={portalBusy || !portalLinkUserId} onClick={() => void handleLinkPortalUser()}>
                        Vincular
                      </Button>
                    </div>
                  ) : null}
                  {portalError ? <p className="text-xs text-red-600">{portalError}</p> : null}
                </div>
              )}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2 md:col-span-2">
              <Label>Nome completo</Label>
              <AppInput value={draft.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="Nome do colaborador" />
            </div>
            <div className="grid gap-2">
              <Label>Cargo</Label>
              <AppInput value={draft.role} onChange={(event) => updateDraft({ role: event.target.value })} placeholder="Ex: Técnico de campo" />
            </div>
            <div className="grid gap-2">
              <Label>Filial</Label>
              <RegionalSelect value={draft.regional} options={normalizedRegionalOptions} onChange={(value) => updateDraft({ regional: value })} />
            </div>
            <div className="grid gap-2">
              <Label>Telefone</Label>
              <AppInput value={draft.phone} onChange={(event) => updateDraft({ phone: event.target.value })} placeholder="(00) 00000-0000" />
            </div>
            <div className="grid gap-2">
              <Label>E-mail</Label>
              <AppInput type="email" value={draft.email} onChange={(event) => updateDraft({ email: event.target.value })} placeholder="nome@exemplo.com" />
            </div>
          </div>

          <div className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 sm:grid-cols-2">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-slate-900">Ativo</div>
                <div className="text-xs text-slate-500">Desligado não entra na apuração.</div>
              </div>
              <AppSwitch checked={draft.active} onCheckedChange={(checked) => updateDraft({ active: checked })} />
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-slate-900">Cadastrado</div>
                <div className="text-xs text-slate-500">Desligue para mover de volta a "Não cadastrados".</div>
              </div>
              <AppSwitch checked={draft.is_registered} onCheckedChange={(checked) => updateDraft({ is_registered: checked })} />
            </div>
          </div>

          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={closeDrawer}>
              Cancelar
            </Button>
            <Button
              type="button"
              onClick={() => void saveDraft()}
              disabled={!draft.name.trim() || !draft.regional.trim() || savingId !== null}
            >
              <Save className="h-4 w-4" />
              {savingId !== null ? "Salvando..." : editingId === "new" ? "Cadastrar" : "Salvar"}
            </Button>
          </div>
        </div>
      </AppDrawer>

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
