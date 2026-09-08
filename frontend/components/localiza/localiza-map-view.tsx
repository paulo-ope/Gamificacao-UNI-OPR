"use client";

import dynamic from "next/dynamic";
import { MapPin, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { LocationRequest } from "@/lib/localiza-api";

const LocalizaMapViewLeaflet = dynamic(
  () => import("./localiza-map-view-leaflet").then((mod) => mod.LocalizaMapViewLeaflet),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-sm text-slate-400">Carregando mapa…</div> },
);

function matchesSearch(item: LocationRequest, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [item.order_code, item.opa_protocol, item.customer_id, item.customer_name, item.public_id, item.ixc_login, item.ixc_login_id ? String(item.ixc_login_id) : null]
    .some((field) => field?.toLowerCase().includes(normalized));
}

// Mapa de referência com TODOS os clientes que já confirmaram localização pelo link - pedido do
// usuário: servir de consulta rápida pra abrir uma O.S. futura no mesmo endereço, sem precisar
// gerar um link novo pra achar o ponto de novo. Busca própria (pedido explícito: "quero poder
// pesquisar o cliente no mapa") - filtra os pontos e reenquadra o mapa neles, sem depender de estar
// na aba "Solicitações" pra restringir o recorte.
export function LocalizaMapView({ items, onOpenDetail }: { items: LocationRequest[]; onOpenDetail: (id: number) => void }) {
  const [search, setSearch] = useState("");
  const confirmedItems = useMemo(() => items.filter((item) => item.confirmed_latitude !== null && item.confirmed_longitude !== null), [items]);
  const visibleItems = useMemo(() => confirmedItems.filter((item) => matchesSearch(item, search)), [confirmedItems, search]);

  return (
    <Card className="min-w-0 rounded-2xl border-slate-200 shadow-sm">
      <CardHeader className="gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-blue-600" aria-hidden="true" />
            Mapa de clientes confirmados
          </CardTitle>
          <p className="mt-1 text-xs text-slate-500">
            {visibleItems.length} de {confirmedItems.length} localização(ões) confirmada(s) no recorte atual - use os
            filtros da aba Solicitações pra restringir por período. Clique num ponto pra ver os detalhes.
          </p>
        </div>
        <div className="relative max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
          <Input
            className="pl-8"
            placeholder="Buscar cliente, login ou O.S. no mapa"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </CardHeader>
      <CardContent className="isolate h-[520px] p-0">
        {confirmedItems.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Nenhuma localização confirmada no recorte atual.
          </div>
        ) : visibleItems.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Nenhum cliente confirmado corresponde à busca.
          </div>
        ) : (
          <LocalizaMapViewLeaflet items={visibleItems} onOpenDetail={onOpenDetail} />
        )}
      </CardContent>
    </Card>
  );
}
