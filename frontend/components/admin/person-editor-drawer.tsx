"use client";

import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AdminPeopleStructure } from "@/lib/types";

import { EMPLOYEE_TYPE_LABELS, STRUCTURE_STATUS_LABELS, TEAM_TYPE_LABELS, type PersonStructureDraft } from "./admin-shared";

type Props = {
  personDraft: PersonStructureDraft;
  peopleStructure: AdminPeopleStructure;
  saving: boolean;
  canWriteUsers: boolean;
  onChange: (patch: Partial<PersonStructureDraft>) => void;
  onCancel: () => void;
  onSave: () => void;
};

export function PersonEditorDrawer({ personDraft, peopleStructure, saving, canWriteUsers, onChange, onCancel, onSave }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/30 p-4">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-slate-950">Estrutura do colaborador</h3>
        <p className="mt-1 text-sm text-slate-500">{personDraft.name}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="grid gap-2">
            <Label>CPF</Label>
            <Input
              value={personDraft.cpf}
              placeholder="Preencher somente se for alterar"
              onChange={(event) => onChange({ cpf: event.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label>Status</Label>
            <select
              value={personDraft.structure_status}
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              onChange={(event) => onChange({ structure_status: event.target.value })}
            >
              {peopleStructure.statuses.map((status) => (
                <option key={status} value={status}>{STRUCTURE_STATUS_LABELS[status] || status}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <Label>Tipo de colaborador</Label>
            <select
              value={personDraft.employee_type}
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              onChange={(event) => onChange({ employee_type: event.target.value })}
            >
              <option value="">Sem tipo</option>
              {peopleStructure.employee_types.map((type) => (
                <option key={type} value={type}>{EMPLOYEE_TYPE_LABELS[type] || type}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <Label>Tipo de equipe</Label>
            <select
              value={personDraft.team_type}
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              onChange={(event) => onChange({ team_type: event.target.value })}
            >
              <option value="">Sem equipe</option>
              {peopleStructure.team_types.map((type) => (
                <option key={type} value={type}>{TEAM_TYPE_LABELS[type] || type}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <Label>Supervisor</Label>
            <select
              value={personDraft.supervisor_user_id}
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              onChange={(event) => onChange({ supervisor_user_id: event.target.value ? Number(event.target.value) : "" })}
            >
              <option value="">Sem supervisor</option>
              {peopleStructure.supervisors.map((option) => (
                <option key={option.id} value={option.id}>{option.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <Label>Gerente regional</Label>
            <select
              value={personDraft.regional_manager_user_id}
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
              onChange={(event) => onChange({ regional_manager_user_id: event.target.value ? Number(event.target.value) : "" })}
            >
              <option value="">Sem gerente</option>
              {peopleStructure.regional_managers.map((option) => (
                <option key={option.id} value={option.id}>{option.name}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2 md:col-span-2">
            <Label>Observação</Label>
            <Input value={personDraft.structure_notes} onChange={(event) => onChange({ structure_notes: event.target.value })} />
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>Cancelar</Button>
          <Button type="button" onClick={onSave} disabled={saving || !canWriteUsers}>
            <Save className="h-4 w-4" /> {saving ? "Salvando..." : "Salvar estrutura"}
          </Button>
        </div>
      </div>
    </div>
  );
}
