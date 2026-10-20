import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { SupportContactRadar, SupportContactRadarCity, SupportContactRadarNeighborhood, SupportContactRadarProtocol, SupportContactRadarRegional } from "@/lib/types";
import { ContactRadarView, ProtocolRow, RegionalTree, defaultDepartmentIds, rangeProblem, type RadarQuery } from "./contact-radar-panel";
import { opaTagClass } from "./opa-tag-chip";

const stats = { contacts: 9, customers: 7, baseline: 1.4, ratio: 5, elevated: false };
const hood = (neighborhood: string, overrides: Partial<SupportContactRadarNeighborhood> = {}): SupportContactRadarNeighborhood => ({
  neighborhood, ...stats, latitude: null, longitude: null, ...overrides,
});
const city = (name: string, neighborhoods: SupportContactRadarNeighborhood[], overrides: Partial<SupportContactRadarCity> = {}): SupportContactRadarCity => ({
  city: name, ...stats, latitude: null, longitude: null, neighborhoods, ...overrides,
});
const regional = (name: string, cities: SupportContactRadarCity[], overrides: Partial<SupportContactRadarRegional> = {}): SupportContactRadarRegional => ({
  regional: name, ...stats, cities, ...overrides,
});
const tree = (): SupportContactRadarRegional[] => [
  regional("UNI - JARU", [
    city("Jaru", [hood("Centro", { elevated: true }), hood("Setor 1", { ratio: 1 })], { elevated: true }),
    city("Theobroma", [hood("Zona Rural")]),
  ], { elevated: true }),
  regional("UNI - JI PARANA", [city("Ji-Paraná", [hood("Nova Brasília")])]),
];
const radar = (overrides: Partial<SupportContactRadar> = {}): SupportContactRadar => ({
  mode: "window", window_minutes: 60, date_from: null, date_to: null, generated_at: "2026-10-20T15:00:00Z", alerts_enabled: true,
  totals: { contacts: 120, customers: 90, located_contacts: 100, unlocated_contacts: 20, coverage_pct: 83.3 },
  by_channel: [{ channel: "whatsapp", contacts: 100 }, { channel: "pabx", contacts: 20 }],
  regionals: tree(),
  series: {
    bucket_minutes: 60,
    points: [
      { start: "2026-10-20T18:00:00Z", contacts: 30, located_contacts: 25, customers: 20, by_channel: { whatsapp: 26, pabx: 4 } },
      { start: "2026-10-20T19:00:00Z", contacts: 90, located_contacts: 75, customers: 60, by_channel: { whatsapp: 74, pabx: 16 } },
    ],
  },
  previous: { contacts: 100, customers: 60, coverage_pct: 80 },
  ...overrides,
});
const baseQuery: RadarQuery = { mode: "window", windowMinutes: 60, dateFrom: "2026-10-20", dateTo: "2026-10-20", channel: "", departmentIds: [] };
const departments = [{ value: "10", label: "Suporte Técnico" }, { value: "20", label: "Financeiro" }, { value: "30", label: "NOC" }];
const render = (data: SupportContactRadar | null, overrides: Partial<Parameters<typeof ContactRadarView>[0]> = {}) => renderToStaticMarkup(
  <ContactRadarView data={data} loading={false} error={null} query={baseQuery} departments={departments} onQueryChange={() => {}} onRefresh={() => {}} {...overrides} />,
);
const renderTree = (initialOpen: string[] = [], compare = true) => renderToStaticMarkup(
  <RegionalTree regionals={tree()} compare={compare} baselineLabel="Habitual" baselineHint="dica" initialOpen={initialOpen} />,
);

