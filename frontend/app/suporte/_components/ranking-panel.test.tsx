import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SupportRanking, SupportRankingRow } from "@/lib/types";
import { api } from "@/lib/api";
import { RankingView } from "./ranking-panel";

const row = (overrides: Partial<SupportRankingRow> = {}): SupportRankingRow => ({
  attendant_id: "one", name: "Pessoa de teste", active: true, position: 1, attendances: 405,
  rating: { value: 4.62, points: 5, partial: false },
  tmr: { value: 185, points: -2, partial: true },
  calls: { value: 96, points: 160, partial: false, detail: "8 blocos de 12 (+160)" },
  total_points: 163, ...overrides,
});
const data = (rows: SupportRankingRow[]): SupportRanking => ({
  date_from: "2026-10-01", date_to: "2026-10-16", months: [{ date_from: "2026-10-01", date_to: "2026-10-31" }],
  rows, rules: [{ key: "calls", label: "Ligações", lines: ["Regra retornada pela API"] }],
  tie_break: "Desempate: menor TMR e, depois, maior avaliação.", not_included: "Critérios não incluídos, conforme a API.",
});
const render = (ranking: SupportRanking | null, overrides: Partial<Parameters<typeof RankingView>[0]> = {}) => renderToStaticMarkup(
  <RankingView data={ranking} loading={false} error={null} onMonthChange={() => {}} onRefresh={() => {}} {...overrides} />,
);

describe("ranking mensal do suporte", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("consulta o endpoint mensal existente ao mudar o mês e retorna a resposta sem recalcular pontos", async () => {
    const response = data([row()]);
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(response), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.supportRanking()).resolves.toEqual(response);
    await expect(api.supportRanking("2026-09-01")).resolves.toEqual(response);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/support\/ranking$/);
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/support\/ranking\?month=2026-09-01$/);
    expect(fetchMock.mock.calls[1][1].cache).toBe("no-store");
  });

  it("preserva pontos e posições da API, incluindo pontuações empatadas", () => {
    const rows = [row(), row({ attendant_id: "two", name: "Segundo colaborador", position: 2, total_points: 68 }), row({ attendant_id: "three", name: "Terceiro colaborador", position: 3, total_points: 68 })];
    const snapshot = JSON.stringify(rows);
    const html = render(data(rows));
    expect(html).toContain("163");
    expect(html).toContain("2º lugar");
    expect(html).toContain("3º lugar");
    expect(html.indexOf("Segundo colaborador")).toBeLessThan(html.indexOf("Terceiro colaborador"));
    expect(JSON.stringify(rows)).toBe(snapshot);
    expect(html).toContain("Desempate: menor TMR");
  });

  it("formata as métricas sem refazer cálculos e mantém detalhes e cobertura parcial", () => {
    const html = render(data([row()]));
    expect(html).toContain("4,62");
    expect(html).toContain("00:03:05");
    expect(html).toContain('aria-label="-2 pontos"');
    expect(html).toContain('aria-label="+160 pontos"');
    expect(html).toContain("Amostra parcial");
    expect(html).toContain("8 blocos de 12 (+160)");
    expect(html).toContain("Regra retornada pela API");
  });

  it("não preenche o pódio com colaboradores inativos nem inventa pontos ausentes", () => {
    const html = render(data([row(), row({ attendant_id: "idle", name: "Pessoa inativa", active: false, position: null, total_points: null })]));
    expect(html).not.toContain("2º lugar");
    expect(html).toContain("o único colaborador classificado");
    expect(html).toContain("Pessoa inativa");
    expect(html).toContain("Sem atendimento no mês");
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("undefined");
  });

  it("trata dados incompletos sem apresentar zero como avaliação ou tempo", () => {
    const html = render(data([row({ name: "", total_points: null, rating: { value: null, points: 0, partial: false }, tmr: { value: null, points: 0, partial: false } })]));
    expect(html).toContain("Nome não informado");
    expect(html).not.toContain("00:00:00");
    expect(html).not.toContain("NaN");
  });

  it("não exibe os resultados antigos durante atualização ou erro", () => {
    const ranking = data([row({ name: "Resultado antigo" })]);
    expect(render(ranking, { loading: true })).not.toContain("Resultado antigo");
    expect(render(ranking, { loading: true })).toContain("Atualizando ranking do mês");
    const html = render(ranking, { error: "Falha de conexão" });
    expect(html).not.toContain("Resultado antigo");
    expect(html).toContain('role="alert"');
    expect(html).toContain("Tentar novamente");
  });

  it("oferece estado vazio, filtro mensal rotulado e cabeçalhos semânticos", () => {
    const html = render(data([]));
    expect(html).toContain("Nenhum atendimento da equipe neste mês");
    expect(html).toContain('for="support-ranking-month"');
    expect(html).toContain('value="2026-10-01" selected=""');
    expect(html.match(/scope="col"/g)).toHaveLength(6);
    expect(html).not.toContain("Líder do mês");
  });
});
