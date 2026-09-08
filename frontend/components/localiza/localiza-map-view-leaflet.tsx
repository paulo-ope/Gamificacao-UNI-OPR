"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useRef } from "react";

import { distanceClassificationLabel } from "@/lib/geo-distance";
import type { LocationRequest } from "@/lib/localiza-api";
import { localizaRequestLabel } from "./localiza-format";

const DEFAULT_CENTER: [number, number] = [-10.9472, -61.9528]; // Ji-Paraná, RO - centro aproximado da base

// Cor por classificação de divergência (mesma régua de `lib/geo-distance.ts`) - útil pra bater o
// olho e ver quais clientes têm cadastro desatualizado (vermelho) antes de abrir uma O.S. nova.
const CLASSIFICATION_COLOR: Record<string, string> = {
  compatible: "#16a34a",
  minor_divergence: "#d97706",
  relevant_divergence: "#ea580c",
  high_divergence: "#dc2626",
};

function pinIcon(color: string) {
  return L.divIcon({
    className: "",
    html: `<svg width="26" height="34" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,0.35))">
      <path d="M16 0C7.163 0 0 7.163 0 16c0 11 16 26 16 26s16-15 16-26C32 7.163 24.837 0 16 0z" fill="${color}"/>
      <circle cx="16" cy="16" r="6.5" fill="white"/>
    </svg>`,
    iconSize: [26, 34],
    iconAnchor: [13, 34],
    popupAnchor: [0, -30],
  });
}

// Mesmo padrão anti-Strict-Mode do resto do módulo (Leaflet criado à mão, guard contra
// remontagem) - aqui com UM marcador por cliente que já confirmou localização, pra servir de
// referência em atendimentos futuros (pedido explícito do usuário).
export function LocalizaMapViewLeaflet({ items, onOpenDetail }: { items: LocationRequest[]; onOpenDetail: (id: number) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.Marker[]>([]);
  const onOpenDetailRef = useRef(onOpenDetail);
  onOpenDetailRef.current = onOpenDetail;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, { center: DEFAULT_CENTER, zoom: 7, scrollWheelZoom: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    mapRef.current = map;

    const resizeObserver = new ResizeObserver(() => map.invalidateSize());
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      delete (container as unknown as { _leaflet_id?: number })._leaflet_id;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    const points: L.LatLngExpression[] = [];
    items.forEach((item) => {
      if (item.confirmed_latitude === null || item.confirmed_longitude === null) return;
      const color = item.distance_classification ? CLASSIFICATION_COLOR[item.distance_classification] : "#2563eb";
      const marker = L.marker([item.confirmed_latitude, item.confirmed_longitude], { icon: pinIcon(color) }).addTo(map);
      const divergenceLine = item.distance_classification
        ? `<p style="margin-top:4px;color:${color}">${distanceClassificationLabel(item.distance_classification)}</p>`
        : "";
      marker.bindPopup(
        `<div style="font-size:12px;min-width:160px">
          <p style="font-weight:600">${localizaRequestLabel(item)}</p>
          <p style="color:#64748b">${item.customer_name ?? ""}</p>
          ${divergenceLine}
          <button data-open-detail style="margin-top:6px;padding:2px 8px;border-radius:6px;border:1px solid #cbd5e1;background:white;font-size:11px;cursor:pointer">Ver detalhes</button>
        </div>`,
      );
      // O botão "Ver detalhes" só existe depois que o popup abre - liga o clique nesse momento,
      // não no bind (o elemento nem existe no DOM ainda).
      marker.on("popupopen", () => {
        const button = marker.getPopup()?.getElement()?.querySelector<HTMLButtonElement>("[data-open-detail]");
        if (button) {
          button.onclick = () => {
            map.closePopup();
            onOpenDetailRef.current(item.id);
          };
        }
      });
      markersRef.current.push(marker);
      points.push([item.confirmed_latitude, item.confirmed_longitude]);
    });

    if (points.length === 1) {
      map.setView(points[0], 14);
    } else if (points.length > 1) {
      map.fitBounds(L.latLngBounds(points), { padding: [32, 32] });
    }
  }, [items]);

  return <div ref={containerRef} className="h-full w-full min-w-0" />;
}
