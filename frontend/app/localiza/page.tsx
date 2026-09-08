"use client";

import { useCallback, useEffect, useState } from "react";

import { StatusToast } from "@/components/ui/status-toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceAppShell } from "@/components/workspace/app-shell";
import { localizaApi, type LocationRequest, type LocationRequestStatus } from "@/lib/localiza-api";
import type { AuthUser } from "@/lib/types";

import { LocalizaCreateForm } from "@/components/localiza/localiza-create-form";
import { LocalizaDetailPanel } from "@/components/localiza/localiza-detail-panel";
import { LocalizaList, type LocalizaListScope } from "@/components/localiza/localiza-list";
import { LocalizaMapView } from "@/components/localiza/localiza-map-view";
import { LocalizaSettingsPanel } from "@/components/localiza/localiza-settings-panel";

// Limite alto de propósito: o mapa de referência (aba "Mapa") precisa enxergar TODO cliente que já
// confirmou localização, não só a primeira página - pedido do usuário ("servir para O.S.
// futuras"). Ainda é um teto (não paginação de verdade); se o volume um dia passar disso, vira um
// problema de escala pra resolver então, não antes (ver docs/manual_desenvolvimento_senior.md -
// medir antes de otimizar).
const LIST_LIMIT = 500;

// "Meus links" por padrão (pedido do usuário: cada atendente controla só os próprios clientes por
// padrão, com a opção de ver "Todos") - preferência lembrada por navegador, mesmo padrão já usado
// pra recolher a barra lateral/filtros em outras telas do ecossistema.
const SCOPE_STORAGE_KEY = "localiza_list_scope";

export default function LocalizaPage() {
  return (
    <WorkspaceAppShell activePath="/localiza" title="UNI Localiza" subtitle="Link para o cliente compartilhar localização por GPS">
      {(user) => <LocalizaPageContent user={user} />}
    </WorkspaceAppShell>
  );
}

function LocalizaPageContent({ user }: { user: AuthUser }) {
  const canRead = Boolean(user?.permissions.includes("localiza:read"));
  const canManage = Boolean(user?.permissions.includes("localiza:manage"));

  const [activeTab, setActiveTab] = useState<"solicitacoes" | "mapa">("solicitacoes");
  const [scope, setScope] = useState<LocalizaListScope>("mine");
  const [items, setItems] = useState<LocationRequest[]>([]);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [status, setStatus] = useState<LocationRequestStatus | "">("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<LocationRequest | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(SCOPE_STORAGE_KEY);
    if (stored === "mine" || stored === "all") setScope(stored);
  }, []);

  function changeScope(next: LocalizaListScope) {
    setScope(next);
    window.localStorage.setItem(SCOPE_STORAGE_KEY, next);
  }

  const load = useCallback(
    async (
      filters: { search: string; dateFrom: string; dateTo: string; status: LocationRequestStatus | ""; scope: LocalizaListScope },
      signal?: AbortSignal,
    ) => {
      setLoading(true);
      setError(null);
      try {
        const result = await localizaApi.list({
          search: filters.search || undefined,
          date_from: filters.dateFrom || undefined,
          date_to: filters.dateTo || undefined,
          status: filters.status || undefined,
          mine_only: filters.scope === "mine",
          limit: LIST_LIMIT
        });
        setItems(result);
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Falha ao carregar as solicitações.");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!user || !canRead) return;
    const controller = new AbortController();
    void load({ search, dateFrom, dateTo, status, scope }, controller.signal);
    return () => controller.abort();
    // Recarrega por um efeito próprio de debounce (abaixo), não pela montagem.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, canRead]);

  useEffect(() => {
    if (!canRead) return;
    const timeout = setTimeout(() => void load({ search, dateFrom, dateTo, status, scope }), 300);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, dateFrom, dateTo, status, scope]);

  function handleDateChange(key: "date_from" | "date_to", value: string) {
    if (key === "date_from") setDateFrom(value);
    else setDateTo(value);
  }

  function handleItemChanged(next: LocationRequest) {
    setItems((prev) => {
      const exists = prev.some((item) => item.id === next.id);
      const updated = exists ? prev.map((item) => (item.id === next.id ? next : item)) : [next, ...prev];
      return updated;
    });
    setSelected(next);
  }

  function openDetailById(id: number) {
    const item = items.find((candidate) => candidate.id === id);
    if (item) setSelected(item);
  }

  if (!canRead) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center text-amber-900">
        <h2 className="text-xl font-semibold">Acesso não autorizado</h2>
        <p className="mt-2 text-sm">Seu perfil não possui a permissão localiza:read.</p>
      </div>
    );
  }

  return (
    <div className="min-w-0 px-4 py-5 lg:px-7">
      <StatusToast error={error} onDismissError={() => setError(null)} />

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "solicitacoes" | "mapa")}>
        <TabsList>
          <TabsTrigger value="solicitacoes">Solicitações</TabsTrigger>
          <TabsTrigger value="mapa">Mapa</TabsTrigger>
        </TabsList>

        <TabsContent value="solicitacoes" className="mt-4 grid gap-4">
          {canManage ? (
            <div className="grid gap-2">
              <LocalizaCreateForm onCreated={handleItemChanged} />
              <div className="flex justify-end">
                <LocalizaSettingsPanel />
              </div>
            </div>
          ) : null}

          <LocalizaList
            items={items}
            loading={loading}
            scope={scope}
            onScopeChange={changeScope}
            search={search}
            onSearchChange={setSearch}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateChange={handleDateChange}
            status={status}
            onStatusChange={setStatus}
            onSelect={setSelected}
          />
        </TabsContent>

        <TabsContent value="mapa" className="mt-4">
          <LocalizaMapView items={items} onOpenDetail={openDetailById} />
        </TabsContent>
      </Tabs>

      {selected ? (
        <LocalizaDetailPanel item={selected} onClose={() => setSelected(null)} onChanged={handleItemChanged} />
      ) : null}
    </div>
  );
}
