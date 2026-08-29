"use client";

import { Eye, EyeOff, Lock, Loader2, Mail, ShieldCheck } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusToast } from "@/components/ui/status-toast";
import { api } from "@/lib/api";
import type { LoginResult, PortalInviteStatus } from "@/lib/types";

type Props = {
  token: string;
  /** Disparado só depois que o backend confirma o convite aceito - o pai decide o que fazer a
   *  seguir (guardar o token de acesso e ir para o Portal, que assume dali pra frente). */
  onAccepted: (result: LoginResult) => void;
};

export function InviteAccept({ token, onAccepted }: Props) {
  const [status, setStatus] = useState<PortalInviteStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const newPasswordId = useId();
  const confirmPasswordId = useId();

  useEffect(() => {
    let active = true;
    async function loadStatus() {
      setLoadingStatus(true);
      try {
        const data = await api.inviteStatus(token);
        if (active) setStatus(data);
      } catch {
        if (active) setStatus({ valid: false, email: null, collaborator_name: null, reason: "Não foi possível validar o convite." });
      } finally {
        if (active) setLoadingStatus(false);
      }
    }
    loadStatus();
    return () => {
      active = false;
    };
  }, [token]);

  // Feedback imediato no cliente - a política de senha (mínimo 8 caracteres) mora no backend, o
  // mesmo limite usado no primeiro acesso (Fase 1) e na troca voluntária de senha (Fase 2A).
  function validate(): boolean {
    const errors: Record<string, string> = {};
    if (newPassword.length < 8) errors.newPassword = "A senha precisa de pelo menos 8 caracteres.";
    if (newPassword !== confirmPassword) errors.confirmPassword = "As senhas não são iguais.";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const result = await api.acceptInvite({ token, new_password: newPassword, confirm_password: confirmPassword });
      onAccepted(result);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Não foi possível concluir o convite.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-blue-950/10 md:grid-cols-[1fr_1.1fr]">
        {/* Mesmo ajuste responsivo do WorkspaceLogin/FirstAccessOnboarding: painel azul aparece em
            toda largura de tela, empilhado acima do formulário no mobile. */}
        <div className="uni-gradient relative flex flex-col overflow-hidden p-6 text-white sm:p-8 md:p-10">
          <img src="/brand/uni-logo-white.png" alt="" className="h-8 w-auto self-start object-contain drop-shadow-sm md:h-9" />
          <div className="mt-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-white/85">
              <Mail className="h-3.5 w-3.5" aria-hidden="true" />
              Convite
            </span>
            <h2 className="mt-4 text-2xl font-semibold leading-[1.15] tracking-tight md:mt-5 md:text-3xl">Bem-vindo(a) ao ecossistema UNI</h2>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/80 md:mt-3">
              Escolha sua própria senha para ativar o acesso. Ninguém mais vê nem escolhe essa senha por você.
            </p>
          </div>
          <div className="hidden flex-1 md:block" />
          <p className="mt-6 hidden text-xs text-white/60 md:mt-8 md:block">UNI Internet · Ecossistema operacional</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-6 p-8 sm:p-10 md:p-12" noValidate>
          <div className="hidden md:block">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-950">Bem-vindo(a) ao ecossistema UNI</h1>
            <p className="mt-2 text-sm text-slate-500">Escolha sua própria senha para ativar o acesso.</p>
          </div>

          {loadingStatus ? (
            <div className="flex items-center gap-3 rounded-xl border bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Verificando convite
            </div>
          ) : !status?.valid ? (
            <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {status?.reason || "Convite inválido, expirado ou já utilizado."}
            </p>
          ) : (
            <div className="grid gap-5">
              <div className="rounded-xl border bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Convite para <span className="font-medium text-slate-950">{status.email}</span>
                {status.collaborator_name ? (
                  <>
                    {" "}
                    - vinculado a <span className="font-medium text-slate-950">{status.collaborator_name}</span>
                  </>
                ) : null}
              </div>

              <div className="grid gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Sua senha</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-1.5">
                    <Label htmlFor={newPasswordId}>Nova senha</Label>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                      <Input
                        id={newPasswordId}
                        className="px-9 focus-visible:ring-[#2d5fff]"
                        type={showPassword ? "text" : "password"}
                        autoComplete="new-password"
                        value={newPassword}
                        onChange={(event) => setNewPassword(event.target.value)}
                        autoFocus
                      />
                      <button
                        type="button"
                        aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                        className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
                        onClick={() => setShowPassword((value) => !value)}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                      </button>
                    </div>
                    {fieldErrors.newPassword ? (
                      <p className="text-xs text-rose-600">{fieldErrors.newPassword}</p>
                    ) : (
                      <p className="text-xs text-slate-400">Pelo menos 8 caracteres.</p>
                    )}
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor={confirmPasswordId}>Confirmar senha</Label>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                      <Input
                        id={confirmPasswordId}
                        className="pl-9 focus-visible:ring-[#2d5fff]"
                        type={showPassword ? "text" : "password"}
                        autoComplete="new-password"
                        value={confirmPassword}
                        onChange={(event) => setConfirmPassword(event.target.value)}
                      />
                    </div>
                    {fieldErrors.confirmPassword ? <p className="text-xs text-rose-600">{fieldErrors.confirmPassword}</p> : null}
                  </div>
                </div>
              </div>

              <Button type="submit" disabled={submitting} className="mt-1 w-full rounded-xl">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                {submitting ? "Ativando..." : "Definir senha e entrar"}
              </Button>
            </div>
          )}
        </form>
      </div>
      <StatusToast error={submitError} onDismissError={() => setSubmitError(null)} />
    </main>
  );
}
