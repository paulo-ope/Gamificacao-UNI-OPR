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

  // Reconsulta `/auth/me` sem passar pelo formulário de login - usada depois que algo no backend
  // muda o próprio usuário sem trocar de sessão (ex: concluir o primeiro acesso do Portal, que
  // vira `portal_first_access_required=false` sem gerar um token novo). Mantém o padrão de erro
  // silencioso do carregamento inicial: se a sessão caiu nesse meio-tempo, `user` vira null e a
  // tela de login normal assume - não precisa de um estado de erro dedicado aqui.
  const refresh = useCallback(async () => {
    try {
      const current = await api.me();
      setUser(current);
      return current;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  return { user, checking, error, login, logout, refresh, clearError: () => setError(null) };
}
