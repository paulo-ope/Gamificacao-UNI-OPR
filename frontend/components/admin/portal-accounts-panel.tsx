"use client";

import type { AccessProfile, AuthUser } from "@/lib/types";

import { AccountsTable } from "./accounts-table";

type Props = {
  users: AuthUser[];
  profiles: AccessProfile[];
  canWriteUsers: boolean;
  canDeleteUsers: boolean;
  revealedTemporaryPassword: { name: string; password: string } | null;
  onDismissRevealedPassword: () => void;
  onEdit: (row: AuthUser) => void;
  onForcePasswordReset: (row: AuthUser) => void;
  onForceFirstAccessReset: (row: AuthUser) => void;
  onDelete: (row: AuthUser) => void;
};

export function PortalAccountsPanel({ users, ...rest }: Props) {
  const rows = users.filter((row) => row.collaborator_id);
  return (
    <AccountsTable
      title="Contas do Portal"
      description="Acessos vinculados a um colaborador - login do Portal do Colaborador."
      emptyLabel="Nenhuma conta do Portal encontrada."
      rows={rows}
      {...rest}
    />
  );
}
