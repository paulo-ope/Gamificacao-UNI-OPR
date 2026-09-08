"use client";

import { Suspense } from "react";

import { OverviewScreen } from "@/components/overview/overview-screen";
import { WorkspaceAppShell } from "@/components/workspace/app-shell";

export default function VisaoGeralPage() {
  return (
    <WorkspaceAppShell
      activePath="/visao-geral"
      title="Visão Geral"
      subtitle="Macrovisão da operação, do suporte e da gamificação em uma tela"
    >
      {(user) => (
        // `useSearchParams` (o filtro desta tela vive na URL) exige um limite de Suspense no App Router.
        <Suspense
          fallback={
            <p className="py-16 text-center text-sm text-slate-500" aria-busy="true">
              Carregando a Visão Geral...
            </p>
          }
        >
          <OverviewScreen user={user} />
        </Suspense>
      )}
    </WorkspaceAppShell>
  );
}
