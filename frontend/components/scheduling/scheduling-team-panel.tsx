"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { StatusToast } from "@/components/ui/status-toast";
import { schedulingApi, type SchedulingTeamMember } from "@/lib/scheduling-api";

// View "Equipe" do menu do módulo - mesmo padrão de painel fixo (não modal) das outras visões do
// cockpit, trocado pelo `SchedulingModuleSidebar`.
export function SchedulingTeamPanel({ onSaved }: { onSaved: () => void }) {
  const [members, setMembers] = useState<SchedulingTeamMember[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    void schedulingApi.team().then(setMembers).catch(() => setError("Falha ao carregar os operadores."));
  }, []);

  const visible = (members || []).filter((member) => member.name.toLocaleLowerCase("pt-BR").includes(query.toLocaleLowerCase("pt-BR")));

  function toggle(ixcUserId: number) {
    setMembers((current) =>
      (current || []).map((item) => (item.ixc_user_id === ixcUserId ? { ...item, is_team_member: !item.is_team_member } : item)),
    );
  }

  async function save() {
    if (!members) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.updateTeam(members.filter((m) => m.is_team_member).map((m) => m.ixc_user_id));
      onSaved();
      setMessage("Equipe salva.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar a equipe.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold text-slate-950">Equipe de agendamento</CardTitle>
        <p className="text-xs text-slate-500">A meta diária só é cobrada de quem está marcado como membro.</p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <StatusToast error={error} message={message} onDismissError={() => setError(null)} onDismissMessage={() => setMessage(null)} />
        <Input
          type="search"
          placeholder="Buscar operador..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="mb-2"
        />
        <div className="max-h-96 space-y-1 overflow-y-auto rounded-xl border border-slate-100 p-1">
          {members === null ? (
            <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          ) : (
            visible.map((member) => (
              <div
                key={member.ixc_user_id}
                role="button"
                tabIndex={0}
                onClick={() => toggle(member.ixc_user_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    toggle(member.ixc_user_id);
                  }
                }}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                <AppCheckbox
                  checked={member.is_team_member}
                  onCheckedChange={() => toggle(member.ixc_user_id)}
                  ariaLabel={`Membro da equipe: ${member.name}`}
                  className="h-4 w-4"
                />
                <span className="truncate">{member.name}</span>
              </div>
            ))
          )}
        </div>
        <div className="mt-4 flex items-center justify-between gap-2">
          <p className="text-xs text-slate-500">{(members || []).filter((m) => m.is_team_member).length} membro(s) na equipe</p>
          <Button type="button" onClick={() => void save()} disabled={saving || members === null}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Salvar equipe
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
