const REGIONAL_CODE_MAP: Record<string, string> = {
  "6": "UNI - JI PARANA",
  "7": "UNI - MACHADINHO DOESTE",
  "8": "UNI - ROLIM DE MOURA",
  "9": "UNI - JARU",
  "10": "UNI - OURO PRETO DOESTE",
  "11": "UNI - NOVA BRASILANDIA DOESTE",
  "12": "UNI - PRESIDENTE MEDICI",
  "13": "UNI - SAO FELIPE DOESTE",
  "14": "UNI - ALVORADA DOESTE",
  "15": "UNI - ALTA FLORESTA DOESTE",
  "16": "UNI - SAO FRANCISCO DO GUAPORE",
  "17": "UNI - SAO FRANCISCO DO GUAPORE",
  "18": "UNI - SAO FRANCISCO DO GUAPORE"
};

const SAO_FRANCISCO_REGIONAL = "UNI - SAO FRANCISCO DO GUAPORE";

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
