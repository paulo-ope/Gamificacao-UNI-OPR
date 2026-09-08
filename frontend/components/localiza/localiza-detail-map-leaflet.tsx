"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useRef } from "react";

// Mesmo padrão de `operations-network-map-leaflet.tsx`: Leaflet criado à mão (não
// `react-leaflet`/`MapContainer`) por causa do React 18 Strict Mode - ver comentário lá.
const DEFAULT_CENTER: [number, number] = [-10.9472, -61.9528]; // Ji-Paraná, RO - centro aproximado da base

function markerIcon(color: string) {
  return L.divIcon({
    className: "",
    html: `<span style="display:block;width:16px;height:16px;border-radius:9999px;background:${color};border:2px solid white;box-shadow:0 0 0 1px rgba(0,0,0,0.25)"></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

export function LocalizaDetailMapLeaflet({
  registered,
  confirmed,
}: {
  registered: { latitude: number; longitude: number } | null;
  confirmed: { latitude: number; longitude: number } | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.Marker[]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, { center: DEFAULT_CENTER, zoom: 13, scrollWheelZoom: true });
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
    if (registered) {
      const marker = L.marker([registered.latitude, registered.longitude], { icon: markerIcon("#2563eb") })
        .addTo(map)
        .bindPopup("Coordenada cadastrada");
      markersRef.current.push(marker);
      points.push([registered.latitude, registered.longitude]);
    }
    if (confirmed) {
      const marker = L.marker([confirmed.latitude, confirmed.longitude], { icon: markerIcon("#dc2626") })
        .addTo(map)
        .bindPopup("Localização confirmada pelo cliente");
      markersRef.current.push(marker);
      points.push([confirmed.latitude, confirmed.longitude]);
    }

    if (points.length === 1) {
      map.setView(points[0], 15);
    } else if (points.length > 1) {
      map.fitBounds(L.latLngBounds(points), { padding: [32, 32] });
    }
  }, [registered, confirmed]);

  return <div ref={containerRef} className="h-full w-full min-w-0" />;
}
