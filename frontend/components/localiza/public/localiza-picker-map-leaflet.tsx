"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useRef } from "react";

// Ícone de pino desenhado à mão (`L.divIcon`) - o ícone PADRÃO do Leaflet (`L.marker` sem `icon`)
// depende de arquivos de imagem (`marker-icon.png`) cujo caminho o bundler do Next.js não resolve
// sozinho, resultando num ícone quebrado (achado real, reportado pelo usuário vendo a tela ao
// vivo). Mesma técnica já usada em `localiza-detail-map-leaflet.tsx`.
function pinIcon(color: string) {
  return L.divIcon({
    className: "",
    html: `<svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,0.35))">
      <path d="M16 0C7.163 0 0 7.163 0 16c0 11 16 26 16 26s16-15 16-26C32 7.163 24.837 0 16 0z" fill="${color}"/>
      <circle cx="16" cy="16" r="6.5" fill="white"/>
    </svg>`,
    iconSize: [32, 42],
    iconAnchor: [16, 42],
  });
}

const MARKER_COLOR = "#2563eb";

// Limiares de qualidade do GPS (raio de incerteza reportado pelo navegador) - só para o CÍRCULO e
// a cor dele; a classificação de divergência cadastral (compatible/minor_divergence/...) é outra
// coisa, calculada no backend contra a coordenada cadastrada.
function accuracyCircleColor(accuracyMeters: number): string {
  if (accuracyMeters <= 20) return "#16a34a";
  if (accuracyMeters <= 100) return "#d97706";
  return "#dc2626";
}

export function LocalizaPickerMapLeaflet({
  latitude,
  longitude,
  accuracyMeters,
  onChange,
}: {
  latitude: number;
  longitude: number;
  accuracyMeters: number;
  onChange: (latitude: number, longitude: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, { center: [latitude, longitude], zoom: 17, scrollWheelZoom: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    // Círculo de incerteza do GPS - fica FIXO na posição e no raio ORIGINAIS (nunca acompanha o
    // marcador se ele for arrastado): representa "o GPS disse que você está em algum lugar aqui
    // dentro", o marcador é a resposta final e mais precisa que a pessoa confirma. Pedido do
    // usuário: dar um indício visual de quando a localização veio imprecisa.
    if (accuracyMeters > 5) {
      const circle = L.circle([latitude, longitude], {
        radius: accuracyMeters,
        color: accuracyCircleColor(accuracyMeters),
        fillColor: accuracyCircleColor(accuracyMeters),
        fillOpacity: 0.12,
        weight: 1.5,
      }).addTo(map);
      // Com pouca precisão (raio grande), o zoom fixo de 17 deixaria o círculo enorme, fora da
      // área visível - sem isso a "bolha de incerteza" fica invisível bem quando mais importa
      // (achado real: com 4 km de imprecisão, nada do aviso aparecia no mapa). Enquadra o círculo
      // inteiro só quando ele é maior que a área que o zoom padrão mostraria.
      if (accuracyMeters > 80) map.fitBounds(circle.getBounds(), { padding: [24, 24] });
    }

    const marker = L.marker([latitude, longitude], { draggable: true, icon: pinIcon(MARKER_COLOR) }).addTo(map);
    marker.on("dragend", () => {
      const position = marker.getLatLng();
      onChangeRef.current(position.lat, position.lng);
    });
    map.on("click", (event: L.LeafletMouseEvent) => {
      marker.setLatLng(event.latlng);
      onChangeRef.current(event.latlng.lat, event.latlng.lng);
    });

    mapRef.current = map;
    markerRef.current = marker;

    const resizeObserver = new ResizeObserver(() => map.invalidateSize());
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
      delete (container as unknown as { _leaflet_id?: number })._leaflet_id;
    };
    // Mapa nasce uma vez com a posição inicial - depois disso a posição só muda por arrastar o
    // marcador ou clicar no mapa (`marker.setLatLng`), nunca por re-render deste componente.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={containerRef} className="h-full w-full min-w-0" />;
}
