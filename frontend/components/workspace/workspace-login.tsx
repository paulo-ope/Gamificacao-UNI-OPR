"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";


type Props = {
  isLoading: boolean;
  error: string | null;
  onLogin: (email: string, password: string) => Promise<unknown>;
};

export function WorkspaceLogin({ isLoading, error, onLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await onLogin(email, password);
    } catch {
      // A mensagem amigável é controlada pelo hook de autenticação.
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-xl shadow-blue-950/5">
        <img src="/brand/uni-logo.png" alt="UNI Internet" className="mb-8 h-9 w-auto" />
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">UNI Workspace</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Acesse o ecossistema</h1>
        <p className="mt-2 text-sm text-slate-500">Use o mesmo usuário da Gamificação.</p>
        <div className="mt-7 grid gap-4">
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            E-mail
            <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Senha
            <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="current-password" />
          </label>
          {error ? <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          <Button type="submit" disabled={isLoading} className="mt-1 w-full rounded-xl">
            {isLoading ? "Entrando..." : "Entrar"}
          </Button>
        </div>
      </form>
    </main>
  );
}
