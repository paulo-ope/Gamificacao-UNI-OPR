"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AppCheckbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { fetchSupportTvConfig, saveSupportTvConfig, type SupportTvConfig, type SupportTvDepartmentOption } from "@/lib/support-tv-api";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Chamado depois de salvar, para a TV recarregar já com o novo recorte.
  onSaved: () => void;
};

const normalize = (value: string) => value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR");

export function TvConfigDialog({ open, onOpenChange, onSaved }: Props) {
  const [config, setConfig] = useState<SupportTvConfig | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Lista dentro do próprio diálogo (e não num seletor suspenso): o diálogo é modal e bloqueia o
  // clique em qualquer popup que abra fora dele - o seletor suspenso não conseguia ser usado.
  const visibleDepartments = useMemo(() => {
    const term = normalize(search.trim());
    const all = config?.available_departments ?? [];
    return term ? all.filter((option) => normalize(option.name).includes(term)) : all;
  }, [config, search]);

  function toggle(option: SupportTvDepartmentOption) {
    setSelected((current) => (current.includes(option.id) ? current.filter((id) => id !== option.id) : [...current, option.id]));
  }

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSearch("");
    fetchSupportTvConfig()
      .then((data) => {
        if (cancelled) return;
        setConfig(data);
        setSelected(data.department_ids);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Não foi possível carregar a configuração.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await saveSupportTvConfig(selected);
      onSaved();
      onOpenChange(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar a configuração.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Configurar a TV</DialogTitle>
          <DialogDescription>
            Escolha os departamentos que a TV vai considerar. Sem nenhum selecionado, ela mostra todos. O radar de incidente e o
            Suporte interno N1 vêm do IXC e não dependem desta escolha.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="py-6 text-center text-sm text-slate-500">Carregando departamentos...</p>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-slate-700">Departamentos</p>
              <p className="text-xs text-slate-500">
                {selected.length === 0 ? "Todos os departamentos" : `${selected.length} selecionado(s)`}
              </p>
            </div>
            <Input aria-label="Pesquisar departamento" placeholder="Pesquisar departamento..." value={search} onChange={(event) => setSearch(event.target.value)} />
            <ul className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-1" aria-label="Departamentos da TV">
              {visibleDepartments.map((option) => {
                const checked = selected.includes(option.id);
                return (
                  <li key={option.id}>
                    <label className="flex cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 text-sm text-slate-800 hover:bg-slate-50">
                      <AppCheckbox checked={checked} onCheckedChange={() => toggle(option)} ariaLabel={option.name} />
                      <span className="min-w-0 flex-1 break-words">{option.name}</span>
                    </label>
                  </li>
                );
              })}
              {visibleDepartments.length === 0 ? (
                <li className="px-2.5 py-3 text-sm text-slate-500">
                  {config && config.available_departments.length === 0 ? "Nenhum departamento encontrado nos atendimentos importados ainda." : "Nenhum departamento encontrado."}
                </li>
              ) : null}
            </ul>
            {selected.length > 0 ? (
              <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setSelected([])}>
                Limpar seleção (mostrar todos)
              </Button>
            ) : null}
          </div>
        )}

        {error ? (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button type="button" onClick={save} disabled={saving || loading || !config}>
            {saving ? "Salvando..." : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
