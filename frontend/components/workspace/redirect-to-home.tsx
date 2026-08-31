"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Pedido do usuário em 2026-08-29: um único ponto de entrada de login (`/`) para todo o
// ecossistema - visitar a URL de um módulo (`/admin`, `/operacao`...) deslogado não deve mais
// mostrar um formulário de login próprio ali, só redirecionar pra tela inicial. `/portal` e
// `/gamificacao` ficam de fora de propósito: são públicos com fluxo de acesso próprio (Portal do
// Colaborador tem o link "Solicite aqui"; Gamificação usa autenticação legada, não
// `useWorkspaceAuth`/`WorkspaceLogin`).
export function RedirectToWorkspaceHome() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/");
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
      Redirecionando para o UNI Workspace...
    </main>
  );
}
