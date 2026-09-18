"use client";

import { Filter, Wifi, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MultiSelect } from "@/components/ui/multi-select";
import type { SupportIxcTicketFilterOption, SupportIxcTicketFilterOptions, SupportIxcTicketThemeOption } from "@/lib/types";

// Atalho pedido pelo usuário (2026-09-17): "filtrar só por assuntos de problema de internet" -
// os temas que cobrem perda/degradação de conexão e o suporte técnico que ela gera (ver
// classificação da taxonomia, item 8 do plano). Se um tema novo de conectividade for cadastrado
// no futuro, precisa ser adicionado aqui manualmente - não é derivado automaticamente do nome do
// tema (um "Wi-Fi" ou "Streaming" também soa "internet" sem ser o mesmo problema operacional).
const INTERNET_THEME_IDS = ["sem_conexao_fibra", "sem_conexao_radio_los", "suporte_tecnico_fibra", "suporte_tecnico_radio"];

function themeIdsCoveredBySubjects(themes: SupportIxcTicketThemeOption[], subjectIds: string[]): string[] {
  const selected = new Set(subjectIds);
  return themes.filter((theme) => theme.subject_ids.length > 0 && theme.subject_ids.every((id) => selected.has(id))).map((theme) => theme.id);
}

// Botão "Filtros (N)" recolhido por padrão, igual ao módulo Agendamento
// (`SchedulingFiltersBar`) - pedido explícito do usuário (2026-09-12). Vive num nível acima da
// Visão Geral/drill-down (ver frontend/app/suporte/page.tsx) porque o mesmo recorte de
// motivo/setor precisa valer nos dois, não só no drill-down.
export function IxcTicketFiltersBar({
  options,
  subjectIds,
  sectorIds,
  onChange,
}: {
  options: SupportIxcTicketFilterOptions | null;
  subjectIds: string[];
  sectorIds: string[];
  onChange: (next: { subjectIds: string[]; sectorIds: string[] }) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const activeCount = (subjectIds.length ? 1 : 0) + (sectorIds.length ? 1 : 0);
  const themes = options?.themes ?? [];
  const themeIds = themeIdsCoveredBySubjects(themes, subjectIds);
  const themeById = new Map(themes.map((theme) => [theme.id, theme]));

  function applyThemeIds(nextThemeIds: string[]) {
    const added = nextThemeIds.filter((id) => !themeIds.includes(id));
    const removed = themeIds.filter((id) => !nextThemeIds.includes(id));
    const nextSubjectIds = new Set(subjectIds);
    added.forEach((themeId) => themeById.get(themeId)?.subject_ids.forEach((id) => nextSubjectIds.add(id)));
    removed.forEach((themeId) => themeById.get(themeId)?.subject_ids.forEach((id) => nextSubjectIds.delete(id)));
    onChange({ subjectIds: Array.from(nextSubjectIds), sectorIds });
  }

  const internetActive = INTERNET_THEME_IDS.length > 0 && INTERNET_THEME_IDS.every((id) => themeIds.includes(id));

  function toggleInternetShortcut() {
    if (internetActive) {
      onChange({ subjectIds: [], sectorIds });
      return;
    }
    const nextSubjectIds = new Set<string>();
    INTERNET_THEME_IDS.forEach((themeId) => themeById.get(themeId)?.subject_ids.forEach((id) => nextSubjectIds.add(id)));
    onChange({ subjectIds: Array.from(nextSubjectIds), sectorIds });
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setExpanded((current) => !current)}>
          <Filter className="h-3.5 w-3.5" /> Filtros{activeCount ? ` (${activeCount})` : ""}
        </Button>
        {themes.length ? (
          <Button
            type="button"
            variant={internetActive ? "default" : "outline"}
            size="sm"
            onClick={toggleInternetShortcut}
            title="Mostrar só motivos de perda de conexão/suporte técnico (fibra e rádio)"
          >
            <Wifi className="h-3.5 w-3.5" /> Internet/Conectividade
          </Button>
        ) : null}
        {subjectIds.length ? (
          <Badge className="border-slate-200 bg-slate-100 text-[11px] text-slate-700">Motivo: {subjectIds.length}</Badge>
        ) : null}
        {sectorIds.length ? (
          <Badge className="border-slate-200 bg-slate-100 text-[11px] text-slate-700">Setor: {sectorIds.length}</Badge>
        ) : null}
        {activeCount ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[11px] text-blue-700"
            onClick={() => onChange({ subjectIds: [], sectorIds: [] })}
          >
            <X className="h-3 w-3" /> Limpar
          </Button>
        ) : null}
      </div>

      {expanded ? (
        <div className="mt-2 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-2">
          {themes.length ? (
            <label className="grid min-w-56 gap-1.5 text-[11px] font-medium text-slate-500">
              Tema (grupo de motivos)
              <MultiSelect<SupportIxcTicketThemeOption>
                ariaLabel="Filtrar por tema"
                values={themeIds}
                options={themes}
                getValue={(theme) => theme.id}
                formatOption={(theme) => theme.name}
                renderMeta={(theme) => <span className="text-[10px] text-slate-400">({theme.category_name})</span>}
                onChange={applyThemeIds}
              />
            </label>
          ) : null}
          <label className="grid min-w-56 gap-1.5 text-[11px] font-medium text-slate-500">
            Motivo
            <MultiSelect<SupportIxcTicketFilterOption>
              ariaLabel="Filtrar por motivo"
              values={subjectIds}
              options={options?.subjects ?? []}
              getValue={(option) => option.id}
              formatOption={(option) => option.name}
              onChange={(next) => onChange({ subjectIds: next, sectorIds })}
            />
          </label>
          {options?.sectors.length ? (
            <label className="grid min-w-56 gap-1.5 text-[11px] font-medium text-slate-500">
              Setor
              <MultiSelect<SupportIxcTicketFilterOption>
                ariaLabel="Filtrar por setor"
                values={sectorIds}
                options={options.sectors}
                getValue={(option) => option.id}
                formatOption={(option) => option.name}
                onChange={(next) => onChange({ subjectIds, sectorIds: next })}
              />
            </label>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
