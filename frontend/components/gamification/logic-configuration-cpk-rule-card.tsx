"use client";

import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { CPK_RULE_LABEL, type CpkRule } from "@/lib/types";

const CPK_RULE_HELP: Record<CpkRule, string> = {
  both: "Na meta soma o bônus e fora da meta desconta a penalidade do multiplicador (padrão).",
  penalty_only: "Só desconta a penalidade de quem está fora da meta; quem está na meta não ganha bônus.",
  bonus_only: "Só soma o bônus de quem está na meta; quem está fora da meta não é descontado.",
  none: "O CPK não altera o multiplicador de nenhuma regional neste mês."
};

type Props = {
  cpkPeriod: { year: number; month: number };
  setCpkPeriod: Dispatch<SetStateAction<{ year: number; month: number }>>;
};

export function CpkRuleCard({ cpkPeriod, setCpkPeriod }: Props) {
  const [rule, setRule] = useState<CpkRule | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setNote(null);
    setRule(null);
    api
      .cpkRule(cpkPeriod.year, cpkPeriod.month)
      .then((result) => !cancelled && setRule(result.rule))
      .catch(() => !cancelled && setNote("Não foi possível carregar a regra de CPK deste período."));
    return () => {
      cancelled = true;
    };
  }, [cpkPeriod.year, cpkPeriod.month]);

  async function changeRule(next: CpkRule) {
    try {
      const result = await api.saveCpkRule(cpkPeriod.year, cpkPeriod.month, next);
      setRule(result.rule);
      setNote("Regra salva. Recalcule o período para aplicar aos valores do pagamento.");
    } catch (error) {
      setNote(error instanceof Error ? error.message : "Não foi possível salvar a regra de CPK.");
    }
  }

  return (
    <section className="mt-4 rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]">
      <div className="panel-header">
        <div>
          <h3 className="panel-title">Regra de CPK por competência</h3>
          <p className="panel-subtitle">
            Define se o CPK soma, desconta, ambos ou nenhum no multiplicador de cada regional naquele mês. Vale para o
            mês escolhido, não para os demais.
          </p>
        </div>
      </div>
      <div className="grid gap-4 border-t border-slate-200 p-5 md:grid-cols-3">
        <div className="grid gap-2">
          <Label>Ano de referência</Label>
          <Input
            inputMode="numeric"
            value={cpkPeriod.year}
            onChange={(event) => setCpkPeriod({ ...cpkPeriod, year: Number(event.target.value) || cpkPeriod.year })}
          />
        </div>
        <div className="grid gap-2">
          <Label>Mês de referência</Label>
          <Input
            inputMode="numeric"
            value={cpkPeriod.month}
            onChange={(event) => setCpkPeriod({ ...cpkPeriod, month: Number(event.target.value) || cpkPeriod.month })}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="cpk-rule-select">Regra de CPK</Label>
          <select
            id="cpk-rule-select"
            value={rule ?? ""}
            disabled={rule === null}
            onChange={(event) => void changeRule(event.target.value as CpkRule)}
            className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
          >
            {rule === null ? <option value="">Carregando...</option> : null}
            {(Object.keys(CPK_RULE_LABEL) as CpkRule[]).map((option) => (
              <option key={option} value={option}>
                {CPK_RULE_LABEL[option]}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-3">
          {rule ? <p className="text-sm text-slate-600">{CPK_RULE_HELP[rule]}</p> : null}
          {note ? <p className="mt-1 text-xs text-slate-500">{note}</p> : null}
          <p className="mt-1 text-xs text-slate-400">
            "Sem base" nunca interfere. Regional no piso de saúde (multiplicador mínimo) não recebe o ajuste de CPK.
          </p>
        </div>
      </div>
    </section>
  );
}
