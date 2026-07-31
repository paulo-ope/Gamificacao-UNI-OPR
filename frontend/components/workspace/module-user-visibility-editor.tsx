"use client";

import { Trash2, UserPlus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { AdminModuleUserVisibility } from "@/lib/types";

type UserOption = { id: number; name: string; email: string };

export function ModuleUserVisibilityEditor({
  overrides,
  users,
  saving,
  disabled,
  onAdd,
  onRemove,
}: {
  overrides: AdminModuleUserVisibility[];
  users: UserOption[];
  saving: boolean;
  disabled: boolean;
  onAdd: (userId: number, visible: boolean) => void;
  onRemove: (userId: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<number | "">("");
  const [visible, setVisible] = useState(false);

  const overriddenIds = new Set(overrides.map((item) => item.user_id));
  const availableUsers = users.filter((user) => !overriddenIds.has(user.id));

  function submit() {
    if (selectedUserId === "") return;
    onAdd(Number(selectedUserId), visible);
    setSelectedUserId("");
    setVisible(false);
    setOpen(false);
  }

  return (
    <div className="mt-2 grid gap-2">
      {overrides.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {overrides.map((item) => (
            <span
              key={item.user_id}
              className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs ${
                item.visible ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-700"
              }`}
              title={item.reason || undefined}
            >
              <span className="font-medium">{item.user_name}</span>
              <span>{item.visible ? "liberado" : "oculto"}</span>
              <button
                type="button"
                disabled={disabled || saving}
                onClick={() => onRemove(item.user_id)}
                aria-label={`Remover exceção de ${item.user_name}`}
                className="text-current/70 hover:text-current"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}

      {open ? (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
          <select
            className="h-9 rounded-md border border-input bg-white px-2 text-xs"
            value={selectedUserId}
            onChange={(event) => setSelectedUserId(event.target.value ? Number(event.target.value) : "")}
          >
            <option value="">Selecionar usuário...</option>
            {availableUsers.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name} ({user.email})
              </option>
            ))}
          </select>
          <select
            className="h-9 rounded-md border border-input bg-white px-2 text-xs"
            value={visible ? "visible" : "hidden"}
            onChange={(event) => setVisible(event.target.value === "visible")}
          >
            <option value="hidden">Ocultar para este usuário</option>
            <option value="visible">Liberar para este usuário</option>
          </select>
          <Button type="button" size="sm" disabled={disabled || saving || selectedUserId === ""} onClick={submit}>
            Salvar
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancelar
          </Button>
        </div>
      ) : (
        <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => setOpen(true)}>
          <UserPlus className="h-3.5 w-3.5" /> Exceção por usuário
        </Button>
      )}
    </div>
  );
}