describe("Radar de Contatos", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("consulta o endpoint com janela, canal, período e departamentos", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(radar()), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await api.supportContactRadar({ window_minutes: 30, channel: "pabx" });
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/support\/opa\/contact-radar\?window_minutes=30&channel=pabx$/);
    await api.supportContactRadar({ window_minutes: 30, date_from: "2026-10-01", date_to: "2026-10-07", department_ids: ["10", "20"] });
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/support\/opa\/contact-radar\?date_from=2026-10-01&date_to=2026-10-07&department_id=10%2C20$/);
  });

  it("mostra o filtro por data e os atalhos nos dois modos; a janela só no ao vivo", () => {
    const live = render(radar(), { query: { ...baseQuery, departmentIds: ["10", "20"] } });
    expect(live).toContain("Suporte Técnico");
    expect(live).toContain("Financeiro");
    expect(render(radar())).toContain("Todos os departamentos");
    // Data sempre à vista, inclusive ao vivo.
    expect(live).toContain('type="date"');
    expect(live).toContain("Ao vivo");
    expect(live).toContain("Últimos 7 dias");
    expect(live).toContain("Últimas 24 horas");
    const range = render(radar({ mode: "range", window_minutes: null, date_from: "2026-10-01", date_to: "2026-10-07" }), { query: { ...baseQuery, mode: "range" } });
    expect(range).toContain('type="date"');
    expect(range).toContain("Últimos 7 dias");
    expect(range).not.toContain("Últimas 24 horas");
    expect(range).toContain("Período anterior");
  });

  it("já vem com Suporte Técnico e Financeiro, casando pelo nome sem acento nem caixa", () => {
    const options = [
      { value: "a", label: "Agendamentos" }, { value: "b", label: "Suporte Técnico" }, { value: "c", label: "FINANCEIRO" },
      { value: "d", label: "Suporte N2" }, { value: "e", label: "Financeiro Matriz" },
    ];
    expect(defaultDepartmentIds(options)).toEqual(["b", "c"]);
    expect(defaultDepartmentIds([])).toEqual([]);
  });

  it("valida o período escolhido", () => {
    const range = (dateFrom: string, dateTo: string): RadarQuery => ({ ...baseQuery, mode: "range", dateFrom, dateTo });
    expect(rangeProblem(baseQuery)).toBeNull();
    expect(rangeProblem(range("2026-10-01", "2026-10-31"))).toBeNull();
    expect(rangeProblem(range("2026-10-10", "2026-10-01"))).toMatch(/anterior/);
    expect(rangeProblem(range("2026-09-01", "2026-10-20"))).toMatch(/31 dias/);
    expect(rangeProblem(range("", "2026-10-01"))).toMatch(/Escolha/);
    expect(render(null, { query: range("2026-10-10", "2026-10-01"), problem: "A data final não pode ser anterior à inicial." })).toContain("A data final não pode ser anterior");
  });

  it("mostra os cartões no desenho dos Indicadores: números, variação contra o anterior e cobertura", () => {
    const html = render(radar());
    expect(html).toContain("Contatos no recorte - OPA");
    expect(html).toContain("Clientes localizados - IXC");
    expect(html).toContain("Cobertura da localização");
    expect(html).toContain("Regional mais acionada");
    expect(html).toContain("Cidade mais acionada");
    expect(html).toContain("Bairros acima do usual");
    expect(html).not.toContain("Contatos ao longo do tempo");
    expect(html).not.toContain("Clientes por regional");
    // 120 contatos contra a média de 100: +20%, comparado com a média dos 7 dias na janela ao vivo.
    expect(html).toContain("+20% vs. média dos 7 dias");
    expect(html).toContain("média dos 7 dias 80%");
    const range = render(radar({ mode: "range", window_minutes: null, date_from: "2026-10-01", date_to: "2026-10-07" }), { query: { ...baseQuery, mode: "range" } });
    expect(range).toContain("vs. período anterior");
  });

  it("não inventa variação quando o período anterior está vazio", () => {
    const html = render(radar({ previous: { contacts: 0, customers: 0, coverage_pct: null } }));
    expect(html).toContain("sem base de comparação");
  });

  it("bairros acima do usual: conta quando os alertas valem e some quando estão desligados", () => {
    expect(render(radar())).toContain("1 cidades · 1 regionais acima do usual");
    const off = render(radar({ alerts_enabled: false }));
    expect(off).toContain("alertas desligados: histórico ainda em carga");
  });

  it("mostra só as regionais, recolhidas, com a contagem de cidades", () => {
    const html = renderTree();
    expect(html).toContain("JARU");
    expect(html).toContain("JI PARANA");
    expect(html).toContain("2 cidades");
    expect(html).toContain("1 cidade");
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('aria-expanded="true"');
    // As cidades só aparecem depois do clique na regional.
    expect(html).not.toContain("Theobroma");
    expect(html).toContain("Expandir tudo");
  });

  it("ao abrir uma regional mostra as cidades; ao abrir a cidade, os bairros", () => {
    const regionalOpen = renderTree(["UNI - JARU"]);
    expect(regionalOpen).toContain("Jaru");
    expect(regionalOpen).toContain("Theobroma");
    expect(regionalOpen).toContain("2 bairros");
    expect(regionalOpen).not.toContain("Ji-Paraná");
    expect(regionalOpen).not.toContain("Zona Rural");
    const cityOpen = renderTree(["UNI - JARU", "UNI - JARU|Theobroma"]);
    expect(cityOpen).toContain("Zona Rural");
    expect(cityOpen).not.toContain("Setor 1");
  });

  it("destaca bairro acima do usual no aviso, mostra cobertura e não localizados", () => {
    const html = render(radar());
    expect(html).toContain("1 bairro com volume acima do usual");
    expect(html).toContain("Centro (Jaru)");
    expect(html).toContain("Acima do usual");
    expect(html).toContain("83,3%");
    expect(html).toContain("sem cliente identificado no OPA");
    expect(html).toContain("WhatsApp 100");
    expect(html).toContain("Ligação 20");
  });

  it("avisa quando os alertas estão desligados e não mostra comparação que enganaria", () => {
    const off = render(radar({ alerts_enabled: false }));
    expect(off).toContain("Alertas de volume desligados");
    expect(off).not.toContain("5×");
    expect(off).not.toContain("com volume acima do usual");
    expect(render(radar())).not.toContain("Alertas de volume desligados");
    expect(renderTree([], false)).not.toContain("Acima do usual");
  });

  it("mostra estado vazio, carregamento e erro", () => {
    expect(render(radar({ regionals: [] }))).toContain("Nenhum contato localizado neste recorte.");
    expect(render(null, { loading: true })).toContain("Carregando o radar");
    expect(render(null, { error: "Falhou" })).toContain("Falhou");
  });
});


