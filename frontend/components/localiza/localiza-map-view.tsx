"use client";

import dynamic from "next/dynamic";
import { MapPin } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LocationRequest } from "@/lib/localiza-api";

const LocalizaMapViewLeaflet = dynamic(
  () => import("./localiza-map-view-leaflet").then((mod) => mod.LocalizaMapViewLeaflet),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-sm text-slate-400">Carregando mapa…</div> },
);

// Mapa de referência com TODOS os clientes que já confirmaram localização pelo link - pedido do
// usuário: servir de consulta rápida pra abrir uma O.S. futura no mesmo endereço, sem precisar
// gerar um link novo pra achar o ponto de novo.
export function LocalizaMapView({ items, onOpenDetail }: { items: LocationRequest[]; onOpenDetail: (id: number) => void }) {
  const confirmedCount = items.filter((item) => item.confirmed_latitude !== null && item.confirmed_longitude !== null).length;

  return (
    <Card className="min-w-0 rounded-2xl border-slate-200 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-blue-600" aria-hidden="true" />
          Mapa de clientes confirmados
        </CardTitle>
        <p className="text-xs text-slate-500">
          {confirmedCount} localização(ões) confirmada(s) no recorte atual - use os filtros acima pra restringir por
          período. Clique num ponto pra ver os detalhes.
        </p>
      </CardHeader>
      <CardContent className="isolate h-[520px] p-0">
        {confirmedCount > 0 ? (
          <LocalizaMapViewLeaflet items={items} onOpenDetail={onOpenDetail} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Nenhuma localização confirmada no recorte atual.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
