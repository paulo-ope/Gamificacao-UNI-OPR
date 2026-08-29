"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { InviteAccept } from "@/components/portal/invite-accept";
import { setAuthToken } from "@/lib/api";
import type { LoginResult } from "@/lib/types";

export default function InvitePage() {
  return (
    <Suspense fallback={<main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Carregando convite...</main>}>
      <InvitePageContent />
    </Suspense>
  );
}

function InvitePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  function handleAccepted(result: LoginResult) {
    // Mesmo mecanismo do login normal (`useWorkspaceAuth().login`) - guarda o token e manda pro
    // Portal, que assume dali pra frente (a pessoa ainda tem o primeiro acesso da Fase 1 pendente,
    // o Portal já sabe mostrar o onboarding sozinho via `portal_first_access_required`).
    setAuthToken(result.access_token);
    router.push("/portal");
  }

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 text-center text-sm text-slate-600">
        Link de convite incompleto. Confira se copiou o endereço inteiro.
      </main>
    );
  }

  return <InviteAccept token={token} onAccepted={handleAccepted} />;
}
