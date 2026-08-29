"use client";

import { Ban, Loader2, Mail } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { IxcCpfInvitePanel } from "@/components/admin/ixc-cpf-invite-panel";
import type { AdminPersonStructure, PortalInvite, PortalInviteCreateResult } from "@/lib/types";

import { INVITE_STATUS_BADGE, INVITE_STATUS_LABELS } from "./admin-shared";

type Props = {
  people: AdminPersonStructure[];
  invites: PortalInvite[];
  canWriteUsers: boolean;
  inviteEmail: string;
  inviteCollaboratorId: string;
  creatingInvite: boolean;
  revealedInviteLink: { email: string; link: string } | null;
  onInviteEmailChange: (value: string) => void;
  onInviteCollaboratorIdChange: (value: string) => void;
  onCreateInvite: () => void;
  onIxcInviteCreated: (result: PortalInviteCreateResult) => void;
  onDismissRevealedInviteLink: () => void;
  onRevokeInvite: (invite: PortalInvite) => void;
};

export function InvitesPanel({
  people,
  invites,
  canWriteUsers,
  inviteEmail,
  inviteCollaboratorId,
  creatingInvite,
  revealedInviteLink,
  onInviteEmailChange,
  onInviteCollaboratorIdChange,
  onCreateInvite,
  onIxcInviteCreated,
  onDismissRevealedInviteLink,
  onRevokeInvite,
}: Props) {
  return (
    <div className="grid gap-6">
      {canWriteUsers ? <IxcCpfInvitePanel people={people} invites={invites} onInviteCreated={onIxcInviteCreated} /> : null}

      <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-5">
          <h3 className="text-lg font-semibold text-slate-950">Convite manual e histórico</h3>
          <p className="text-sm text-slate-500">
            Convide informando o e-mail e o colaborador diretamente (sem buscar no IXC) - o vínculo é definido aqui pelo admin, nunca por quem aceita o convite.
          </p>
        </div>

        {revealedInviteLink ? (
          <div className="m-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex items-center gap-2 font-semibold">
              <Mail className="h-4 w-4" /> Copie agora - o link de convite para {revealedInviteLink.email} não será mostrado de novo:
            </div>
            <code className="mt-2 block break-all rounded-lg bg-white p-2 text-xs">{revealedInviteLink.link}</code>
            <Button type="button" variant="outline" className="mt-3" onClick={onDismissRevealedInviteLink}>
              Já copiei
            </Button>
          </div>
        ) : null}

        {canWriteUsers ? (
          <div className="grid gap-3 border-b border-slate-200 p-5 sm:grid-cols-[1fr_1fr_auto]">
            <div className="grid gap-1.5">
              <Label>Colaborador</Label>
              <select
                value={inviteCollaboratorId}
                className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
                onChange={(event) => onInviteCollaboratorIdChange(event.target.value)}
              >
                <option value="">Selecione...</option>
                {people
                  .filter((person) => !person.portal_user_id)
                  .map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                    </option>
                  ))}
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label>E-mail do convite</Label>
              <Input
                type="email"
                placeholder="pessoa@exemplo.com"
                value={inviteEmail}
                onChange={(event) => onInviteEmailChange(event.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button type="button" disabled={creatingInvite || !inviteEmail.trim() || !inviteCollaboratorId} onClick={onCreateInvite}>
                {creatingInvite ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                Criar convite
              </Button>
            </div>
          </div>
        ) : null}

        <div className="overflow-x-auto p-5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>E-mail</TableHead>
                <TableHead>Colaborador</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Expira em</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invites.map((invite) => (
                <TableRow key={invite.id}>
                  <TableCell className="text-sm text-slate-600">{invite.email}</TableCell>
                  <TableCell className="text-sm text-slate-600">{invite.collaborator_name || "—"}</TableCell>
                  <TableCell>
                    <Badge className={INVITE_STATUS_BADGE[invite.status] || "bg-slate-100 text-slate-600"}>
                      {INVITE_STATUS_LABELS[invite.status] || invite.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{new Date(invite.expires_at).toLocaleString("pt-BR")}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      {canWriteUsers && invite.status === "pending" ? (
                        <Button
                          aria-label={`Revogar convite de ${invite.email}`}
                          title="Revogar convite"
                          type="button"
                          size="sm"
                          variant="outline"
                          className="text-red-600"
                          onClick={() => onRevokeInvite(invite)}
                        >
                          <Ban className="h-3.5 w-3.5" />
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {!invites.length ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-slate-400">
                    Nenhum convite criado ainda.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
