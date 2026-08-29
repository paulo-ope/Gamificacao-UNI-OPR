"use client";

import { ArrowLeft, CheckCircle2, IdCard, KeyRound, Loader2, Mail, Phone, ShieldCheck, User as UserIcon } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusToast } from "@/components/ui/status-toast";
import { api } from "@/lib/api";
import { formatCpf, formatPhone, isValidCpf, onlyDigits } from "@/lib/masks";

// Fase 2D - autoatendimento por CPF (pedido do usuário em 2026-08-29): digita o CPF, confirma o
// próprio nome (sempre do IXC, revalidado no servidor no envio - nunca o que o cliente mandaria,
// é a confirmação de identidade) e confirma o próprio telefone. O telefone é diferente: se a
// pessoa não reconhecer o número que veio do IXC (cadastro desatualizado), ela pode digitar o
// número certo - é ESSE que fica salvo, com prioridade sobre o do IXC (pedido explícito do
// usuário em 2026-08-29). Só então informa o e-mail (sempre digitado, nunca herdado do IXC,
// restrito ao domínio corporativo). Se o CPF não for encontrado no IXC (cadastro ainda não
// sincronizado), cai no formulário manual original, pra não perder essa capacidade.
type Step = "cpf" | "confirm_identity" | "confirm_phone" | "correct_phone" | "email" | "manual" | "done";

const CORPORATE_EMAIL_SUFFIX = "@souuni.com";

