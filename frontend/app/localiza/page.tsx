"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { StatusToast } from "@/components/ui/status-toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceAppShell } from "@/components/workspace/app-shell";
import { localizaApi, type LocationRequest, type LocationRequestStatus } from "@/lib/localiza-api";
import type { AuthUser } from "@/lib/types";

import { LocalizaCreateForm } from "@/components/localiza/localiza-create-form";
import { LocalizaDetailPanel } from "@/components/localiza/localiza-detail-panel";
import { LocalizaList, type LocalizaListScope } from "@/components/localiza/localiza-list";
import { LocalizaMapView } from "@/components/localiza/localiza-map-view";
import { LOCALIZA_NAV_ITEMS, isLocalizaTab, type LocalizaTab } from "@/components/localiza/localiza-nav-items";
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

// Ciclo de atualização da lista. Mais espaçado que o do painel de detalhe (4s): aqui é uma visão
// de acompanhamento, não a tela focada em um atendimento específico.
const LIST_POLL_INTERVAL_MS = 10_000;

export default function LocalizaPage() {
  return (
    <WorkspaceAppShell activePath="/localiza" title="UNI Localiza" subtitle="Link para o cliente compartilhar localização por GPS">
      {(user) => (
        // `useSearchParams` (aba pedida pela URL) exige fronteira de Suspense em rota estática -
        // mesmo padrão já usado em `app/admin/page.tsx`.
        <Suspense
          fallback={
            <p className="py-16 text-center text-sm text-slate-500" aria-busy="true">
              Carregando UNI Localiza...
            </p>
          }
        >
          <LocalizaPageContent user={user} />
        </Suspense>
      )}
    </WorkspaceAppShell>
  );
}

function LocalizaPageContent({ user }: { user: AuthUser }) {
  const canRead = Boolean(user?.permissions.includes("localiza:read"));
  const canManage = Boolean(user?.permissions.includes("localiza:manage"));

  const [activeTab, setActiveTab] = useState<LocalizaTab>("solicitacoes");
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

  // Tela pedida pela URL (`?tab=`), como o submenu do módulo na barra lateral do ecossistema linka
  // (ver `lib/module-screens.ts`). Depende de `searchParams` e não de `window.location` pelo mesmo
  // motivo já documentado em `app/admin/page.tsx`: em navegação pelo lado do cliente a URL do
  // navegador ainda não está atualizada na primeira renderização.
  const searchParams = useSearchParams();
  useEffect(() => {
    const tab = searchParams.get("tab");
    if (isLocalizaTab(tab)) setActiveTab(tab);
  }, [searchParams]);

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

  // Atualização automática da LISTA enquanto houver solicitação pendente - sem isso o atendente
  // fechava o painel de detalhe e a tela nunca mais mudava sozinha, obrigando a recarregar a
  // página pra ver que o cliente já tinha confirmado (achado real, reportado pelo usuário).
  // O painel de detalhe tem o seu próprio ciclo, mais curto, por ser uma tela focada num item só.
  //
  // Só na aba "Solicitações": na aba "Mapa", recarregar a lista redesenharia os marcadores e
  // reenquadraria o mapa a cada ciclo, atrapalhando quem está navegando nele.
  const hasPending = items.some((item) => item.status === "pending");
  useEffect(() => {
    if (!canRead || !hasPending || activeTab !== "solicitacoes") return;
    const interval = setInterval(() => {
      // Aba em segundo plano não precisa de atualização - evita chamada inútil no servidor.
      if (document.visibilityState !== "visible") return;
      void load({ search, dateFrom, dateTo, status, scope });
    }, LIST_POLL_INTERVAL_MS);
    // Voltar pra aba atualiza NA HORA, sem esperar o próximo ciclo: o caminho normal é o atendente
    // sair pra mandar o link pelo WhatsApp e voltar querendo saber se o cliente já confirmou.
    function refreshOnFocus() {
      if (document.visibilityState === "visible") void load({ search, dateFrom, dateTo, status, scope });
    }
    document.addEventListener("visibilitychange", refreshOnFocus);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshOnFocus);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRead, hasPending, activeTab, search, dateFrom, dateTo, status, scope]);

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

      <Tabs value={activeTab} onValueChange={(value) => isLocalizaTab(value) && setActiveTab(value)}>
        <TabsList>
          {LOCALIZA_NAV_ITEMS.map((item) => (
            <TabsTrigger key={item.value} value={item.value}>
              {item.label}
            </TabsTrigger>
          ))}
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
