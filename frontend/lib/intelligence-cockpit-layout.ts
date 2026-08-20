export type CockpitWidgetSize = "S" | "M" | "L" | "XL";

const DEFAULT_WIDGET_SIZE: Record<string, CockpitWidgetSize> = {
  overall_status: "M",
  cockpit_content: "M",
  ai_insights: "M",
  active_alerts: "L",
  active_incidents: "L",
  production: "M",
  backlog: "M",
  sla: "M",
  monitor_health: "M",
};

export function configuredCockpitWidgetSize(config: Record<string, unknown>, key: string): CockpitWidgetSize {
  const sizes = config.widget_sizes;
  const value = sizes && typeof sizes === "object" && !Array.isArray(sizes) ? (sizes as Record<string, unknown>)[key] : null;
  if (value === "S" || value === "M" || value === "L" || value === "XL") return value;
  if (config.layout_mode === "DENSE") {
    return key === "active_alerts" || key === "active_incidents" || key === "cockpit_content" || key === "ai_insights" ? "M" : "S";
  }
  if (config.layout_mode === "FOCUS") {
    return key === "active_alerts" || key === "active_incidents" || key === "cockpit_content" || key === "ai_insights" ? "XL" : "M";
  }
  return DEFAULT_WIDGET_SIZE[key] ?? "M";
}
