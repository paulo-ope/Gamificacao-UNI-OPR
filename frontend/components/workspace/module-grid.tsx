"use client";

import Link from "next/link";

import type { WorkspaceVisibleModule } from "@/lib/types";
import { moduleIcon } from "@/lib/workspace-navigation";

/**
 * Grade de cartões dos módulos do ecossistema.
 *
 * Extraída da tela inicial para poder ser reaproveitada na tela `/modulos` dentro da casca de
 * aplicação: a entrada do sistema passou a ser a Visão Geral, mas a grade continua sendo a forma
 * mais legível de descobrir os módulos - e continua igual para quem já estava acostumado com ela.
 */
export function WorkspaceModuleGrid({ modules }: { modules: WorkspaceVisibleModule[] }) {
  if (!modules.length) {
    return (
      <p className="rounded-2xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
        Nenhum módulo está liberado para o seu perfil. Fale com quem administra o ecossistema.
      </p>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {modules.map((module) => {
        const Icon = moduleIcon(module.key);
        return (
          <Link
            key={module.key}
            href={module.web_path}
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-uni-royal/40 hover:shadow-lg"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-uni-royal/10 text-uni-royal">
              <Icon className="h-5 w-5" />
            </div>
            <h3 className="mt-4 text-base font-semibold text-slate-950">{module.name}</h3>
            <p className="mt-1.5 text-sm leading-6 text-slate-500">{module.description}</p>
            <p className="mt-4 text-sm font-semibold text-uni-royal group-hover:underline">Abrir módulo →</p>
          </Link>
        );
      })}
    </div>
  );
}
