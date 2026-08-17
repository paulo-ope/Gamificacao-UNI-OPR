// Traduções centralizadas do UNI Intelligence - único lugar que mapeia os valores técnicos
// (enum/slug em inglês, iguais em banco/API/MCP) para o texto exibido ao usuário em português.
// NUNCA espalhar esses mapas/ternários pelos componentes - qualquer tela nova que precise exibir
// um desses valores importa daqui. Os valores técnicos em si (chaves destes mapas) nunca mudam -
// só o texto mostrado na UI.

export const PROFILE_PURPOSE_LABELS: Record<string, string> = {
  MATRIX_TV: "TV Matriz",
  REGIONAL_TV: "TV Regional",
  EXECUTIVE: "Executivo",
  INCIDENT_ROOM: "Sala de Incidentes",
  NOC: "NOC",
};

export const CONTENT_TYPE_LABELS: Record<string, string> = {
  AI_INSIGHT: "Análise da IA",
  MANUAL_MESSAGE: "Mensagem Manual",
  ANNOUNCEMENT: "Comunicado",
  OPERATIONAL_PRIORITY: "Prioridade Operacional",
  INCIDENT_UPDATE: "Atualização de Incidente",
  MAINTENANCE_NOTICE: "Aviso de Manutenção",
  INFO: "Informação",
};

export const CONTENT_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Ativo",
  EXPIRED: "Expirado",
  DISMISSED: "Encerrado",
};

// Valores reais de IntelligenceAlert.status (ver backend/app/modules/intelligence/models.py) -
// achado real: a tela usava "ACTIVE"/"ACKNOWLEDGED", que não existem no enum de verdade (o filtro
// nunca batia com nenhum alerta, sempre voltava 0 registros mesmo com alertas ativos no banco).
export const ALERT_STATUS_LABELS: Record<string, string> = {
  NEW: "Novo",
  INVESTIGATING: "Investigando",
  CONFIRMED: "Confirmado",
  IN_PROGRESS: "Em andamento",
  RECOVERING: "Normalizando",
  RESOLVED: "Resolvido",
  DISMISSED: "Encerrado",
  EXPIRED: "Expirado",
};

export const SEVERITY_LABELS: Record<string, string> = {
  LOW: "Baixa",
  MEDIUM: "Média",
  HIGH: "Alta",
  CRITICAL: "Crítica",
  INFO: "Informação",
};

// NORMAL/ATTENTION/RISK/CRITICAL vêm de `overall_status`; NORMAL/ATTENTION/INCIDENT vêm de
// `display_mode`; ALERT/INCIDENT vêm de `kind` (alerta x incidente) - todos convivem no mesmo
// mapa porque nunca colidem entre si (nenhum widget mistura os três domínios ao mesmo tempo).
export const STATUS_WORD_LABELS: Record<string, string> = {
  NORMAL: "Normal",
  ATTENTION: "Atenção",
  RISK: "Risco",
  CRITICAL: "Crítico",
  INCIDENT: "Incidente",
  ALERT: "Alerta",
};

export const WIDGET_LABELS: Record<string, string> = {
  overall_status: "Status Geral",
  active_alerts: "Alertas Ativos",
  active_incidents: "Incidentes Ativos",
  production: "Produção",
  backlog: "Backlog",
  sla: "SLA",
  monitor_health: "Saúde dos Monitores",
  cockpit_content: "Conteúdo do Cockpit",
  ai_insights: "Inteligência da IA",
};

export const FILTER_FIELD_LABELS: Record<string, string> = {
  regionals: "Regionais",
  cities: "Cidades",
  sectors: "Setores",
  os_subjects: "Assuntos de O.S.",
  team_models: "Modelos de Equipe",
  responsibles: "Responsáveis",
  severity: "Severidade",
  status: "Status",
  content_type: "Tipo de conteúdo",
};

export const SETTINGS_FIELD_LABELS: Record<string, string> = {
  purpose: "Finalidade",
  scope: "Escopo",
  widgets: "Blocos exibidos",
  refresh_seconds: "Atualização automática",
  active: "Ativo",
  valid_from: "Exibir a partir de",
  valid_until: "Exibir até",
  content_type: "Tipo de conteúdo",
  profile: "Perfil da TV",
};

// origem da publicação (IA/GESTÃO/SISTEMA/MONITOR) - mesma distinção visual usada na TV e na
// Administração de Publicações, nunca duas fontes de verdade para o mesmo texto.
export const SOURCE_TYPE_LABELS: Record<string, string> = {
  AI: "IA",
  MCP: "IA",
  USER: "Gestão",
  SYSTEM: "Sistema",
  MONITOR: "Monitor",
};

