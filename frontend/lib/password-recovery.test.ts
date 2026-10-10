import { describe, expect, it, vi } from "vitest";
import {
  normalizeRecoveryCode,
  PasswordRecoveryController,
  RecoveryCodeError,
  type PasswordRecoveryApi,
} from "./password-recovery";

function backend() {
  return {
    requestCode: vi.fn(async () => ({ retryAfterSeconds: 60 })),
    verifyCode: vi.fn(async () => ({ resetToken: "server-reset-token" })),
    resetPassword: vi.fn(async () => undefined),
  } satisfies PasswordRecoveryApi;
}

describe("password recovery flow", () => {
  it("preserves leading zeros and normalizes a pasted six-digit code", () => {
    expect(normalizeRecoveryCode("00 12-34")).toBe("001234");
    expect(normalizeRecoveryCode("ABC123456789")).toBe("123456");
  });
  it("does not verify or reset before the previous steps succeed", async () => {
    const api = backend();
    const flow = new PasswordRecoveryController(api);
    expect(await flow.verifyCode("001234")).toBe(false);
    expect(await flow.resetPassword("password123", "password123")).toBe(false);
    expect(api.verifyCode).not.toHaveBeenCalled();
    expect(api.resetPassword).not.toHaveBeenCalled();
    expect(await flow.requestCode("invalid")).toBe(false);
    expect(api.requestCode).not.toHaveBeenCalled();
  });
  it("blocks duplicate requests and respects the server resend interval", async () => {
    let now = 1000;
    const api = backend();
    const flow = new PasswordRecoveryController(api, "", () => now);
    const first = flow.requestCode(" person@example.com ");
    expect(await flow.requestCode("person@example.com")).toBe(false);
    await first;
    expect(api.requestCode).toHaveBeenCalledTimes(1);
    expect(flow.remainingSeconds()).toBe(60);
    expect(await flow.resendCode()).toBe(false);
    now += 60_000;
    expect(await flow.resendCode()).toBe(true);
    expect(api.requestCode).toHaveBeenCalledTimes(2);
    expect(flow.remainingSeconds()).toBe(60);
  });
  it("keeps invalid or expired codes on the verification step", async () => {
    const api = backend();
    api.verifyCode.mockRejectedValueOnce(new Error("Código expirado."));
    const flow = new PasswordRecoveryController(api);
    await flow.requestCode("person@example.com");
    expect(await flow.verifyCode("12345")).toBe(false);
    expect(api.verifyCode).not.toHaveBeenCalled();
    expect(await flow.verifyCode("001234")).toBe(false);
    expect(flow.getSnapshot().step).toBe("code");
    expect(flow.getSnapshot().error).toBe("Código expirado.");
    expect(flow.getSnapshot().busy).toBe(false);
  });
  it("requires matching passwords and confirms success only after a successful save", async () => {
    const api = backend();
    const flow = new PasswordRecoveryController(api);
    await flow.requestCode("person@example.com");
    await flow.verifyCode("001234");
    expect(await flow.resetPassword("short", "short")).toBe(false);
    expect(await flow.resetPassword("password123", "different123")).toBe(false);
    expect(api.resetPassword).not.toHaveBeenCalled();
    api.resetPassword.mockRejectedValueOnce(new Error("Tente novamente."));
    expect(await flow.resetPassword("password123", "password123")).toBe(false);
    expect(flow.getSnapshot().step).toBe("password");
    expect(await flow.resetPassword("password123", "password123")).toBe(true);
    expect(api.resetPassword).toHaveBeenLastCalledWith({
      email: "person@example.com",
      code: "001234",
      resetToken: "server-reset-token",
      newPassword: "password123",
      confirmPassword: "password123",
    });
    expect(flow.getSnapshot().step).toBe("success");
  });
  it("ignores responses from a closed dialog even if its controller is reactivated", async () => {
    let resolveRequest!: (result: { retryAfterSeconds: number }) => void;
    const api = backend();
    api.requestCode.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const flow = new PasswordRecoveryController(api);
    const pending = flow.requestCode("person@example.com");
    flow.dispose();
    flow.activate();
    resolveRequest({ retryAfterSeconds: 60 });
    expect(await pending).toBe(false);
    expect(flow.getSnapshot().step).toBe("email");
    expect(flow.getSnapshot().busy).toBe(false);
  });
  it("never fakes a successful send when no backend adapter is configured", async () => {
    const flow = new PasswordRecoveryController();
    expect(await flow.requestCode("person@example.com")).toBe(false);
    expect(flow.getSnapshot().step).toBe("email");
    expect(flow.getSnapshot().error).toBeTruthy();
  });
  it("defers code verification to the save endpoint when the backend provides only two routes", async () => {
    const api = backend();
    const flow = new PasswordRecoveryController({
      requestCode: api.requestCode,
      resetPassword: api.resetPassword,
    });
    await flow.requestCode("person@example.com");
    expect(flow.supportsCodeVerification()).toBe(false);
    expect(await flow.verifyCode("001234")).toBe(true);
    expect(flow.getSnapshot().codeVerified).toBe(false);
    expect(flow.getSnapshot().step).toBe("password");
    expect(api.verifyCode).not.toHaveBeenCalled();
    api.resetPassword.mockRejectedValueOnce(
      new RecoveryCodeError("Código inválido ou expirado."),
    );
    expect(await flow.resetPassword("password123", "password123")).toBe(false);
    expect(flow.getSnapshot().step).toBe("code");
    expect(flow.getSnapshot().codeVerified).toBe(false);
    expect(await flow.verifyCode("000111")).toBe(true);
    expect(await flow.resetPassword("password123", "password123")).toBe(true);
    expect(flow.getSnapshot().step).toBe("success");
    expect(flow.getSnapshot().codeVerified).toBe(true);
  });
});
