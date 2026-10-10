import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { RecoveryCodeError } from "./password-recovery";
import { workspacePasswordRecoveryApi } from "./workspace-password-recovery-api";

vi.mock("./api", () => ({
  api: { forgotPassword: vi.fn(), resetPassword: vi.fn() },
}));

describe("Workspace recovery backend adapter", () => {
  beforeEach(() => vi.resetAllMocks());
  it("uses the verified send endpoint and does not invent a verification endpoint", async () => {
    vi.mocked(api.forgotPassword).mockResolvedValue({
      received: true,
      message: "Solicitação recebida.",
    });
    await expect(
      workspacePasswordRecoveryApi.requestCode("person@example.com"),
    ).resolves.toEqual({ retryAfterSeconds: 60 });
    expect(api.forgotPassword).toHaveBeenCalledWith("person@example.com");
    expect(workspacePasswordRecoveryApi.verifyCode).toBeUndefined();
  });
  it("maps the reset payload exactly and preserves the six-digit string", async () => {
    vi.mocked(api.resetPassword).mockResolvedValue(undefined);
    await workspacePasswordRecoveryApi.resetPassword({
      email: "person@example.com",
      code: "001234",
      newPassword: "password123",
      confirmPassword: "password123",
    });
    expect(api.resetPassword).toHaveBeenCalledWith({
      email: "person@example.com",
      code: "001234",
      new_password: "password123",
      confirm_password: "password123",
    });
  });
  it("distinguishes a rejected code from other failures so the user can correct it", async () => {
    const input = {
      email: "person@example.com",
      code: "001234",
      newPassword: "password123",
      confirmPassword: "password123",
    };
    vi.mocked(api.resetPassword).mockRejectedValueOnce(
      new Error("Código inválido ou expirado."),
    );
    await expect(
      workspacePasswordRecoveryApi.resetPassword(input),
    ).rejects.toBeInstanceOf(RecoveryCodeError);
    vi.mocked(api.resetPassword).mockRejectedValueOnce(
      new Error("Serviço indisponível."),
    );
    await expect(
      workspacePasswordRecoveryApi.resetPassword(input),
    ).rejects.toThrow("Serviço indisponível.");
  });
});
