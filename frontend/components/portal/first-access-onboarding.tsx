"use client";

import { Eye, EyeOff, IdCard, Loader2, Lock, Mail, Phone, ShieldCheck, UserCheck } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusToast } from "@/components/ui/status-toast";
import { api } from "@/lib/api";
import { formatCpf, formatPhone, isValidCpf, onlyDigits } from "@/lib/masks";
import type { PortalFirstAccessStatus } from "@/lib/types";

type Props = {
  /** Disparado só depois que o backend confirma a conclusão - o pai decide o que fazer a seguir
   *  (no Portal: `useWorkspaceAuth().refresh()` pra sair do estado de pendência). */
  onComplete: () => void;
};

export function FirstAccessOnboarding({ onComplete }: Props) {
  const [status, setStatus] = useState<PortalFirstAccessStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [cpf, setCpf] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const cpfId = useId();
  const phoneId = useId();
  const emailId = useId();
  const newPasswordId = useId();
  const confirmPasswordId = useId();

  useEffect(() => {
    let active = true;
    async function loadStatus() {
      setLoadingStatus(true);
      setLoadError(null);
      try {
        const data = await api.portalFirstAccessStatus();
        if (!active) return;
        setStatus(data);
        setPhone(data.phone ? formatPhone(data.phone) : "");
        setEmail(data.email ?? "");
      } catch (err) {
        if (active) setLoadError(err instanceof Error ? err.message : "Não foi possível carregar seus dados.");
      } finally {
        if (active) setLoadingStatus(false);
      }
    }
    loadStatus();
    return () => {
      active = false;
    };
  }, []);

  // Validação básica no cliente: só feedback imediato, quem decide de verdade é o backend (o mesmo
  // algoritmo de CPF, a checagem de "já cadastrado e diverge" e a política de senha vivem só lá).
  function validate(): boolean {
    const errors: Record<string, string> = {};
    if (!isValidCpf(cpf)) errors.cpf = "CPF inválido. Confira os números.";
    if (onlyDigits(phone).length < 10) errors.phone = "Informe um telefone válido, com DDD.";
    if (!email.trim() || !email.includes("@")) errors.email = "Informe um e-mail válido.";
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
      await api.completePortalFirstAccess({
        cpf: onlyDigits(cpf),
        phone: formatPhone(phone),
        email: email.trim(),
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      onComplete();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Não foi possível concluir seu primeiro acesso.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-blue-950/10 md:grid-cols-[1fr_1.1fr]">
        {/* Painel azul agora aparece em toda largura de tela, não só a partir de `md` - mesmo
            ajuste do WorkspaceLogin (ver comentário lá): no mobile ele empilha em cima do
            formulário, com lista de destaques e rodapé escondidos pra não empurrar os campos pra
            fora da primeira tela. */}
        <div className="uni-gradient relative flex flex-col overflow-hidden p-6 text-white sm:p-8 md:p-10">
          {/* `self-start`: mesmo ajuste do WorkspaceLogin - sem isso, o flex-col estica a logo pra
              preencher a largura toda do painel, distorcendo a proporção original. */}
          <img src="/brand/uni-logo-white.png" alt="" className="h-8 w-auto self-start object-contain drop-shadow-sm md:h-9" />
          <div className="mt-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-white/85">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Primeiro acesso
            </span>
            <h2 className="mt-4 text-2xl font-semibold leading-[1.15] tracking-tight md:mt-5 md:text-3xl">Vamos confirmar seus dados</h2>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/80 md:mt-3">
              Só uma vez: confirme CPF e contato, e escolha uma senha nova antes de ver seu ranking, O.S. e fechamento.
            </p>
            <ul className="mt-5 hidden gap-3 md:mt-7 md:grid">
              <li className="flex items-center gap-3 text-sm text-white/90">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/10">
                  <UserCheck className="h-4 w-4" aria-hidden="true" />
                </span>
                CPF só confirma quem é você
              </li>
              <li className="flex items-center gap-3 text-sm text-white/90">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/10">
                  <IdCard className="h-4 w-4" aria-hidden="true" />
                </span>
                Nunca exibido por completo depois
              </li>
              <li className="flex items-center gap-3 text-sm text-white/90">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/10">
                  <Lock className="h-4 w-4" aria-hidden="true" />
                </span>
                Senha nova, só sua, a partir de agora
              </li>
            </ul>
          </div>
          {/* Mesmo ajuste do WorkspaceLogin: espaçador flexível + margem mínima garantida no
              rodapé, em vez de `justify-between` (zerava o respiro quando a lista de destaques
              cresceu). Ambos somem no mobile junto com a lista de destaques. */}
          <div className="hidden flex-1 md:block" />
          <p className="mt-6 hidden text-xs text-white/60 md:mt-8 md:block">UNI Internet · Ecossistema operacional</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-6 p-8 sm:p-10 md:p-12" noValidate>
          {/* Título/subtítulo só a partir de `md`: no mobile o painel azul logo acima já mostra
              logo, selo e título - repetir aqui embaixo seria duplicação visual. */}
          <div className="hidden md:block">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-950">Vamos confirmar seus dados</h1>
            <p className="mt-2 text-sm text-slate-500">Isso leva menos de um minuto e só aparece uma vez.</p>
          </div>

          {loadingStatus ? (
            <div className="flex items-center gap-3 rounded-xl border bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Carregando seus dados
            </div>
          ) : loadError ? (
            <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{loadError}</p>
          ) : (
            <div className="grid gap-5">
              <div className="grid gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Identificação</p>
                <div className="grid gap-1.5">
                  <Label htmlFor={cpfId}>
                    {status?.has_cpf ? `Confirme seu CPF${status.cpf_masked ? ` (cadastrado como ${status.cpf_masked})` : ""}` : "Cadastre seu CPF"}
                  </Label>
                  <div className="relative">
                    <IdCard className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                    <Input
                      id={cpfId}
                      className="pl-9 focus-visible:ring-[#2d5fff]"
                      inputMode="numeric"
                      placeholder="000.000.000-00"
                      value={cpf}
                      onChange={(event) => setCpf(formatCpf(event.target.value))}
                      autoFocus
                    />
                  </div>
                  {fieldErrors.cpf ? (
                    <p className="text-xs text-rose-600">{fieldErrors.cpf}</p>
                  ) : (
                    <p className="text-xs text-slate-400">
                      {status?.has_cpf
                        ? "É só uma confirmação de identidade - o CPF já cadastrado não muda."
                        : "Usado só para confirmar quem é você. Depois disso, nunca aparece completo em nenhuma tela."}
                    </p>
                  )}
                </div>
              </div>

              <div className="grid gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Contato</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-1.5">
                    <Label htmlFor={phoneId}>Telefone</Label>
                    <div className="relative">
                      <Phone className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                      <Input
                        id={phoneId}
                        className="pl-9 focus-visible:ring-[#2d5fff]"
                        inputMode="tel"
                        placeholder="(00) 00000-0000"
                        value={phone}
                        onChange={(event) => setPhone(formatPhone(event.target.value))}
                      />
                    </div>
                    {fieldErrors.phone ? <p className="text-xs text-rose-600">{fieldErrors.phone}</p> : null}
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor={emailId}>E-mail de contato</Label>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                      <Input
                        id={emailId}
                        className="pl-9 focus-visible:ring-[#2d5fff]"
                        type="email"
                        placeholder="voce@exemplo.com"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                      />
                    </div>
                    {fieldErrors.email ? <p className="text-xs text-rose-600">{fieldErrors.email}</p> : null}
                  </div>
                </div>
              </div>

              <div className="grid gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Nova senha</p>
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
                {submitting ? "Confirmando..." : "Confirmar e entrar no portal"}
              </Button>
            </div>
          )}
        </form>
      </div>
      <StatusToast error={submitError} onDismissError={() => setSubmitError(null)} />
    </main>
  );
}
