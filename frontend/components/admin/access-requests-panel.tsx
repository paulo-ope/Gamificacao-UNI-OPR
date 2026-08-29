"use client";

import { Ban, IdCard, Loader2, Mail } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AdminPersonStructure, PortalAccessRequest } from "@/lib/types";

import { ACCESS_REQUEST_STATUS_BADGE, ACCESS_REQUEST_STATUS_LABELS } from "./admin-shared";

type Props = {
  accessRequests: PortalAccessRequest[];
  people: AdminPersonStructure[];
  canWriteUsers: boolean;
  decidingAccessRequestId: number | null;
  approveCollaboratorByRequest: Record<number, string>;
  onApproveCollaboratorChange: (requestId: number, collaboratorId: string) => void;
  onApprove: (request: PortalAccessRequest) => void;
  onReject: (request: PortalAccessRequest) => void;
};

export function AccessRequestsPanel({
  accessRequests,
  people,
  canWriteUsers,
  decidingAccessRequestId,
  approveCollaboratorByRequest,
  onApproveCollaboratorChange,
  onApprove,
  onReject,
}: Props) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 p-5">
        <h3 className="text-lg font-semibold text-slate-950">Solicitações de acesso</h3>
        <p className="text-sm text-slate-500">
          Pedidos de quem ainda não tem conta nem convite. Aprovar cria a conta direto, com a senha que a pessoa já definiu (o vínculo com o colaborador precisa ser confirmado aqui, mesmo quando já existe uma sugestão automática por CPF/IXC).
        </p>
      </div>

      <div className="overflow-x-auto p-5">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>CPF</TableHead>
              <TableHead>Contato</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Decisão</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accessRequests.map((item) => (
              <TableRow key={item.id} className={item.status === "pending" ? "bg-blue-50/40" : undefined}>
                <TableCell className="font-medium text-slate-950">{item.name}</TableCell>
                <TableCell className="text-sm text-slate-600">{item.cpf_masked || "—"}</TableCell>
                <TableCell className="text-sm text-slate-600">
                  <div>{item.phone}</div>
                  <div className="text-slate-400">{item.email}</div>
                </TableCell>
                <TableCell>
                  <Badge className={ACCESS_REQUEST_STATUS_BADGE[item.status] || "bg-slate-100 text-slate-600"}>
                    {ACCESS_REQUEST_STATUS_LABELS[item.status] || item.status}
                  </Badge>
                  {item.status !== "pending" ? (
                    <p className="mt-1 max-w-[220px] text-xs text-slate-400">
                      {item.reviewed_by_name ? `Por ${item.reviewed_by_name}` : null}
                      {item.decision_reason ? ` - ${item.decision_reason}` : null}
                    </p>
                  ) : null}
                </TableCell>
                <TableCell>
                  {item.status === "pending" && canWriteUsers ? (
                    <div className="flex flex-col items-end gap-2">
                      {item.suggested_collaborator_id && item.suggested_collaborator_name ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-[#2d5fff]/25 bg-[#2d5fff]/10 px-2.5 py-1 text-[11px] font-medium text-[#0028f3]">
                          <IdCard className="h-3 w-3" aria-hidden="true" />
                          Sugestão por CPF/IXC: {item.suggested_collaborator_name}
                        </span>
                      ) : null}
                      <select
                        value={approveCollaboratorByRequest[item.id] ?? (item.suggested_collaborator_id ? String(item.suggested_collaborator_id) : "")}
                        className="h-9 w-full max-w-[220px] rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
                        onChange={(event) => onApproveCollaboratorChange(item.id, event.target.value)}
                      >
                        <option value="">Selecione o colaborador...</option>
                        {people
                          .filter((person) => !person.portal_user_id)
                          .map((person) => (
                            <option key={person.id} value={person.id}>
                              {person.name}
                              {person.id === item.suggested_collaborator_id ? " (sugestão)" : ""}
                            </option>
                          ))}
                      </select>
                      <div className="flex justify-end gap-2">
                        <Button
                          aria-label={`Aprovar solicitação de ${item.name}`}
                          type="button"
                          size="sm"
                          disabled={decidingAccessRequestId === item.id}
                          onClick={() => onApprove(item)}
                        >
                          {decidingAccessRequestId === item.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
                          Aprovar
                        </Button>
                        <Button
                          aria-label={`Rejeitar solicitação de ${item.name}`}
                          type="button"
                          size="sm"
                          variant="outline"
                          className="text-red-600"
                          disabled={decidingAccessRequestId === item.id}
                          onClick={() => onReject(item)}
                        >
                          <Ban className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
            {!accessRequests.length ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-sm text-slate-400">
                  Nenhuma solicitação de acesso recebida ainda.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
