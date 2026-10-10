export type RecoveryStep = "email" | "code" | "password" | "success";

/** Verification is optional for backends that validate the code when saving the new password. */
export interface PasswordRecoveryApi {
  requestCode(email: string): Promise<{ retryAfterSeconds?: number } | void>;
  verifyCode?(
    email: string,
    code: string,
  ): Promise<{ resetToken?: string } | void>;
  resetPassword(input: {
    email: string;
    code: string;
    resetToken?: string;
    newPassword: string;
    confirmPassword: string;
  }): Promise<unknown>;
}

export type RecoveryState = {
  step: RecoveryStep;
  email: string;
  busy: boolean;
  error: string | null;
  notice: string | null;
  resendAt: number;
  codeVerified: boolean;
};

export class RecoveryCodeError extends Error {}

export function normalizeRecoveryCode(value: string) {
  return value.replace(/\D/g, "").slice(0, 6);
}

export function validateRecoveryPassword(
  password: string,
  confirmation: string,
) {
  if (password.length < 8)
    return "A nova senha precisa ter pelo menos 8 caracteres.";
  if (password.length > 128)
    return "A nova senha deve ter no máximo 128 caracteres.";
  if (password !== confirmation)
    return "As senhas não coincidem. Confira a confirmação.";
  return null;
}

/** Shared state machine for React and the portable HTML. Sensitive values stay in memory. */
export class PasswordRecoveryController {
  private state: RecoveryState;
  private listeners = new Set<() => void>();
  private generation = 0;
  private verifiedCode = "";
  private resetToken: string | undefined;
  private disposed = false;

  constructor(
    private api?: PasswordRecoveryApi,
    email = "",
    private now = () => Date.now(),
  ) {
    this.state = {
      step: "email",
      email,
      busy: false,
      error: null,
      notice: null,
      resendAt: 0,
      codeVerified: false,
    };
  }

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(patch: Partial<RecoveryState>) {
    if (this.disposed) return;
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  remainingSeconds = () =>
    Math.max(0, Math.ceil((this.state.resendAt - this.now()) / 1000));
  supportsCodeVerification = () => Boolean(this.api?.verifyCode);
  private resendAt(result: { retryAfterSeconds?: number } | void) {
    const seconds = result?.retryAfterSeconds;
    return (
      this.now() +
      (typeof seconds === "number" && Number.isFinite(seconds)
        ? Math.max(0, Math.min(seconds, 86400))
        : 60) *
        1000
    );
  }

  private async run(
    operation: (
      api: PasswordRecoveryApi,
      isCurrent: () => boolean,
    ) => Promise<void>,
  ) {
    if (this.state.busy || this.disposed) return false;
    if (!this.api) {
      this.update({
        error:
          "Não foi possível iniciar a recuperação. Tente novamente mais tarde.",
      });
      return false;
    }
    const generation = ++this.generation;
    this.update({ busy: true, error: null, notice: null });
    try {
      await operation(
        this.api,
        () => generation === this.generation && !this.disposed,
      );
      return generation === this.generation && !this.disposed;
    } catch (error) {
      if (generation === this.generation) {
        if (error instanceof RecoveryCodeError) {
          this.verifiedCode = "";
          this.resetToken = undefined;
          this.update({ step: "code", codeVerified: false });
        }
        this.update({
          error:
            error instanceof Error
              ? error.message
              : "Não foi possível continuar. Tente novamente.",
        });
      }
      return false;
    } finally {
      if (generation === this.generation) this.update({ busy: false });
    }
  }

  requestCode = async (email: string) => {
    if (this.state.step !== "email" || this.state.busy || this.disposed)
      return false;
    const normalized = email.trim();
    if (
      normalized.length > 180 ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)
    ) {
      this.update({ error: "Informe um e-mail válido para receber o código." });
      return false;
    }
    return this.run(async (api, isCurrent) => {
      const result = await api.requestCode(normalized);
      if (!isCurrent()) return;
      this.verifiedCode = "";
      this.resetToken = undefined;
      this.update({
        step: "code",
        email: normalized,
        resendAt: this.resendAt(result),
        codeVerified: false,
      });
    });
  };

  resendCode = async () => {
    if (this.state.step !== "code" || this.remainingSeconds() > 0) return false;
    return this.run(async (api, isCurrent) => {
      const result = await api.requestCode(this.state.email);
      if (!isCurrent()) return;
      this.update({
        resendAt: this.resendAt(result),
        notice: "Novo código solicitado. Use o código do e-mail mais recente.",
      });
    });
  };

  verifyCode = async (code: string) => {
    if (this.state.step !== "code" || this.state.busy || this.disposed)
      return false;
    if (!/^\d{6}$/.test(code)) {
      this.update({ error: "Digite os 6 dígitos do código recebido." });
      return false;
    }
    if (this.api && !this.api.verifyCode) {
      this.verifiedCode = code;
      this.update({
        step: "password",
        codeVerified: false,
        error: null,
        notice: null,
      });
      return true;
    }
    return this.run(async (api, isCurrent) => {
      const result = await api.verifyCode!(this.state.email, code);
      if (!isCurrent()) return;
      this.verifiedCode = code;
      this.resetToken = result?.resetToken;
      this.update({ step: "password", codeVerified: true });
    });
  };

  resetPassword = async (password: string, confirmation: string) => {
    if (
      this.state.step !== "password" ||
      !this.verifiedCode ||
      this.state.busy ||
      this.disposed
    )
      return false;
    const error = validateRecoveryPassword(password, confirmation);
    if (error) {
      this.update({ error });
      return false;
    }
    return this.run(async (api, isCurrent) => {
      await api.resetPassword({
        email: this.state.email,
        code: this.verifiedCode,
        resetToken: this.resetToken,
        newPassword: password,
        confirmPassword: confirmation,
      });
      if (!isCurrent()) return;
      this.verifiedCode = "";
      this.resetToken = undefined;
      this.update({ step: "success", codeVerified: true });
    });
  };

  changeEmail = () => {
    if (this.state.busy) return;
    this.verifiedCode = "";
    this.resetToken = undefined;
    this.update({
      step: "email",
      error: null,
      notice: null,
      codeVerified: false,
    });
  };

  dispose = () => {
    this.disposed = true;
    this.generation++;
    this.verifiedCode = "";
    this.resetToken = undefined;
    this.listeners.clear();
  };
  activate = () => {
    this.disposed = false;
    this.update({ busy: false });
  };
}
