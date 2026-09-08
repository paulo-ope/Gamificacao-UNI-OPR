"use client";

import { Lock, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { SectionCard } from "@/components/ui/section-card";

export type OverviewBlockState = {
  /** Carregando pela primeira vez (recarga com dado na tela não deve piscar skeleton). */
  loading?: boolean;
  error?: string | null;
  /** Usuário não tem a permissão que o bloco exige. */
  denied?: boolean;
  /** Consulta respondeu, mas sem nada para mostrar. */
  empty?: boolean;
};

/**
 * Moldura padrão de um bloco da Visão Geral.
 *
 * A tela é compartilhada entre perfis (diretoria, coordenação regional, supervisão), então cada
 * bloco precisa se degradar sozinho: sem permissão, sem dado ou com erro, o resto da tela
 * continua útil. Centralizar os quatro estados aqui evita a alternativa ruim - repetir loading,
 * erro, vazio e bloqueado em cada um dos blocos.
 */
export function OverviewBlock({
  eyebrow,
  title,
  subtitle,
  badge,
  actions,
  state,
  deniedLabel = "Seu perfil não tem acesso a este indicador.",
  emptyLabel = "Sem dados para o filtro selecionado.",
  contentClassName,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  actions?: ReactNode;
  state?: OverviewBlockState;
  deniedLabel?: string;
  emptyLabel?: string;
  contentClassName?: string;
  children: ReactNode;
}) {
  return (
    <SectionCard
      eyebrow={eyebrow}
      title={title}
      subtitle={subtitle}
      badge={badge}
      actions={actions}
      contentClassName={contentClassName}
    >
      <OverviewBlockBody state={state} deniedLabel={deniedLabel} emptyLabel={emptyLabel}>
        {children}
      </OverviewBlockBody>
    </SectionCard>
  );
}

function OverviewBlockBody({
  state,
  deniedLabel,
  emptyLabel,
  children,
}: {
  state?: OverviewBlockState;
  deniedLabel: string;
  emptyLabel: string;
  children: ReactNode;
}) {
  if (state?.denied) {
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
        <Lock className="h-4 w-4 shrink-0 text-slate-400" />
        {deniedLabel}
      </p>
    );
  }
  if (state?.error) {
    return (
      <p className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{state.error}</span>
      </p>
    );
  }
  if (state?.loading) {
    return (
      <div className="space-y-2" aria-label="Carregando indicador" aria-busy="true">
        <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
        <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
        <div className="h-4 w-3/4 animate-pulse rounded bg-slate-100" />
      </div>
    );
  }
  if (state?.empty) {
    return <p className="py-6 text-center text-sm text-slate-500">{emptyLabel}</p>;
  }
  return <>{children}</>;
}
