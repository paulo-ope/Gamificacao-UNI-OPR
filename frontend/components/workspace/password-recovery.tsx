"use client";

import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";
import {
  FormEvent,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import {
  normalizeRecoveryCode,
  PasswordRecoveryApi,
  PasswordRecoveryController,
  RecoveryState,
  RecoveryStep,
} from "@/lib/password-recovery";

const STEP_COPY = {
  email: {
    title: "Recuperar senha",
    description:
      "Informe seu e-mail corporativo para receber um código seguro de recuperação.",
  },
  code: {
    title: "Código de verificação",
    description:
      "Digite os 6 dígitos do e-mail mais recente para confirmar seu acesso.",
  },
  password: {
    title: "Definir nova senha",
    description: "Crie uma nova senha para recuperar seu acesso ao Workspace.",
  },
  success: {
    title: "Senha atualizada",
    description:
      "Tudo pronto. Você já pode entrar no Workspace com a sua nova senha.",
  },
};

type ViewProps = {
  step?: RecoveryStep;
  email?: string;
  busy?: boolean;
  error?: string | null;
  notice?: string | null;
  resendSeconds?: number;
  inDialog?: boolean;
  demo?: boolean;
  codeVerified?: boolean;
  canVerifyCode?: boolean;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onResend?: () => void;
  onChangeEmail?: () => void;
  onClose?: () => void;
};

/** Rendered by React and into the four HTML templates by the model generator. */
export function PasswordRecoveryView({
  step = "email",
  email = "",
  busy = false,
  error,
  notice,
  resendSeconds = 0,
  inDialog = false,
  demo = false,
  codeVerified = true,
  canVerifyCode = true,
  onSubmit,
  onResend,
  onChangeEmail,
  onClose,
}: ViewProps) {
  const [code, setCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const copy = STEP_COPY[step];
  const current =
    step === "success" ? 3 : ["email", "code", "password"].indexOf(step);
  return (
    <>
      <div className="uni-recovery-heading">
        <span className="uni-access-recovery-icon">
          <KeyRound size={23} aria-hidden="true" />
        </span>
        <div>
          <p className="uni-access-kicker">SEGURANÇA DE ACESSO</p>
          {inDialog ? (
            <Dialog.Title asChild>
              <h2>{copy.title}</h2>
            </Dialog.Title>
          ) : (
            <h2 id="uni-recovery-title">{copy.title}</h2>
          )}
          {inDialog ? (
            <Dialog.Description className="uni-access-recovery-description">
              {copy.description}
            </Dialog.Description>
          ) : (
            <p
              id="uni-recovery-description"
              className="uni-access-recovery-description"
            >
              {copy.description}
            </p>
          )}
        </div>
      </div>
      <ol
        className="uni-recovery-progress"
        aria-label="Etapas da recuperação de senha"
      >
        {[
          { icon: Mail, label: "E-mail", detail: "Identificação" },
          { icon: ShieldCheck, label: "Código", detail: "Validação" },
          { icon: LockKeyhole, label: "Senha", detail: "Redefinição" },
        ].map(({ icon: Icon, label, detail }, index) => (
          <li
            key={label}
            className={
              index === 1 && step === "password" && !codeVerified
                ? "is-pending"
                : index < current
                  ? "is-complete"
                  : index === current
                    ? "is-current"
                    : ""
            }
            aria-current={index === current ? "step" : undefined}
          >
            <span className="uni-recovery-step-icon">
              {index < current &&
              !(index === 1 && step === "password" && !codeVerified) ? (
                <CheckCircle2 size={19} aria-hidden="true" />
              ) : (
                <Icon size={19} aria-hidden="true" />
              )}
            </span>
            <strong>{label}</strong>
            <small>
              {index === 1 && step === "password" && !codeVerified
                ? "Ao salvar"
                : detail}
            </small>
            {index < current &&
            !(index === 1 && step === "password" && !codeVerified) ? (
              <span className="uni-recovery-sr-only">Concluída</span>
            ) : null}
          </li>
        ))}
      </ol>

      {demo ? (
        <p className="uni-recovery-demo" role="note">
          Prévia interativa: nenhum e-mail é enviado e nenhuma conta é alterada.
          Código de teste: <strong>123456</strong>.
        </p>
      ) : null}
      {step === "code" ? (
        <div className="uni-recovery-email-note">
          Confira o e-mail <strong data-recovery-email>{email}</strong>. Para
          continuar, use o código mais recente recebido.
        </div>
      ) : null}
      {step === "success" ? (
        <div className="uni-recovery-success">
          <span>
            <Check size={27} aria-hidden="true" />
          </span>
          <p>
            {demo
              ? "As três etapas foram demonstradas. No projeto integrado, a confirmação aparece após o backend salvar a nova senha."
              : "Sua nova senha foi salva. Use-a no próximo acesso."}
          </p>
          <button
            type="button"
            className="uni-access-primary"
            data-recovery-finish
            id="uni-recovery-finish"
            onClick={onClose}
          >
            Voltar para o login
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <form
          className="uni-recovery-form"
          method="post"
          onSubmit={onSubmit}
          aria-busy={busy}
        >
          {step === "email" ? (
            <div className="uni-access-field">
              <label htmlFor="uni-recovery-email">E-mail corporativo</label>
              <div className="uni-access-input-wrap">
                <Mail size={17} aria-hidden="true" />
                <input
                  id="uni-recovery-email"
                  name="recoveryEmail"
                  type="email"
                  defaultValue={email}
                  placeholder="nome@souuni.com"
                  required
                  maxLength={180}
                  autoComplete="email"
                  disabled={busy}
                  aria-describedby={error ? "uni-recovery-error" : undefined}
                />
              </div>
            </div>
          ) : null}
          {step === "code" ? (
            <>
              <div className="uni-access-field">
                <label htmlFor="uni-recovery-code">Código recebido</label>
                <input
                  id="uni-recovery-code"
                  className="uni-recovery-code"
                  name="recoveryCode"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(event) =>
                    setCode(normalizeRecoveryCode(event.target.value))
                  }
                  placeholder="000000"
                  required
                  disabled={busy}
                  aria-describedby="uni-recovery-code-hint"
                />
                <p id="uni-recovery-code-hint" className="uni-recovery-sr-only">
                  Digite ou cole o código de 6 dígitos recebido por e-mail.
                </p>
              </div>
              <div className="uni-recovery-code-actions">
                <button
                  type="button"
                  data-recovery-change-email
                  onClick={onChangeEmail}
                  disabled={busy}
                >
                  <ArrowLeft size={15} aria-hidden="true" />
                  Alterar e-mail
                </button>
                <button
                  type="button"
                  data-recovery-resend
                  onClick={onResend}
                  disabled={busy || resendSeconds > 0}
                >
                  {resendSeconds > 0
                    ? `Reenviar em ${resendSeconds}s`
                    : "Reenviar código"}
                </button>
              </div>
            </>
          ) : null}
          {step === "password" ? (
            <>
              {[
                {
                  name: "newPassword",
                  id: "uni-recovery-new-password",
                  label: "Nova senha",
                  placeholder: "Digite a nova senha",
                },
                {
                  name: "confirmPassword",
                  id: "uni-recovery-confirm-password",
                  label: "Confirmar nova senha",
                  placeholder: "Repita a nova senha",
                },
              ].map((field) => (
                <div className="uni-access-field" key={field.name}>
                  <label htmlFor={field.id}>{field.label}</label>
                  <div className="uni-access-input-wrap">
                    <input
                      id={field.id}
                      name={field.name}
                      type={showPassword ? "text" : "password"}
                      placeholder={field.placeholder}
                      required
                      minLength={8}
                      maxLength={128}
                      autoComplete="new-password"
                      disabled={busy}
                      aria-describedby="uni-recovery-password-hint"
                    />
                    <button
                      type="button"
                      className="uni-access-password-toggle"
                      data-recovery-password-toggle
                      aria-label={
                        showPassword ? "Ocultar senhas" : "Mostrar senhas"
                      }
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword((visible) => !visible)}
                    >
                      {showPassword ? (
                        <EyeOff size={17} aria-hidden="true" />
                      ) : (
                        <Eye size={17} aria-hidden="true" />
                      )}
                    </button>
                  </div>
                </div>
              ))}
              <p
                id="uni-recovery-password-hint"
                className="uni-recovery-password-hint"
              >
                Use pelo menos 8 caracteres. Prefira uma senha exclusiva, que
                você ainda não utiliza em outros acessos.
                {!codeVerified
                  ? " O código será conferido ao salvar a nova senha."
                  : ""}
              </p>
            </>
          ) : null}
          <p
            id="uni-recovery-error"
            className="uni-access-error"
            role="alert"
            hidden={!error}
          >
            {error}
          </p>
          <p className="uni-recovery-notice" role="status" hidden={!notice}>
            {notice}
          </p>
          <button
            type="submit"
            className="uni-access-primary"
            disabled={busy || (step === "code" && code.length !== 6)}
          >
            <span>
              {busy
                ? step === "email"
                  ? "Enviando código..."
                  : step === "code"
                    ? "Validando código..."
                    : "Salvando nova senha..."
                : step === "email"
                  ? "Enviar código de recuperação"
                  : step === "code"
                    ? canVerifyCode
                      ? "Validar código"
                      : "Continuar"
                    : "Salvar nova senha"}
            </span>
            {busy ? (
              <Loader2
                size={17}
                className="uni-access-spinner"
                aria-hidden="true"
              />
            ) : null}
          </button>
        </form>
      )}
    </>
  );
}

