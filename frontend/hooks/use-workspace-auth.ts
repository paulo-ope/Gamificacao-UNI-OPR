"use client";

import { useCallback, useEffect, useState } from "react";

import { api, setAuthToken } from "@/lib/api";
import type { AuthUser } from "@/lib/types";


export function useWorkspaceAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .me()
      .then((current) => {
        if (active) setUser(current);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    setChecking(true);
    try {
      const result = await api.login(email, password);
      setAuthToken(result.access_token);
      setUser(result.user);
      return result.user;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Não foi possível entrar.";
      setError(message);
      throw reason;
    } finally {
      setChecking(false);
    }
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  return { user, checking, error, login, logout, clearError: () => setError(null) };
}
