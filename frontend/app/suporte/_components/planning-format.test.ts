import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { SupportPlanItem } from "@/lib/types";

import { assigneesLabel, avatarColor, dateLabel, deadlineInfo, dueLabel, durationText, initials, progressPercent } from "./planning-format";

const item = (overrides: Partial<SupportPlanItem> = {}): SupportPlanItem => ({
  id: 1, kind: "task", parent_id: null, parent_title: null, title: "Revisar fila", description: null,
  status: "planned", priority: "medium", due_date: null, overdue: false, assignees: [], result: null,
  completed_at: null, archived: false, version: 1, created_by_name: "Admin",
  created_at: "2026-10-21T10:00:00Z", updated_at: "2026-10-21T10:00:00Z",
  tasks_total: 0, tasks_done: 0, updates_count: 0, ...overrides,
});

describe("formatação da aba Especialista/Analista", () => {
  it("formata a data sem deslocar o dia pelo fuso", () => {
    expect(dateLabel("2026-11-01")).toBe("01/11/2026");
    expect(dateLabel(null)).toBe("—");
  });

  it("marca atraso e ausência de prazo", () => {
    expect(dueLabel(item())).toBe("Sem prazo");
    expect(dueLabel(item({ due_date: "2026-10-01", overdue: true }))).toBe("01/10/2026 · atrasado");
    expect(dueLabel(item({ due_date: "2026-12-01" }))).toBe("01/12/2026");
  });

  it("calcula o progresso só quando há tarefas", () => {
    expect(progressPercent(item())).toBeNull();
    expect(progressPercent(item({ tasks_total: 3, tasks_done: 1 }))).toBe(33);
  });

  it("junta os dois responsáveis e avisa quando não há nenhum", () => {
    expect(assigneesLabel(item())).toBe("Sem responsável");
    expect(assigneesLabel(item({ assignees: [{ id: 1, name: "Ana" }, { id: 2, name: "Beto" }] }))).toBe("Ana e Beto");
  });
});

describe("barra de prazo do cartão", () => {
  const now = new Date("2026-10-21T12:00:00");

  it("formata a duração em dias e horas, ou horas e minutos", () => {
    expect(durationText(3 * 86_400_000 + 4 * 3_600_000)).toBe("3 dias 4 horas");
    expect(durationText(86_400_000)).toBe("1 dia");
    expect(durationText(5 * 3_600_000 + 20 * 60_000)).toBe("5 horas 20 min");
    expect(durationText(-1000)).toBe("0 min");
  });

  it("mostra restante e 'Em dia' quando o prazo ainda está longe", () => {
    const info = deadlineInfo(item({ due_date: "2026-11-21", created_at: "2026-10-21T08:00:00" }), now);
    expect(info.tone).toBe("ok");
    expect(info.badge).toBe("Em dia");
    expect(info.detail).toMatch(/^Restante: 31 dias/);
    expect(info.percent).toBeLessThan(10);
  });

  it("avisa atenção quando já passou de 80% do tempo", () => {
    const info = deadlineInfo(item({ due_date: "2026-10-22", created_at: "2026-10-01T00:00:00" }), now);
    expect(info.tone).toBe("warn");
    expect(info.badge).toBe("Atenção");
  });

  it("usa o atraso do backend e mostra há quanto tempo venceu", () => {
    const info = deadlineInfo(item({ due_date: "2026-10-19", overdue: true }), now);
    expect(info).toMatchObject({ tone: "late", percent: 100, badge: "Atrasado" });
    expect(info.detail).toMatch(/^Atraso: 1 dia/);
  });

  it("trata concluído, cancelado e sem prazo", () => {
    expect(deadlineInfo(item({ status: "done", completed_at: "2026-10-20T10:00:00Z" }), now)).toMatchObject({ tone: "done", percent: 100 });
    expect(deadlineInfo(item({ status: "canceled" }), now).detail).toBe("Cancelado");
    expect(deadlineInfo(item(), now)).toMatchObject({ tone: "none", detail: "Sem prazo", badge: "" });
  });

  it("gera iniciais e cor estável por pessoa", () => {
    expect(initials("Paulo Alves")).toBe("PA");
    expect(initials("maria da silva souza")).toBe("MS");
    expect(initials("Ana")).toBe("A");
    expect(initials("  ")).toBe("?");
    expect(avatarColor(3)).toBe(avatarColor(3));
  });
});

describe("chamadas da API do planejamento", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("monta os filtros da listagem e envia a versão ao registrar andamento", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0 }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await api.supportPlanItems({ status: "planned,blocked", assignee_id: 7, q: "fila", only_overdue: true });
    await api.addSupportPlanProgress(5, { version: 3, text: "Feito", status: "done", result: "ok" });

    const listUrl = String(fetchMock.mock.calls[0][0]);
    expect(listUrl).toContain("/support/planning/items?");
    expect(listUrl).toContain("status=planned%2Cblocked");
    expect(listUrl).toContain("assignee_id=7");
    expect(listUrl).toContain("only_overdue=true");
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/support\/planning\/items\/5\/updates$/);
    expect(fetchMock.mock.calls[1][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ version: 3, text: "Feito", status: "done", result: "ok" });
  });
});
