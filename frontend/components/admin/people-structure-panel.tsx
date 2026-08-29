"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AdminPeopleStructure, AdminPersonStructure } from "@/lib/types";

import { STRUCTURE_STATUS_LABELS, STRUCTURE_TYPES, TEAM_TYPE_LABELS } from "./admin-shared";

type Props = {
  peopleStructure: AdminPeopleStructure | null;
  filteredPeople: AdminPersonStructure[];
  canWriteUsers: boolean;
  personSearch: string;
  personStatusFilter: string;
  onPersonSearchChange: (value: string) => void;
  onPersonStatusFilterChange: (value: string) => void;
  onEditPerson: (person: AdminPersonStructure) => void;
};

export function PeopleStructurePanel({
  peopleStructure,
  filteredPeople,
  canWriteUsers,
  personSearch,
  personStatusFilter,
  onPersonSearchChange,
  onPersonStatusFilterChange,
  onEditPerson,
}: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-950">Pessoas e estrutura</h3>
          <Badge className="bg-blue-50 text-blue-700">Governança</Badge>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.active_people || 0}</p>
            <p className="text-xs text-slate-500">Pessoas ativas</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.without_supervisor || 0}</p>
            <p className="text-xs text-slate-500">Campo sem supervisor</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.without_team_type || 0}</p>
            <p className="text-xs text-slate-500">Sem tipo de equipe</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-2xl font-bold text-slate-950">{peopleStructure?.summary.pending_review || 0}</p>
            <p className="text-xs text-slate-500">Pendentes</p>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {STRUCTURE_TYPES.map((type) => (
            <Badge key={type} className="border border-slate-200 bg-white text-slate-700">
              {type}
            </Badge>
          ))}
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
          <h3 className="text-lg font-semibold text-slate-950">Colaboradores</h3>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input value={personSearch} placeholder="Buscar pessoa" onChange={(event) => onPersonSearchChange(event.target.value)} />
            <select
              value={personStatusFilter}
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              onChange={(event) => onPersonStatusFilterChange(event.target.value)}
            >
              <option value="all">Todos</option>
              {(peopleStructure?.statuses || []).map((status) => (
                <option key={status} value={status}>{STRUCTURE_STATUS_LABELS[status] || status}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="overflow-x-auto p-5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Colaborador</TableHead>
                <TableHead>Equipe</TableHead>
                <TableHead>Supervisor</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredPeople.slice(0, 30).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <div className="font-medium text-slate-950">{row.name}</div>
                    <div className="text-xs text-slate-500">{row.regional} · {row.role}</div>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {row.team_type ? TEAM_TYPE_LABELS[row.team_type] || row.team_type : "Pendente"}
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{row.supervisor_name || "Pendente"}</TableCell>
                  <TableCell>
                    <Badge className={row.structure_status === "validated" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}>
                      {STRUCTURE_STATUS_LABELS[row.structure_status] || row.structure_status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {canWriteUsers ? (
                      <Button type="button" size="sm" variant="outline" onClick={() => onEditPerson(row)}>
                        Editar
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
              {filteredPeople.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                    Nenhum colaborador encontrado.
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
