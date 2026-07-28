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
  "16": "UNI - São Miguel do Guaporé",
  "17": "UNI - Seringueiras",
  "18": "UNI - São Francisco do Guaporé"
};

// A gamificação apura e paga São Miguel do Guaporé, Seringueiras e São Francisco do Guaporé como
// uma única regional (a Operação Analítica, que usa seu próprio código de exibição, mantém as 3
// separadas - ela não importa deste arquivo).
const REGIONAL_GROUP_ALIASES: Record<string, string> = {
  "UNI - SAO MIGUEL DO GUAPORE": "UNI - São Francisco do Guaporé",
  "UNI - SAO MIGUEL": "UNI - São Francisco do Guaporé",
  "SAO MIGUEL DO GUAPORE": "UNI - São Francisco do Guaporé",
  "SAO MIGUEL": "UNI - São Francisco do Guaporé",
  "UNI - SERINGUEIRAS": "UNI - São Francisco do Guaporé",
  "SERINGUEIRAS": "UNI - São Francisco do Guaporé",
  "UNI - SAO FRANCISCO DO GUAPORE": "UNI - São Francisco do Guaporé",
  "UNI - SAO FRANCISCO": "UNI - São Francisco do Guaporé",
  "SAO FRANCISCO DO GUAPORE": "UNI - São Francisco do Guaporé",
  "SAO FRANCISCO": "UNI - São Francisco do Guaporé"
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