describe("protocolos e etiquetas por cidade", () => {
  afterEach(() => vi.unstubAllGlobals());

  const protocol = (overrides: Partial<SupportContactRadarProtocol> = {}): SupportContactRadarProtocol => ({
    source_id: "abc", protocol: "UNI20261050885", opened_at: "2026-10-20T18:35:00Z", status: "F", channel: "whatsapp",
    department_name: "Financeiro", attendant_name: "Atendente Um", neighborhood: "Centro",
    tags: [{ id: "t1", name: "Sem conexão", color: "red", known: true }, { id: "t2", name: "IA Financeiro", color: "blue", known: true }],
    ...overrides,
  });

  it("pinta cada etiqueta na cor que ela tem no OPA e cai em cinza quando a cor é desconhecida", () => {
    expect(opaTagClass("red")).toContain("text-red-700");
    expect(opaTagClass("blue")).toContain("text-blue-700");
    expect(opaTagClass("gray")).toContain("text-slate-700");
    expect(opaTagClass("green")).toContain("emerald");
    expect(opaTagClass("yellow")).toContain("amber");
    expect(opaTagClass("purple")).toContain("violet");
    expect(opaTagClass("orange")).toContain("orange");
    expect(opaTagClass("RED")).toContain("text-red-700");
    expect(opaTagClass(null)).toBe(opaTagClass("gray"));
    expect(opaTagClass("rosa")).toBe(opaTagClass("gray"));
  });

  it("mostra o protocolo com o departamento e as etiquetas ao lado, e a data, o bairro, o canal e a situação", () => {
    const html = renderToStaticMarkup(<ul><ProtocolRow item={protocol()} /></ul>);
    expect(html).toContain("UNI20261050885");
    expect(html).toContain("Financeiro");
    expect(html).toContain("Sem conexão");
    expect(html).toContain("IA Financeiro");
    expect(html.indexOf("UNI20261050885")).toBeLessThan(html.indexOf("Sem conexão"));
    expect(html.indexOf("Sem conexão")).toBeLessThan(html.indexOf("IA Financeiro"));
    expect(html).toContain("text-red-700");
    expect(html).toContain("text-blue-700");
    // 18:35Z é 14:35 em Porto Velho.
    expect(html).toContain("20/10 14:35 · Centro · WhatsApp · Finalizado");
  });

  it("etiqueta sem cadastro aparece neutra, com o id do OPA no tooltip", () => {
    const html = renderToStaticMarkup(
      <ul><ProtocolRow item={protocol({ tags: [{ id: "690f472a", name: "Etiqueta sem cadastro", color: null, known: false }] })} /></ul>,
    );
    expect(html).toContain("Etiqueta sem cadastro");
    expect(html).toContain("id 690f472a");
    expect(html).toContain("text-slate-700");
  });

  it("protocolo sem etiqueta nem departamento não mostra chip", () => {
    const html = renderToStaticMarkup(<ul><ProtocolRow item={protocol({ tags: [], department_name: null })} /></ul>);
    expect(html).not.toContain("rounded-md border");
    expect(html).toContain("UNI20261050885");
  });

  it("abrir uma cidade mostra os bairros, sem protocolos: eles ficam em cada bairro", () => {
    const html = renderToStaticMarkup(
      <RegionalTree regionals={tree()} query={baseQuery} refreshKey="k" compare baselineLabel="Habitual" baselineHint="dica" initialOpen={["UNI - JARU", "UNI - JARU|Jaru"]} />,
    );
    expect(html).toContain("Centro");
    expect(html).toContain("Setor 1");
    expect(html).not.toContain("Protocolos");
    expect(html).not.toContain("Carregando protocolos");
  });

  it("abrir um bairro mostra os protocolos dele, e só dele", () => {
    const html = renderToStaticMarkup(
      <RegionalTree regionals={tree()} query={baseQuery} refreshKey="k" compare baselineLabel="Habitual" baselineHint="dica" initialOpen={["UNI - JARU", "UNI - JARU|Jaru", "UNI - JARU|Jaru|Centro"]} />,
    );
    expect(html).toContain("Protocolos");
    expect(html).toContain("Carregando protocolos");
    // Um bairro aberto, uma lista: o "Setor 1" fechado não carrega nada.
    expect(html.match(/Carregando protocolos/g)?.length).toBe(1);
    // A lista aparece logo abaixo do bairro aberto, antes do bairro seguinte.
    expect(html.indexOf("Centro")).toBeLessThan(html.indexOf("Carregando protocolos"));
    expect(html.indexOf("Carregando protocolos")).toBeLessThan(html.indexOf("Setor 1"));
  });

  it("sem recorte (query) o bairro aberto não busca protocolos", () => {
    const html = renderToStaticMarkup(
      <RegionalTree regionals={tree()} compare baselineLabel="Habitual" baselineHint="dica" initialOpen={["UNI - JARU", "UNI - JARU|Jaru", "UNI - JARU|Jaru|Centro"]} />,
    );
    expect(html).not.toContain("Protocolos");
  });

  it("dentro do bairro o protocolo não repete o nome do bairro", () => {
    const html = renderToStaticMarkup(<ul><ProtocolRow item={protocol()} showNeighborhood={false} /></ul>);
    expect(html).toContain("20/10 14:35 · WhatsApp · Finalizado");
    expect(html).not.toContain("Centro");
  });

  it("consulta os protocolos da cidade com o mesmo recorte do radar", async () => {
    const page = { total: 1, limit: 50, offset: 0, items: [protocol()] };
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(page), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await api.supportContactRadarProtocols({ regional: "UNI - JARU", city: "Jaru", neighborhood: "Setor 1", window_minutes: 60, channel: "pabx", department_ids: ["10", "20"], limit: 50 });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("neighborhood=Setor+1");
    expect(url).toContain("/support/opa/contact-radar/protocols?");
    expect(url).toContain("regional=UNI+-+JARU");
    expect(url).toContain("city=Jaru");
    expect(url).toContain("window_minutes=60");
    expect(url).toContain("channel=pabx");
    expect(url).toContain("department_id=10%2C20");
    await api.supportContactRadarProtocols({ regional: "UNI - JARU", city: "Jaru", date_from: "2026-10-01", date_to: "2026-10-07", offset: 50 });
    const byRange = String(fetchMock.mock.calls[1][0]);
    expect(byRange).toContain("date_from=2026-10-01&date_to=2026-10-07");
    expect(byRange).not.toContain("window_minutes");
    expect(byRange).toContain("offset=50");
  });
});
