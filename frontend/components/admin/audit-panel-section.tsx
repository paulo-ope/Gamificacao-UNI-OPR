"use client";

import { AuditTrailPanel } from "@/components/shared/audit-trail-panel";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type PermissionModuleRow = { module: string; count: number; writeCount: number };

type Props = {
  canReadAudit: boolean;
  permissionModuleRows: PermissionModuleRow[];
};

export function AuditPanelSection({ canReadAudit, permissionModuleRows }: Props) {
  return (
    <div className="grid gap-4">
      {canReadAudit ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <AuditTrailPanel title="Auditoria administrativa (todos os módulos)" />
        </div>
      ) : (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Seu perfil não possui a permissão admin:audit:read para ver a trilha de auditoria.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-semibold text-slate-950">Mapa de permissões</h3>
          <div className="mt-4 grid gap-2">
            {permissionModuleRows.map((row) => (
              <div key={row.module} className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                <span className="font-medium text-slate-800">{row.module}</span>
                <span className="text-slate-500">{row.count} permissões</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-5">
            <h3 className="text-lg font-semibold text-slate-950">Ações sensíveis</h3>
          </div>
          <div className="overflow-x-auto p-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Módulo</TableHead>
                  <TableHead>Permissões de escrita</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {permissionModuleRows.map((row) => (
                  <TableRow key={row.module}>
                    <TableCell className="font-medium text-slate-950">{row.module}</TableCell>
                    <TableCell className="text-sm text-slate-600">{row.writeCount}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </div>
  );
}
