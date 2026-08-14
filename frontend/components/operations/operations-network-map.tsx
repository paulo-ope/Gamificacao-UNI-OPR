"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { numericInputValue, parseNumericInput } from "@/lib/numeric-input";
import { operationsApi, type OperationOfflineLoginClusters } from "@/lib/operations-api";

const OperationsNetworkMapLeaflet = dynamic(
  () => import("./operations-network-map-leaflet").then((mod) => mod.OperationsNetworkMapLeaflet),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-sm text-slate-400">Carregando mapa…</div> },
);

const DEFAULT_RADIUS_METERS = 300;
const DEFAULT_MIN_CLUSTER_SIZE = 3;
const DEFAULT_WINDOW_MINUTES = 30;

export function OperationsNetworkMap() {
  const [radiusMeters, setRadiusMeters] = useState(DEFAULT_RADIUS_METERS);
  const [minClusterSize, setMinClusterSize] = useState(DEFAULT_MIN_CLUSTER_SIZE);
  const [windowMinutes, setWindowMinutes] = useState(DEFAULT_WINDOW_MINUTES);
  const [data, setData] = useState<OperationOfflineLoginClusters | null>(null);
  const [selectedClusterIndex, setSelectedClusterIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Campo pode estar vazio (NaN) enquanto o usuário edita - cai no default nesse caso, em vez
      // de mandar NaN pra API (achado real: sem isso, limpar o campo pra digitar de novo já
      // disparava uma busca inválida antes do usuário terminar de digitar o novo valor).
      const result = await operationsApi.networkOfflineLoginClusters({
        radiusMeters: Number.isFinite(radiusMeters) ? radiusMeters : DEFAULT_RADIUS_METERS,
        minClusterSize: Number.isFinite(minClusterSize) ? minClusterSize : DEFAULT_MIN_CLUSTER_SIZE,
        windowMinutes: Number.isFinite(windowMinutes) ? windowMinutes : DEFAULT_WINDOW_MINUTES,
      });
      setData(result);
      setSelectedClusterIndex(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao buscar clusters de queda de conexão.");
    } finally {
      setLoading(false);
    }
  }, [radiusMeters, minClusterSize, windowMinutes]);

  // Carrega automaticamente com os valores padrão ao abrir a aba - o Radix Tabs desmonta o
  // conteúdo de abas inativas por padrão, então este efeito de montagem dispara de novo cada vez
  // que o usuário volta pra esta aba, sem precisar clicar em "Buscar clusters" primeiro.
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clusters = data?.clusters ?? [];
  const totalLoginsAfetados = useMemo(() => clusters.reduce((sum, cluster) => sum + cluster.size, 0), [clusters]);
  const selectedCluster = selectedClusterIndex !== null ? clusters[selectedClusterIndex] : null;

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <Card className="min-w-0 rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Quedas por proximidade</CardTitle>
          <p className="text-xs text-slate-500">
            Agrupa logins que caíram (transicionaram para desconectado) recentemente e estão perto um do
            outro - candidato a rompimento de fibra num trecho.
          </p>
        </CardHeader>
        <CardContent className="grid min-w-0 gap-4">
          <label className="grid gap-1.5 text-xs font-medium text-slate-700">
            Raio de proximidade (metros)
            <Input
              type="number"
              min={10}
              max={5000}
              value={numericInputValue(radiusMeters)}
              onChange={(event) => setRadiusMeters(parseNumericInput(event.target.value))}
            />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-slate-700">
            Mínimo de logins no cluster
            <Input
              type="number"
              min={2}
              max={100}
              value={numericInputValue(minClusterSize)}
              onChange={(event) => setMinClusterSize(parseNumericInput(event.target.value))}
            />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-slate-700">
            Janela de tempo (minutos)
            <Input
              type="number"
              min={5}
              max={1440}
              value={numericInputValue(windowMinutes)}
              onChange={(event) => setWindowMinutes(parseNumericInput(event.target.value))}
            />
            <span className="text-[10px] font-normal text-slate-500">
              Considera só quem caiu dentro desse intervalo - não pega quedas antigas.
            </span>
          </label>
          <Button onClick={load} disabled={loading}>
            {loading ? "Buscando…" : "Buscar clusters"}
          </Button>
          {error && <p className="text-xs text-red-600">{error}</p>}
          {data && (
            <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
              <p>
                <span className="font-semibold">{clusters.length}</span> clusters encontrados
              </p>
              <p>
                <span className="font-semibold">{totalLoginsAfetados}</span> logins afetados no total
              </p>
            </div>
          )}
          {clusters.length > 0 && (
            <ul className="grid max-h-64 gap-1 overflow-y-auto text-xs">
              {clusters.map((cluster, index) => (
                <li key={`${cluster.center_latitude}-${cluster.center_longitude}-${index}`}>
                  <button
                    type="button"
                    onClick={() => setSelectedClusterIndex(index)}
                    className={`w-full rounded-md px-2 py-1.5 text-left transition ${
                      index === selectedClusterIndex ? "bg-orange-100 text-orange-900" : "hover:bg-slate-100"
                    }`}
                  >
                    {cluster.size} logins · {cluster.center_latitude.toFixed(4)}, {cluster.center_longitude.toFixed(4)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* `isolate` + `overflow-hidden` restritos a este card: contêm o z-index interno do Leaflet
          (controles/tiles chegam a z-index 1000) dentro da própria stacking context, pra ele não
          escapar por cima da barra de filtros (sticky, z-40) acima - achado real, sem isso o
          filtro Regional ficava encoberto pelo mapa ao rolar a página. Não afeta dropdowns/
          popovers de fora deste card.

          Altura: em mobile/tablet (grid empilhado, sem stretch de linha) o card usa uma altura fixa
          (`h-[420px]`) - só assim o mapa (`h-full` por dentro) tem uma altura definida pra resolver
          contra, já que `height:100%` não funciona encadeado a partir de um pai `auto`. A partir de
          `lg` (grid de 2 colunas), o card passa a `h-full`, que estica pra acompanhar a altura da
          linha (definida pelo maior entre painel esquerdo e mapa) - é o CSS Grid, não JS, resolvendo
          isso. Achado real do ajuste anterior: usar `h-[60vh]` no CardContent deixava uma faixa
          branca embaixo do Leaflet sempre que o painel esquerdo (que define a altura da linha) ficava
          mais alto que esses 60vh. */}
      <Card className="relative isolate min-h-[420px] min-w-0 overflow-hidden rounded-2xl border-slate-200 shadow-sm lg:h-full">
        <CardContent className="h-[420px] min-h-0 min-w-0 p-0 lg:h-full">
          {data ? (
            <OperationsNetworkMapLeaflet
              clusters={clusters}
              selectedClusterIndex={selectedClusterIndex}
              onSelectCluster={setSelectedClusterIndex}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              {loading ? "Carregando…" : 'Clique em "Buscar clusters" para carregar o mapa.'}
            </div>
          )}
        </CardContent>
      </Card>

      {selectedCluster && (
        <Card className="min-w-0 rounded-2xl border-slate-200 shadow-sm lg:col-span-2">
          <CardHeader>
            <CardTitle>
              Cluster selecionado - {selectedCluster.size} logins
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-1 text-xs text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
              {selectedCluster.logins.map((login) => (
                <li key={login.login_id}>{login.login}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
