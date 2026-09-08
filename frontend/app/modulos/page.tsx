"use client";

import { WorkspaceAppShell } from "@/components/workspace/app-shell";
import { WorkspaceModuleGrid } from "@/components/workspace/module-grid";
import { useVisibleModules } from "@/hooks/use-visible-modules";
import type { AuthUser } from "@/lib/types";

export default function ModulosPage() {
  return (
    <WorkspaceAppShell
      activePath="/modulos"
      title="Módulos"
      subtitle="Todos os módulos do ecossistema liberados para o seu perfil"
    >
      {(user) => <ModuleGridForUser user={user} />}
    </WorkspaceAppShell>
  );
}

function ModuleGridForUser({ user }: { user: AuthUser }) {
  const modules = useVisibleModules(user);
  return <WorkspaceModuleGrid modules={modules} />;
}
