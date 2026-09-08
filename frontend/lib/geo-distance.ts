import type { Tone } from "@/lib/tones";

// Espelha os limiares de `backend/app/modules/localiza/service.py` (DISTANCE_*_MAX_METERS) -
// mudar a régua exige trocar os dois lados (o backend é quem calcula e persiste a classificação
// real; aqui só formata o que já veio pronto na resposta da API).
export type DistanceClassification = "compatible" | "minor_divergence" | "relevant_divergence" | "high_divergence";

const CLASSIFICATION_LABELS: Record<DistanceClassification, string> = {
  compatible: "Posição compatível",
  minor_divergence: "Pequena divergência",
  relevant_divergence: "Divergência relevante",
  high_divergence: "Forte divergência cadastral"
};

const CLASSIFICATION_TONES: Record<DistanceClassification, Tone> = {
  compatible: "emerald",
  minor_divergence: "amber",
  relevant_divergence: "amber",
  high_divergence: "red"
};

export function distanceClassificationLabel(classification: DistanceClassification): string {
  return CLASSIFICATION_LABELS[classification];
}

export function distanceClassificationTone(classification: DistanceClassification): Tone {
  return CLASSIFICATION_TONES[classification];
}

export function formatDistanceMeters(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2).replace(".", ",")} km`;
  return `${Math.round(meters)} m`;
}

export function googleMapsUrl(latitude: number, longitude: number): string {
  return `https://www.google.com/maps?q=${latitude},${longitude}`;
}
