import { api } from "./api";
import {
  RecoveryCodeError,
  type PasswordRecoveryApi,
} from "./password-recovery";

/** Contract verified from the running backend's OpenAPI schema.
 * This backend validates the code on reset; it has no separate verification route.
 */
export const workspacePasswordRecoveryApi: PasswordRecoveryApi = {
  async requestCode(email) {
    await api.forgotPassword(email);
    return { retryAfterSeconds: 60 };
  },
  async resetPassword({ email, code, newPassword, confirmPassword }) {
    try {
      await api.resetPassword({
        email,
        code,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
    } catch (error) {
      if (error instanceof Error && /c[oó]digo|\bcode\b/i.test(error.message))
        throw new RecoveryCodeError(error.message);
      throw error;
    }
  },
};