export function AccessRequestForm() {
  const [step, setStep] = useState<Step>("cpf");
  const [cpf, setCpf] = useState("");
  const [foundName, setFoundName] = useState("");
  const [foundPhoneMasked, setFoundPhoneMasked] = useState<string | null>(null);
  const [correctedPhone, setCorrectedPhone] = useState("");
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualPhone, setManualPhone] = useState("");

  const [cpfError, setCpfError] = useState<string | null>(null);
  const [correctedPhoneError, setCorrectedPhoneError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [manualErrors, setManualErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const cpfId = useId();
  const correctedPhoneId = useId();
  const emailId = useId();
  const newPasswordId = useId();
  const confirmPasswordId = useId();
  const manualNameId = useId();
  const manualPhoneId = useId();

  function restart() {
    setStep("cpf");
    setCpf("");
    setFoundName("");
    setFoundPhoneMasked(null);
    setCorrectedPhone("");
    setEmail("");
    setNewPassword("");
    setConfirmPassword("");
    setManualName("");
    setManualPhone("");
    setCpfError(null);
    setCorrectedPhoneError(null);
    setEmailError(null);
    setPasswordError(null);
    setManualErrors({});
    setSubmitError(null);
  }

  function validatePassword(): string | null {
    if (newPassword.length < 8) return "A senha precisa ter pelo menos 8 caracteres.";
    if (newPassword !== confirmPassword) return "A senha e a confirmação não são iguais.";
    return null;
  }

  function handleConfirmCorrectedPhone() {
    setCorrectedPhoneError(null);
    if (onlyDigits(correctedPhone).length < 10) {
      setCorrectedPhoneError("Informe um telefone válido, com DDD.");
      return;
    }
    setStep("email");
  }

  async function handleSearch() {
    setCpfError(null);
    if (!isValidCpf(cpf)) {
      setCpfError("CPF inválido. Confira os números.");
      return;
    }
    setSearching(true);
    try {
      const found = await api.lookupAccessRequestCpf(onlyDigits(cpf));
      setFoundName(found.name);
      setFoundPhoneMasked(found.phone_masked);
      setStep("confirm_identity");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Não foi possível consultar seu cadastro.";
      // `request()` (lib/api.ts) só devolve a mensagem, sem o status HTTP - "não encontrado" cai
      // no formulário manual; qualquer outro erro (rede, IXC fora do ar) fica na própria etapa.
      if (message.toLowerCase().includes("nenhum funcionário encontrado")) {
        setStep("manual");
      } else {
        setCpfError(message);
      }
    } finally {
      setSearching(false);
    }
  }

  async function handleSubmitFound() {
    setEmailError(null);
    setPasswordError(null);
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail.endsWith(CORPORATE_EMAIL_SUFFIX)) {
      setEmailError(`Use seu e-mail corporativo, terminado em ${CORPORATE_EMAIL_SUFFIX}.`);
      return;
    }
    const passwordProblem = validatePassword();
    if (passwordProblem) {
      setPasswordError(passwordProblem);
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      // `phone` só vai preenchido quando a pessoa corrigiu o número (ver `correct_phone`) - nesse
      // caso ele tem prioridade sobre o do IXC no servidor (pedido explícito do usuário). Quando
      // ela só confirmou o número que já veio do IXC, não manda nada - o servidor usa o do IXC.
      await api.submitAccessRequest({
        cpf: onlyDigits(cpf),
        email: normalizedEmail,
        new_password: newPassword,
        confirm_password: confirmPassword,
        phone: correctedPhone ? formatPhone(correctedPhone) : undefined,
      });
      setStep("done");
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Não foi possível enviar sua solicitação.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitManual(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors: Record<string, string> = {};
    const normalizedEmail = email.trim().toLowerCase();
    if (!manualName.trim()) errors.name = "Informe seu nome completo.";
    if (onlyDigits(manualPhone).length < 10) errors.phone = "Informe um telefone válido, com DDD.";
    if (!normalizedEmail.endsWith(CORPORATE_EMAIL_SUFFIX)) errors.email = `Use seu e-mail corporativo, terminado em ${CORPORATE_EMAIL_SUFFIX}.`;
    const passwordProblem = validatePassword();
    if (passwordProblem) errors.password = passwordProblem;
    setManualErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.submitAccessRequest({
        cpf: onlyDigits(cpf),
        email: normalizedEmail,
        new_password: newPassword,
        confirm_password: confirmPassword,
        name: manualName.trim(),
        phone: formatPhone(manualPhone),
      });
      setStep("done");
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Não foi possível enviar sua solicitação.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-blue-950/10 md:grid-cols-[1fr_1.1fr]">
        <div className="uni-gradient relative flex flex-col overflow-hidden p-6 text-white sm:p-8 md:p-10">
          <img src="/brand/uni-logo-white.png" alt="" className="h-8 w-auto self-start object-contain drop-shadow-sm md:h-9" />
          <div className="mt-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-white/85">
              <UserIcon className="h-3.5 w-3.5" aria-hidden="true" />
              Solicitar acesso
            </span>
            <h2 className="mt-4 text-2xl font-semibold leading-[1.15] tracking-tight md:mt-5 md:text-3xl">Ainda não tem acesso ao Portal?</h2>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/80 md:mt-3">
              Confirme seu CPF, nome e telefone e já defina sua senha. Um administrador confirma seu vínculo - depois disso, é só entrar.
            </p>
          </div>
          <div className="hidden flex-1 md:block" />
          <p className="mt-6 hidden text-xs text-white/60 md:mt-8 md:block">UNI Internet · Ecossistema operacional</p>
        </div>

        <div className="flex flex-col gap-6 p-8 sm:p-10 md:p-12">
          <div className="hidden md:block">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-950">Ainda não tem acesso ao Portal?</h1>
            <p className="mt-2 text-sm text-slate-500">Leva menos de um minuto.</p>
          </div>

          {step !== "cpf" && step !== "done" ? (
            <button type="button" onClick={restart} className="flex w-fit items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-slate-600">
              <ArrowLeft className="h-3.5 w-3.5" /> Trocar CPF
            </button>
          ) : null}

          {step === "cpf" ? (
            <div className="grid gap-5">
              <div className="grid gap-1.5">
                <Label htmlFor={cpfId}>CPF</Label>
                <div className="relative">
                  <IdCard className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={cpfId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    inputMode="numeric"
                    placeholder="000.000.000-00"
                    value={cpf}
                    onChange={(event) => setCpf(formatCpf(event.target.value))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        handleSearch();
                      }
                    }}
                    autoFocus
                  />
                </div>
                {cpfError ? (
                  <p className="text-xs text-rose-600">{cpfError}</p>
                ) : (
                  <p className="text-xs text-slate-400">Usado só para confirmar quem você é e localizar seu cadastro.</p>
                )}
              </div>
              <Button type="button" disabled={searching || !cpf.trim()} className="w-full rounded-xl" onClick={handleSearch}>
                {searching ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                {searching ? "Consultando..." : "Continuar"}
              </Button>
            </div>
          ) : null}

          {step === "confirm_identity" ? (
            <div className="grid gap-5">
              <div className="rounded-xl border border-[#2d5fff]/20 bg-[#2d5fff]/5 p-5 text-center">
                <UserIcon className="mx-auto h-6 w-6 text-[#0028f3]" aria-hidden="true" />
                <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">É você?</p>
                <p className="mt-1 text-lg font-semibold text-slate-950">{foundName}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="outline" className="rounded-xl" onClick={restart}>
                  Não sou eu
                </Button>
                <Button type="button" className="rounded-xl" onClick={() => setStep("confirm_phone")}>
                  Sim, sou eu
                </Button>
              </div>
            </div>
          ) : null}

          {step === "confirm_phone" ? (
            <div className="grid gap-5">
              <div className="rounded-xl border border-[#2d5fff]/20 bg-[#2d5fff]/5 p-5 text-center">
                <Phone className="mx-auto h-6 w-6 text-[#0028f3]" aria-hidden="true" />
                <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Este é o seu telefone?</p>
                <p className="mt-1 text-lg font-semibold text-slate-950">{foundPhoneMasked || "Não cadastrado"}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Button type="button" variant="outline" className="rounded-xl" onClick={() => setStep("correct_phone")}>
                  Não é o meu
                </Button>
                <Button type="button" className="rounded-xl" onClick={() => setStep("email")}>
                  Sim, é o meu
                </Button>
              </div>
              <p className="text-center text-xs text-slate-400">Se o número não for seu, você pode atualizar na próxima etapa.</p>
            </div>
          ) : null}

          {step === "correct_phone" ? (
            <div className="grid gap-5">
              <div className="grid gap-1.5">
                <Label htmlFor={correctedPhoneId}>Qual é o seu telefone atual?</Label>
                <div className="relative">
                  <Phone className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={correctedPhoneId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    inputMode="tel"
                    placeholder="(00) 00000-0000"
                    value={correctedPhone}
                    onChange={(event) => setCorrectedPhone(formatPhone(event.target.value))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        handleConfirmCorrectedPhone();
                      }
                    }}
                    autoFocus
                  />
                </div>
                {correctedPhoneError ? (
                  <p className="text-xs text-rose-600">{correctedPhoneError}</p>
                ) : (
                  <p className="text-xs text-slate-400">Este número atualiza o que fica salvo no seu cadastro.</p>
                )}
              </div>
              <Button type="button" disabled={!correctedPhone.trim()} className="w-full rounded-xl" onClick={handleConfirmCorrectedPhone}>
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                Continuar
              </Button>
            </div>
          ) : null}

          {step === "email" ? (
            <div className="grid gap-5">
              <div className="grid gap-1.5">
                <Label htmlFor={emailId}>Seu e-mail corporativo</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={emailId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    type="email"
                    placeholder={`voce${CORPORATE_EMAIL_SUFFIX}`}
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    autoFocus
                  />
                </div>
                {emailError ? (
                  <p className="text-xs text-rose-600">{emailError}</p>
                ) : (
                  <p className="text-xs text-slate-400">Só aceitamos e-mail terminado em {CORPORATE_EMAIL_SUFFIX}.</p>
                )}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={newPasswordId}>Crie uma senha</Label>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={newPasswordId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    type="password"
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={confirmPasswordId}>Confirme a senha</Label>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={confirmPasswordId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </div>
                {passwordError ? (
                  <p className="text-xs text-rose-600">{passwordError}</p>
                ) : (
                  <p className="text-xs text-slate-400">Pelo menos 8 caracteres. É a senha que você vai usar para entrar no Portal, assim que for aprovado.</p>
                )}
              </div>
              <Button type="button" disabled={submitting || !email.trim() || !newPassword || !confirmPassword} className="w-full rounded-xl" onClick={handleSubmitFound}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                {submitting ? "Enviando..." : "Enviar solicitação"}
              </Button>
            </div>
          ) : null}

          {step === "manual" ? (
            <form onSubmit={handleSubmitManual} className="grid gap-5" noValidate>
              <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                Não encontramos seu CPF no nosso cadastro ainda - preencha seus dados manualmente.
              </p>
              <div className="grid gap-1.5">
                <Label htmlFor={manualNameId}>Nome completo</Label>
                <div className="relative">
                  <UserIcon className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input id={manualNameId} className="pl-9 focus-visible:ring-[#2d5fff]" value={manualName} onChange={(event) => setManualName(event.target.value)} autoFocus />
                </div>
                {manualErrors.name ? <p className="text-xs text-rose-600">{manualErrors.name}</p> : null}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={manualPhoneId}>Telefone</Label>
                <div className="relative">
                  <Phone className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={manualPhoneId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    inputMode="tel"
                    placeholder="(00) 00000-0000"
                    value={manualPhone}
                    onChange={(event) => setManualPhone(formatPhone(event.target.value))}
                  />
                </div>
                {manualErrors.phone ? <p className="text-xs text-rose-600">{manualErrors.phone}</p> : null}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={emailId}>Seu e-mail corporativo</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={emailId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    type="email"
                    placeholder={`voce${CORPORATE_EMAIL_SUFFIX}`}
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </div>
                {manualErrors.email ? (
                  <p className="text-xs text-rose-600">{manualErrors.email}</p>
                ) : (
                  <p className="text-xs text-slate-400">Só aceitamos e-mail terminado em {CORPORATE_EMAIL_SUFFIX}.</p>
                )}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={newPasswordId}>Crie uma senha</Label>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={newPasswordId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    type="password"
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={confirmPasswordId}>Confirme a senha</Label>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
                  <Input
                    id={confirmPasswordId}
                    className="pl-9 focus-visible:ring-[#2d5fff]"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </div>
                {manualErrors.password ? (
                  <p className="text-xs text-rose-600">{manualErrors.password}</p>
                ) : (
                  <p className="text-xs text-slate-400">Pelo menos 8 caracteres. É a senha que você vai usar para entrar no Portal, assim que for aprovado.</p>
                )}
              </div>
              <Button type="submit" disabled={submitting} className="mt-1 w-full rounded-xl">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                {submitting ? "Enviando..." : "Enviar solicitação"}
              </Button>
            </form>
          ) : null}

          {step === "done" ? (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-8 text-center">
              <CheckCircle2 className="h-8 w-8 text-emerald-600" aria-hidden="true" />
              <p className="text-sm font-medium text-emerald-900">Solicitação recebida.</p>
              <p className="max-w-xs text-sm text-emerald-800">
                Um administrador vai analisar seu pedido. Assim que for aprovado, você já pode entrar no Portal com o e-mail e a senha que você cadastrou aqui.
              </p>
            </div>
          ) : null}
        </div>
      </div>
      <StatusToast error={submitError} onDismissError={() => setSubmitError(null)} />
    </main>
  );
}