export function WorkspacePasswordRecovery({
  api,
  initialEmail = "",
  onClose,
  onRecovered,
}: {
  api?: PasswordRecoveryApi;
  initialEmail?: string;
  onClose: () => void;
  onRecovered?: (email: string) => void;
}) {
  const controller = useMemo(
    () => new PasswordRecoveryController(api, initialEmail),
    [api, initialEmail],
  );
  const state: RecoveryState = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    controller.activate();
    return () => controller.dispose();
  }, [controller]);
  useEffect(() => {
    const update = () => setRemaining(controller.remainingSeconds());
    update();
    if (state.step !== "code") return;
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [controller, state.step, state.resendAt]);
  useEffect(() => {
    const id =
      state.step === "email"
        ? "uni-recovery-email"
        : state.step === "code"
          ? "uni-recovery-code"
          : state.step === "password"
            ? "uni-recovery-new-password"
            : "uni-recovery-finish";
    if (id) document.getElementById(id)?.focus();
  }, [state.step, state.resendAt, state.busy]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // React portal events still bubble through the login form's component tree.
    event.stopPropagation();
    const values = new FormData(event.currentTarget);
    if (state.step === "email")
      await controller.requestCode(String(values.get("recoveryEmail") ?? ""));
    if (state.step === "code")
      await controller.verifyCode(String(values.get("recoveryCode") ?? ""));
    if (state.step === "password")
      await controller.resetPassword(
        String(values.get("newPassword") ?? ""),
        String(values.get("confirmPassword") ?? ""),
      );
  }
  return (
    <PasswordRecoveryView
      key={state.step === "code" ? `code-${state.resendAt}` : state.step}
      {...state}
      inDialog
      resendSeconds={remaining}
      canVerifyCode={controller.supportsCodeVerification()}
      onSubmit={submit}
      onResend={controller.resendCode}
      onChangeEmail={controller.changeEmail}
      onClose={() => {
        if (state.step === "success") onRecovered?.(state.email);
        onClose();
      }}
    />
  );
}
