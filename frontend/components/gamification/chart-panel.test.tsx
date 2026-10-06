import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BarComparison, ChartPanel } from "./chart-panel";

describe("gamification chart presentation", () => {
  it("keeps a zero result visible without inventing a nonzero bar", () => {
    const html = renderToStaticMarkup(<BarComparison items={[{ label: "Sem pontuação", value: 0, formatted: "0 pts" }]} />);
    expect(html).toContain("0 pts");
    expect(html).toContain("width:0%");
    expect(html).not.toContain("NaN");
  });

  it("places negative and positive results on opposite sides of zero", () => {
    const html = renderToStaticMarkup(<BarComparison items={[
      { label: "Ajuste negativo", value: -20, formatted: "-20 pts" },
      { label: "Resultado positivo", value: 40, formatted: "40 pts" },
    ]} />);
    expect(html).toContain("-20 pts");
    expect(html).toContain("width:25%;right:50%");
    expect(html).toContain("width:50%;left:50%");
  });

  it("shows an empty state instead of drawing a chart without records", () => {
    const html = renderToStaticMarkup(<ChartPanel title="Resultados" description="Período atual" columns={["Nome", "Pontos"]} rows={[]}><span>Gráfico preenchido</span></ChartPanel>);
    expect(html).toContain("Nenhum dado neste recorte");
    expect(html).not.toContain("Gráfico preenchido");
  });
});