// Status de execução de uma run de monitor (MonitorRunOut.status / MonitorOut.last_run_status).
export const MONITOR_RUN_STATUS_LABELS: Record<string, string> = {
  RUNNING: "Em execução",
  COMPLETED: "Concluído",
  COMPLETED_WITH_WARNINGS: "Concluído com avisos",
  FAILED: "Falhou",
  INTERRUPTED: "Interrompido",
};

// Regras de Alertas (camada de configuração sobre os monitores/detectores existentes).
export const RULE_TYPE_LABELS: Record<string, string> = {
  OS_CONCENTRATION_AREA: "Concentração de O.S. em área",
  OS_CONCENTRATION_LINEAR: "Concentração linear de O.S.",
  OS_OPENING_ABOVE_AVERAGE: "Abertura de O.S. acima da média",
  OS_GROWTH_ANOMALY: "Crescimento anormal de O.S.",
  BACKLOG_THRESHOLD: "Backlog acima do limite",
  SLA_THRESHOLD: "SLA abaixo do limite",
  COLLECTIVE_OUTAGE: "Incidente coletivo (variante configurável)",
  MONITOR_UNHEALTHY: "Monitor com falhas consecutivas",
};

export const RULE_PARAM_LABELS: Record<string, string> = {
  min_count: "Quantas O.S. no mínimo",
  window_minutes: "Em quantos minutos",
  radius_meters: "Distância máxima entre elas (metros)",
  historical_comparison: "Só alertar se for acima do normal",
  min_multiplier_over_average: "Quanto acima do normal (vezes)",
  baseline_days: "Dias de histórico usados para comparar",
  threshold_value: "A partir de qual valor",
  window_days: "Nos últimos quantos dias",
  group_by: "Separar por",
  target_monitor_key: "Qual monitor observar",
  max_consecutive_failures: "Quantas falhas seguidas",
};

// Frase curta em linguagem simples, sempre visível abaixo do campo - pedido explícito do usuário
// ("falta explicação do que cada campo faz"). Sem jargão de raio/DBSCAN/multiplicador cru.
export const RULE_PARAM_HELP: Record<string, string> = {
  min_count: "Quantidade de O.S. juntas necessária para considerar isso um agrupamento.",
  window_minutes: "Período observado para contar as O.S. - só conta o que abriu dentro desse tempo.",
  radius_meters: "O.S. mais perto umas das outras do que essa distância entram no mesmo agrupamento.",
  historical_comparison: "Se ligado, só cria o alerta quando o volume também estiver maior que o normal para esse local/horário - não só pela quantidade mínima.",
  min_multiplier_over_average: "Ex.: 1,5 dispara quando o volume estiver 50% acima do normal. Só usado se \"Só alertar se for acima do normal\" estiver ligado.",
  baseline_days: "Quantos dias anteriores olhar para calcular o que é \"normal\" nesse local/horário.",
  threshold_value: "Número (ou %, no caso de SLA) que precisa ser ultrapassado para o alerta disparar.",
  window_days: "Período (em dias) usado para calcular o SLA que será comparado ao limite.",
  group_by: "Em vez de olhar a UNI inteira de uma vez, compara o volume separadamente para cada regional/cidade/assunto.",
  target_monitor_key: "Nome interno do monitor a acompanhar, ex.: collective_outage, sla_deterioration.",
  max_consecutive_failures: "Quantidade de execuções seguidas com erro para considerar esse monitor com problema.",
};

export const RULE_TOP_LEVEL_HELP: Record<string, string> = {
  severity: "Nível mostrado no alerta quando a regra dispara - não muda a chance de disparar, só a urgência exibida.",
  cooldown_minutes: "Depois que um alerta desta regra for encerrado, espera esse tempo antes de poder abrir outro igual - evita alerta piscando.",
  confirm_cycles: "Quantas vezes seguidas a condição precisa se repetir antes do alerta ser criado - use 2 ou mais para evitar alarme de pico isolado.",
  resolve_cycles: "Quantas execuções seguidas sem a condição acontecer para o alerta ser encerrado automaticamente.",
  active: "Regra desligada não é avaliada - fica salva, mas não gera alerta.",
};

export const GROUP_BY_LABELS: Record<string, string> = {
  regional: "Regional",
  city: "Cidade",
  os_subject: "Assunto de O.S.",
};

/** Lookup seguro: valor desconhecido cai para o próprio valor técnico (nunca quebra a tela por um
 * enum novo que ainda não ganhou tradução). */
export function labelFor(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return "-";
  return map[key] ?? key;
}
