"use client";

import { KeyRound, Plus, RotateCcw, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AccessProfile, AuthUser } from "@/lib/types";

import { profileNames } from "./admin-shared";

type Props = {
  title: string;
  description: string;
  emptyLabel: string;
  rows: AuthUser[];
  profiles: AccessProfile[];
  canWriteUsers: boolean;
  canDeleteUsers: boolean;
  showNewUserButton?: boolean;
  onNewUser?: () => void;
  revealedTemporaryPassword: { name: string; password: string } | null;
  onDismissRevealedPassword: () => void;
  onEdit: (row: AuthUser) => void;
  onForcePasswordReset: (row: AuthUser) => void;
  onForceFirstAccessReset: (row: AuthUser) => void;
  onDelete: (row: AuthUser) => void;
};

export function AccountsTable({
  title,
  description,
  emptyLabel,
  rows,
  profiles,
  canWriteUsers,
  canDeleteUsers,
  showNewUserButton,
  onNewUser,
  revealedTemporaryPassword,
  onDismissRevealedPassword,
  onEdit,
  onForcePasswordReset,
  onForceFirstAccessReset,
  onDelete,
}: Props) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-5">
        <div>
          <h3 className="text-lg font-semibold text-slate-950">{title}</h3>
          <p className="text-sm text-slate-500">{description}</p>
        </div>
        {showNewUserButton && canWriteUsers ? (
          <Button type="button" onClick={onNewUser}>
            <Plus className="h-4 w-4" /> Novo usuário
          </Button>
        ) : null}
      </div>
      {revealedTemporaryPassword ? (
        <div className="m-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex items-center gap-2 font-semibold">
            <KeyRound className="h-4 w-4" /> Copie agora - esta senha temporária de {revealedTemporaryPassword.name} não será mostrada de novo:
          </div>
          <code className="mt-2 block break-all rounded-lg bg-white p-2 text-xs">{revealedTemporaryPassword.password}</code>
          <Button type="button" variant="outline" className="mt-3" onClick={onDismissRevealedPassword}>
            Já copiei
          </Button>
        </div>
      ) : null}
      <div className="overflow-x-auto p-5">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>E-mail</TableHead>
              <TableHead>Perfis</TableHead>
              <TableHead>Regionais</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-medium text-slate-950">{row.name}</TableCell>
                <TableCell className="text-sm text-slate-600">{row.email}</TableCell>
                <TableCell className="max-w-xs text-sm text-slate-600">{profileNames(row, profiles)}</TableCell>
                <TableCell className="text-sm text-slate-600">{row.managed_regionals.join(", ") || "—"}</TableCell>
                <TableCell>
                  <Badge className={row.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                    {row.active ? "Ativo" : "Inativo"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    {canWriteUsers ? (
                      <Button type="button" size="sm" variant="outline" onClick={() => onEdit(row)}>
                        Editar
                      </Button>
                    ) : null}
                    {canWriteUsers ? (
                      <Button
                        aria-label={`Forçar troca de senha de ${row.name}`}
                        title="Forçar troca de senha"
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => onForcePasswordReset(row)}
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                    {canWriteUsers && row.collaborator_id ? (
                      <Button
                        aria-label={`Forçar primeiro acesso completo de ${row.name}`}
                        title="Forçar primeiro acesso completo"
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => onForceFirstAccessReset(row)}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                    {canDeleteUsers ? (
                      <Button type="button" size="sm" variant="outline" className="text-red-600" onClick={() => onDelete(row)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!rows.length ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-sm text-slate-500">
                  {emptyLabel}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
