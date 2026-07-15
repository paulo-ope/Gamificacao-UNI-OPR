const REGIONAL_CODE_MAP: Record<string, string> = {
  "6": "UNI - Ji-Paraná",
  "7": "UNI - Machadinho D'Oeste",
  "8": "UNI - Rolim de Moura",
  "9": "UNI - Jaru",
  "10": "UNI - Ouro Preto do Oeste",
  "11": "UNI - Nova Brasilândia D'Oeste",
  "12": "UNI - Presidente Médici",
  "13": "UNI - São Felipe D'Oeste",
  "14": "UNI - Alvorada D'Oeste",
  "15": "UNI - Alta Floresta D'Oeste",
  "16": "UNI - São Francisco do Guaporé",
  "17": "UNI - São Francisco do Guaporé",
  "18": "UNI - São Francisco do Guaporé"
};

const SAO_FRANCISCO_REGIONAL = "UNI - São Francisco do Guaporé";

const REGIONAL_GROUP_ALIASES: Record<string, string> = {
  "UNI - SAO MIGUEL DO GUAPORE": SAO_FRANCISCO_REGIONAL,
  "UNI - SAO MIGUEL": SAO_FRANCISCO_REGIONAL,
  "SAO MIGUEL DO GUAPORE": SAO_FRANCISCO_REGIONAL,
  "SAO MIGUEL": SAO_FRANCISCO_REGIONAL,
  "UNI - SERINGUEIRAS": SAO_FRANCISCO_REGIONAL,
  "SERINGUEIRAS": SAO_FRANCISCO_REGIONAL,
  "UNI - SAO FRANCISCO DO GUAPORE": SAO_FRANCISCO_REGIONAL,
  "UNI - SAO FRANCISCO": SAO_FRANCISCO_REGIONAL,
  "SAO FRANCISCO DO GUAPORE": SAO_FRANCISCO_REGIONAL,
  "SAO FRANCISCO": SAO_FRANCISCO_REGIONAL
};

function regionalKey(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().trim().replace(/\s+/g, " ");
}

export function normalizeRegional(value: string | null | undefined) {
  if (!value) return "NAO IDENTIFICADO";
  const mapped = REGIONAL_CODE_MAP[value.trim()] ?? value.trim();
  return REGIONAL_GROUP_ALIASES[regionalKey(mapped)] ?? mapped;
}

export function regionalName(value: string | null | undefined) {
  return normalizeRegional(value);
}
