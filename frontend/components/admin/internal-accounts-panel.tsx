"use client";

import type { AccessProfile, AuthUser } from "@/lib/types";

import { AccountsTable } from "./accounts-table";

type Props = {
  users: AuthUser[];
  profiles: AccessProfile[];
  canWriteUsers: boolean;
  canDeleteUsers: boolean;
  onNewUser: () => void;
  revealedTemporaryPassword: { name: string; password: string } | null;
  onDismissRevealedPassword: () => void;
  onEdit: (row: AuthUser) => void;
  onForcePasswordReset: (row: AuthUser) => void;
  onForceFirstAccessReset: (row: AuthUser) => void;
  onDelete: (row: AuthUser) => void;
};

export function InternalAccountsPanel({ users, ...rest }: Props) {
  const rows = users.filter((row) => !row.collaborator_id);
  return (
    <AccountsTable
      title="Contas internas"
      description="Acessos ao Workspace sem vínculo com um colaborador (equipe interna, administração)."
      emptyLabel="Nenhuma conta interna encontrada."
      rows={rows}
      showNewUserButton
      {...rest}
    />
  );
}
