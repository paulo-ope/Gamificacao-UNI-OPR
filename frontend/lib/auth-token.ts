"use client";

// Módulo único de gerenciamento do token de sessão (JWT) - achado da auditoria de 2026-09-14: a
// mesma chave de localStorage e a mesma lógica de leitura/escrita estavam duplicadas de forma
// independente em 6 arquivos (api.ts, operations-api.ts, scheduling-api.ts, localiza-api.ts,
// intelligence-cockpit-api.ts, ai-governance-api.ts). Um deles (`localiza-api.ts`) cacheava o
// token numa variável de módulo lida só na primeira importação, sem nenhum jeito de atualizar -
// login/logout feito depois que aquele módulo já tinha carregado continuava usando o token velho
// (ou nenhum) nas chamadas do Localiza, um bug real de sessão cruzada, não só duplicação de
// código. Com todo client HTTP lendo/escrevendo esta ÚNICA variável, isso deixa de ser possível.
//
// Deliberadamente NÃO migra para cookie HttpOnly nesta rodada (pedido explícito, 2026-09-14) -
// isso exigiria mudar o fluxo de auth backend/frontend inteiro. Só elimina a duplicação e cria um
// ponto único de onde uma futura migração de storage partiria.
const TOKEN_KEY = "gamification_auth_token";

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

let authToken: string | null = readStoredToken();

export function getAuthToken(): string | null {
  return authToken;
}

export function setAuthToken(token: string | null) {
  authToken = token;
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

/** Header pronto pra spread num `Headers`/objeto de fetch - `{}` quando não há sessão. */
export function authHeader(): HeadersInit {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

/** Assina notificações de "a sessão caiu" (hoje só `useWorkspaceAuth` ouve, pra derrubar a tela
 * pro login sem precisar de reload de página). Devolve a função de cancelamento. */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

/** Chamado por QUALQUER client HTTP do app ao receber 401 - limpa o token e avisa quem estiver
 * ouvindo. Idempotente: chamar de novo com a sessão já limpa não tem efeito colateral extra. */
export function notifyUnauthorized() {
  setAuthToken(null);
  unauthorizedListeners.forEach((listener) => listener());
}
