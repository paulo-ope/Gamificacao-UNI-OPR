"use client";

import { useCallback, useRef, type Dispatch, type SetStateAction } from "react";

import { api } from "@/lib/api";
import type { SupportOpaAttendanceFilters } from "@/lib/types";

const splitValues = (value?: string) => (value ?? "").split(",").map((item) => item.trim()).filter(Boolean);

/** Teto de `limit` aceito por `/support/opa/breakdowns`. */
const MAX_ATTENDANTS = 200;

/**
 * Ao escolher departamentos no filtro do Suporte Interno, marca no filtro de Atendente quem
 * atendeu nesses departamentos dentro do período escolhido (mesma base do ranking "Atendentes com
 * mais volume"). Não é o cadastro do OPA: o sync de usuários não traz os departamentos de cada um,
 * então "pertence ao departamento" aqui significa "teve atendimento nele no período".
 *
 * As marcações são só um ponto de partida: o usuário desmarca/marca à mão e isso é respeitado.
 * Ao trocar ou limpar os departamentos, saem apenas os atendentes que ESTA regra marcou; os que o
 * usuário marcou por conta própria ficam.
 */
export function useDepartmentAttendantsSync({
  period,
  dateBasis,
  attendantId,
  setFilters,
}: {
  period: { date_from: string; date_to: string };
  /** Atendentes marcados agora (CSV); usado para não tratar uma marcação manual como automática. */
  attendantId?: string;
  dateBasis: SupportOpaAttendanceFilters["date_basis"];
  setFilters: Dispatch<SetStateAction<SupportOpaAttendanceFilters>>;
}) {
  const autoSelected = useRef<Set<string>>(new Set());
  const requestId = useRef(0);
  const latestAttendantId = useRef(attendantId);
  latestAttendantId.current = attendantId;

  return useCallback(
    async (departmentIds: string | undefined) => {
      const current = ++requestId.current;
      const previousAuto = autoSelected.current;
      const withoutAuto = (attendantId?: string) => splitValues(attendantId).filter((id) => !previousAuto.has(id));
      const apply = (attendantIds: string[], auto: Set<string>) => {
        autoSelected.current = auto;
        setFilters((filters) => ({
          ...filters,
          attendant_id: Array.from(new Set([...withoutAuto(filters.attendant_id), ...attendantIds])).join(",") || undefined,
        }));
      };

      if (!departmentIds) {
        apply([], new Set());
        return;
      }
      try {
        const result = await api.supportOpaBreakdowns("attendant", {
          date_from: period.date_from,
          date_to: period.date_to,
          date_basis: dateBasis,
          department_id: departmentIds,
          sort_by: "total",
          sort_dir: "desc",
          limit: MAX_ATTENDANTS,
        });
        // Uma troca de departamento mais nova já saiu: descarta esta resposta atrasada.
        if (current !== requestId.current) return;
        const ids = result.items.map((item) => item.id).filter((id): id is string => Boolean(id));
        const manual = new Set(withoutAuto(latestAttendantId.current));
        apply(ids, new Set(ids.filter((id) => !manual.has(id))));
      } catch {
        // Sem a sugestão o filtro continua utilizável: o usuário escolhe os atendentes à mão.
        if (current === requestId.current) apply([], new Set());
      }
    },
    [period.date_from, period.date_to, dateBasis, setFilters],
  );
}
