"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { AuthUser } from "@/lib/types";

type WorkspaceShellContextValue = {
  user: AuthUser;
  logout: () => void;
};

const WorkspaceShellContext = createContext<WorkspaceShellContextValue | null>(null);

export function WorkspaceShellProvider({
  value,
  children,
}: {
  value: WorkspaceShellContextValue;
  children: ReactNode;
}) {
  return <WorkspaceShellContext.Provider value={value}>{children}</WorkspaceShellContext.Provider>;
}

// Usado pelas páginas de módulo já migradas pro shell `(shell)/layout.tsx` - evita que cada uma
// chame `useWorkspaceAuth()` de novo (duplicando o GET /auth/me que o próprio shell já fez).
export function useWorkspaceShell() {
  const context = useContext(WorkspaceShellContext);
  if (!context) {
    throw new Error("useWorkspaceShell só pode ser usado dentro do layout (shell).");
  }
  return context;
}
