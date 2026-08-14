"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useRef } from "react";

import type { OperationOfflineLoginCluster } from "@/lib/operations-api";

// Não usamos `react-leaflet` (MapContainer) de propósito - achado real: com o React 18 Strict
// Mode ligado neste projeto (ver next.config.mjs), o MapContainer do react-leaflet v4 quebra com
// "Map container is already initialized" porque o Leaflet marca o elemento DOM com `_leaflet_id`
// e o `.remove()` não limpa essa marca; no ciclo mount->cleanup->mount que o Strict Mode simula em
// dev, a segunda tentativa de montar sobre o MESMO elemento sempre falha. Aqui o mapa é criado à
// mão com um guard (`mapRef`) que só chama `L.map()` uma vez por elemento físico, e o cleanup
// remove a marca manualmente - assim uma segunda montagem (Strict Mode, ou HMR) funciona.
const DEFAULT_CENTER: [number, number] = [-10.9472, -61.9528]; // Ji-Paraná, RO - centro aproximado da base

export function OperationsNetworkMapLeaflet({
  clusters,
  selectedClusterIndex,
  onSelectCluster,
}: {
  clusters: OperationOfflineLoginCluster[];
  selectedClusterIndex: number | null;
  onSelectCluster: (index: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const circlesRef = useRef<L.Circle[]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, {
      center: DEFAULT_CENTER,
      zoom: 7,
      scrollWheelZoom: true,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    mapRef.current = map;

    // O Leaflet não redetecta sozinho quando o CONTAINER muda de tamanho por CSS (troca de
    // breakpoint, painel lateral recolhendo, resize da janela) - sem isto o mapa fica com
    // tiles cortados/deslocados até a próxima interação. `requestAnimationFrame` throttla pra
    // no máximo uma chamada de `invalidateSize()` por frame, mesmo que o ResizeObserver dispare
    // várias vezes durante um resize contínuo.
    let pendingFrame: number | null = null;
    const resizeObserver = new ResizeObserver(() => {
      if (pendingFrame !== null) return;
      pendingFrame = requestAnimationFrame(() => {
        pendingFrame = null;
        map.invalidateSize();
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
      map.remove();
      mapRef.current = null;
      // `map.remove()` não apaga `_leaflet_id` do elemento - sem isso, a próxima montagem no
      // mesmo elemento (Strict Mode dev, ou navegação de volta pra esta aba) quebra.
      delete (container as unknown as { _leaflet_id?: number })._leaflet_id;
    };
  }, []);

  // Raio do círculo desenhado é o raio de busca (`radius_meters`), não um cálculo geométrico
  // sobre os logins do cluster - é só referência visual de "essa foi a distância usada pra
  // agrupar", não o contorno exato da área afetada.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    circlesRef.current.forEach((circle) => circle.remove());
    circlesRef.current = clusters.map((cluster, index) => {
      const isSelected = index === selectedClusterIndex;
      const circle = L.circle([cluster.center_latitude, cluster.center_longitude], {
        radius: cluster.radius_meters,
        color: isSelected ? "#dc2626" : "#f97316",
        fillColor: isSelected ? "#dc2626" : "#f97316",
        fillOpacity: isSelected ? 0.35 : 0.2,
        weight: isSelected ? 3 : 2,
      }).addTo(map);

      const loginsPreview = cluster.logins
        .slice(0, 5)
        .map((login) => `<li>${login.login}</li>`)
        .join("");
      const remaining = cluster.logins.length > 5 ? `<p>+${cluster.logins.length - 5} mais</p>` : "";
      circle.bindPopup(
        `<div style="font-size:12px"><p style="font-weight:600">${cluster.size} logins desconectados</p>` +
          `<p style="color:#64748b">${cluster.center_latitude.toFixed(5)}, ${cluster.center_longitude.toFixed(5)}</p>` +
          `<ul style="margin-top:4px;padding-left:16px;list-style:disc">${loginsPreview}</ul>${remaining}</div>`,
      );
      circle.on("click", () => onSelectCluster(index));
      return circle;
    });

    if (clusters.length > 0) {
      map.setView([clusters[0].center_latitude, clusters[0].center_longitude], 12);
    }
  }, [clusters, selectedClusterIndex, onSelectCluster]);

  return <div ref={containerRef} className="h-full w-full min-w-0" />;
}
