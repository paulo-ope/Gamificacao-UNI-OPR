"use client";

import Link from "next/link";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, KeyRound, Loader2, Lock, Mail, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Step = "request" | "reset" | "done";

// Mesmo intervalo mínimo que o backend aplica entre dois pedidos de código (RESEND_COOLDOWN_SECONDS).
const RESEND_COOLDOWN_SECONDS = 60;

/** Esqueci minha senha: pede o e-mail, recebe um código de 6 dígitos e define a senha nova na mesma
 *  tela. Toda regra (validade do código, tentativas, política de senha) mora no backend - aqui só há
 *  feedback imediato. A resposta do passo 1 é sempre a mesma exista ou não a conta, então a tela
 *  nunca afirma que o e-mail "existe". */
export function PasswordReset() {
  const [step, setStep] = useState<Step>("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  const emailId = useId();
  const codeId = useId();
  const newPasswordId = useId();
  const confirmPasswordId = useId();
  const errorId = useId();

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setError(null);
    setNotice(null);
    if (!email.trim()) {
      setError("Informe o e-mail da sua conta.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.forgotPassword(email.trim());
      setNotice(result.message);
      setStep("reset");
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível enviar o código. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^\d{6}$/.test(code)) {
      setError("O código tem 6 dígitos.");
      return;
    }
    if (newPassword.length < 8) {
      setError("A senha precisa de pelo menos 8 caracteres.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("As senhas não são iguais.");
      return;
    }
    setBusy(true);
    try {
      await api.resetPassword({ email: email.trim(), code, new_password: newPassword, confirm_password: confirmPassword });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível redefinir a senha. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  const heading =
    step === "request" ? "Esqueci minha senha" : step === "reset" ? "Digite o código recebido" : "Senha redefinida";
  const description =
    step === "request"
      ? "Informe o e-mail da sua conta e enviaremos um código de 6 dígitos para você."
      : step === "reset"
        ? "Confira sua caixa de entrada (e o spam) e escolha uma senha nova."
        : "Pronto! Agora você já pode entrar com a senha nova.";

  return (
    <main className="workspace-surface flex min-h-dvh items-center justify-center px-4 py-6 sm:py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-blue-950/10 md:grid-cols-[1fr_1.1fr]">
        <div className="uni-gradient relative flex flex-col overflow-hidden p-6 text-white sm:p-8 md:p-10">
          <img src="/brand/uni-logo-white.png" alt="" className="h-8 w-auto self-start object-contain drop-shadow-sm md:h-9" />
          <div className="mt-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-white/85">
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              Recuperar acesso
            </span>
            <h2 className="mt-4 text-2xl font-semibold leading-[1.15] tracking-tight md:mt-5 md:text-3xl">{heading}</h2>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/80 md:mt-3">{description}</p>
          </div>
          <div className="hidden flex-1 md:block" />
          <p className="mt-6 hidden text-xs text-white/60 md:mt-8 md:block">UNI Internet · Ecossistema operacional</p>
        </div>

        <div className="flex flex-col justify-center gap-6 p-6 sm:p-10 md:p-12">
          <div className="hidden md:block">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-950">{heading}</h1>
            <p className="mt-2 text-sm text-slate-500">{description}</p>
          </div>

          {step === "request" ? (
            <form onSubmit={requestCode} className="grid gap-4" noValidate>
              <div className="grid gap-1.5">
                <Label htmlFor={emailId}>E-mail</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={emailId}
                    type="email"
                    autoComplete="email"
                    autoFocus
                    required
                    className="pl-9 focus-visible:ring-uni-royal"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </div>
              </div>
              {error ? (
                <p id={errorId} role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {error}
                </p>
              ) : null}
              <Button type="submit" disabled={busy} aria-describedby={error ? errorId : undefined} className="w-full rounded-xl">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Mail className="h-4 w-4" aria-hidden="true" />}
                {busy ? "Enviando..." : "Enviar código"}
              </Button>
            </form>
          ) : null}

          {step === "reset" ? (
            <form onSubmit={submitReset} className="grid gap-4" noValidate>
              {notice ? (
                <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  {notice}
                </p>
              ) : null}
              <div className="grid gap-1.5">
                <Label htmlFor={codeId}>Código de 6 dígitos</Label>
                <Input
                  id={codeId}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={6}
                  autoFocus
                  className="text-center text-2xl font-semibold tracking-[0.5em] focus-visible:ring-uni-royal"
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor={newPasswordId}>Nova senha</Label>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                    <Input
                      id={newPasswordId}
                      className="px-9 focus-visible:ring-uni-royal"
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                    />
                    <button
                      type="button"
                      aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                      aria-pressed={showPassword}
                      className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
                      onClick={() => setShowPassword((value) => !value)}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                    </button>
                  </div>
                  <p className="text-xs text-slate-400">Pelo menos 8 caracteres.</p>
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={confirmPasswordId}>Confirmar senha</Label>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                    <Input
                      id={confirmPasswordId}
                      className="pl-9 focus-visible:ring-uni-royal"
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                    />
                  </div>
                </div>
              </div>
              {error ? (
                <p id={errorId} role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {error}
                </p>
              ) : null}
              <Button type="submit" disabled={busy} aria-describedby={error ? errorId : undefined} className="w-full rounded-xl">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                {busy ? "Salvando..." : "Redefinir senha"}
              </Button>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                <button
                  type="button"
                  disabled={busy || cooldown > 0}
                  className="font-medium text-uni-impact hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
                  onClick={() => void requestCode()}
                >
                  {cooldown > 0 ? `Reenviar código em ${cooldown}s` : "Reenviar código"}
                </button>
                <button
                  type="button"
                  className="hover:underline"
                  onClick={() => {
                    setStep("request");
                    setCode("");
                    setError(null);
                    setNotice(null);
                  }}
                >
                  Usar outro e-mail
                </button>
              </div>
            </form>
          ) : null}

          {step === "done" ? (
            <div className="grid gap-4">
              <p role="status" className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                Sua senha foi alterada. Use a senha nova no próximo acesso.
              </p>
              <Link
                href="/portal"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                Ir para o login
              </Link>
            </div>
          ) : null}

          {step !== "done" ? (
            <Link href="/portal" className="inline-flex items-center justify-center gap-2 text-sm text-slate-500 hover:text-slate-800">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Voltar para o login
            </Link>
          ) : null}
        </div>
      </div>
    </main>
  );
}
