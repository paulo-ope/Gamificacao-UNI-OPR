"use client";

import { AlertTriangle, CheckCircle2, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { OverviewBlock } from "@/components/overview/overview-block";
import { api } from "@/lib/api";
import type { SupportRules, SupportRulesState } from "@/lib/types";

import { clock } from "./dashboard-format";

// Configuração > Regras (pedido do usuário, 2026-10-16): pontos do Ranking, metas do Feedback e metas dos
// Indicadores do Suporte, antes fixos no código. A validação de verdade é do servidor (`support_rules.py`: faixas em
// ordem, metas positivas...); a tela só edita, mostra o erro devolvido e permite restaurar o padrão.

const MAX_TMR_STEPS = 6;

function NumberInput({
  label,
  value,
  onChange,
  disabled,
  step = 1,
  hint,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  disabled: boolean;
  step?: number;
  hint?: string;
  suffix?: string;
}) {
  // Guarda o texto digitado: apagar o campo para digitar outro valor não pode virar 0 no meio da edição.
  const [text, setText] = useState(String(value));
  useEffect(() => {
    setText((current) => (Number(current.replace(",", ".")) === value ? current : String(value)));
  }, [value]);
  return (
    <label className="grid gap-1 text-xs font-medium text-slate-600">
      {label}
      <span className="flex items-center gap-1.5">
        <input
          type="number"
          inputMode="decimal"
          step={step}
          value={text}
          disabled={disabled}
          onChange={(event) => {
            setText(event.target.value);
            const parsed = Number(event.target.value.replace(",", "."));
            if (event.target.value.trim() !== "" && Number.isFinite(parsed)) onChange(parsed);
          }}
          className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-800 disabled:bg-slate-50 disabled:text-slate-500"
        />
        {suffix ? <span className="shrink-0 text-[11px] text-slate-500">{suffix}</span> : null}
      </span>
      {hint ? <span className="text-[10px] font-normal text-slate-500">{hint}</span> : null}
    </label>
  );
}

const dateBr = (iso: string) => iso.split("-").reverse().join("/");

export function RulesPanel({ canEdit }: { canEdit: boolean }) {
  const [state, setState] = useState<SupportRulesState | null>(null);
  const [draft, setDraft] = useState<SupportRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .supportRules()
      .then((result) => {
        if (cancelled) return;
        setState(result);
        setDraft(result.rules);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Falha ao carregar as regras.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const dirty = useMemo(() => (state && draft ? JSON.stringify(state.rules) !== JSON.stringify(draft) : false), [state, draft]);

  function update(change: (current: SupportRules) => SupportRules) {
    setDraft((current) => (current ? change(current) : current));
    setSaved(false);
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.updateSupportRules(draft);
      setState(result);
      setDraft(result.rules);
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar as regras.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div aria-busy className="h-64 animate-pulse rounded-2xl bg-slate-100" />;
  if (!state || !draft) {
    return (
      <div role="alert" className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
        <AlertTriangle className="h-4 w-4" aria-hidden /> {error ?? "Regras indisponíveis."}
      </div>
    );
  }

  const { ranking, feedback_goals: feedback, indicator_goals: indicators } = draft;
  const disabled = !canEdit || saving;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="text-sm text-slate-600">
          {state.updated_at ? (
            <>
              Última alteração em <strong>{dateBr(state.updated_at)}</strong>
              {state.updated_by ? <> por <strong>{state.updated_by}</strong></> : null}.
            </>
          ) : (
            "Nenhuma alteração ainda: valem os valores padrão."
          )}
          <p className="mt-0.5 text-[11px] text-slate-500">
            As mudanças valem a partir de hoje. O ranking de meses já fechados continua com a regra que estava em vigor neles.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => update(() => state.defaults)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Restaurar padrão
          </button>
          <button
            type="button"
            disabled={disabled || !dirty}
            onClick={() => void save()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Save className="h-3.5 w-3.5" aria-hidden /> {saving ? "Salvando..." : "Salvar regras"}
          </button>
        </div>
      </div>

      {!canEdit ? (
        <div role="status" className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 shadow-sm">
          Seu perfil só consulta as regras. Para alterar, é preciso a permissão de configuração do Suporte.
        </div>
      ) : null}
      {error ? (
        <div role="alert" className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 shadow-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden /> {error}
        </div>
      ) : null}
      {saved ? (
        <div role="status" className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 shadow-sm">
          <CheckCircle2 className="h-4 w-4" aria-hidden /> Regras salvas.
        </div>
      ) : null}

      <OverviewBlock eyebrow="Ranking" title="Pontuação do Ranking" subtitle="Valores em pontos (podem ser negativos). O ranking é mensal.">
        <div className="grid gap-5">
          <section>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-blue-600">Qualidade da avaliação</h3>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <NumberInput label="Nota a partir de (faixa positiva)" step={0.1} value={ranking.rating.good_min} disabled={disabled} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, rating: { ...c.ranking.rating, good_min: v } } }))} />
              <NumberInput label="Pontos da faixa positiva" value={ranking.rating.good_points} disabled={disabled} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, rating: { ...c.ranking.rating, good_points: v } } }))} />
              <NumberInput label="Nota até (faixa negativa)" step={0.1} value={ranking.rating.bad_max} disabled={disabled} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, rating: { ...c.ranking.rating, bad_max: v } } }))} hint="Entre as duas notas, 0 ponto." />
              <NumberInput label="Pontos da faixa negativa" value={ranking.rating.bad_points} disabled={disabled} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, rating: { ...c.ranking.rating, bad_points: v } } }))} />
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-blue-600">TMR (tempo médio de resposta)</h3>
            <div className="grid gap-2">
              {ranking.tmr_steps.map((step, index) => (
                <div key={index} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
                  <NumberInput
                    label={`Faixa ${index + 1}: até (segundos)`}
                    value={step.max_seconds}
                    disabled={disabled}
                    hint={`= ${clock(step.max_seconds)}`}
                    onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_steps: c.ranking.tmr_steps.map((item, i) => (i === index ? { ...item, max_seconds: v } : item)) } }))}
                  />
                  <NumberInput
                    label="Pontos"
                    value={step.points}
                    disabled={disabled}
                    onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_steps: c.ranking.tmr_steps.map((item, i) => (i === index ? { ...item, points: v } : item)) } }))}
                  />
                  <button
                    type="button"
                    aria-label={`Remover faixa ${index + 1}`}
                    disabled={disabled || ranking.tmr_steps.length <= 1}
                    onClick={() => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_steps: c.ranking.tmr_steps.filter((_, i) => i !== index) } }))}
                    className="mb-1 inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </div>
              ))}
              <button
                type="button"
                disabled={disabled || ranking.tmr_steps.length >= MAX_TMR_STEPS}
                onClick={() =>
                  update((c) => {
                    const last = c.ranking.tmr_steps[c.ranking.tmr_steps.length - 1];
                    return { ...c, ranking: { ...c.ranking, tmr_steps: [...c.ranking.tmr_steps, { max_seconds: last.max_seconds + 60, points: 0 }] } };
                  })
                }
                className="inline-flex w-fit items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden /> Adicionar faixa
              </button>
              <p className="text-[11px] text-slate-500">As faixas devem estar em ordem crescente de tempo.</p>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <NumberInput label="Penalidade começa acima de (segundos)" value={ranking.tmr_penalty.after_seconds} disabled={disabled} hint={`= ${clock(ranking.tmr_penalty.after_seconds)}; não pode ser menor que a última faixa`} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_penalty: { ...c.ranking.tmr_penalty, after_seconds: v } } }))} />
              <NumberInput label="A cada (segundos excedidos)" value={ranking.tmr_penalty.block_seconds} disabled={disabled} hint={`= ${clock(ranking.tmr_penalty.block_seconds)}`} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_penalty: { ...c.ranking.tmr_penalty, block_seconds: v } } }))} />
              <NumberInput label={ranking.tmr_penalty.flat ? "Pontos da penalidade (única)" : "Pontos por bloco excedido"} value={ranking.tmr_penalty.points} disabled={disabled} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_penalty: { ...c.ranking.tmr_penalty, points: v } } }))} />
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 sm:col-span-3">
                <input type="checkbox" checked={ranking.tmr_penalty.flat} disabled={disabled} onChange={(e) => update((c) => ({ ...c, ranking: { ...c.ranking, tmr_penalty: { ...c.ranking.tmr_penalty, flat: e.target.checked } } }))} />
                Penalidade única (desmarcado: repete a cada bloco de segundos excedidos)
              </label>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-blue-600">Ligações atendidas</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <NumberInput label="Meta e teto de ligações por semana" value={ranking.calls.week_target} disabled={disabled} hint="Semana parcial nas pontas do mês: proporcional aos dias." onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, calls: { ...c.ranking.calls, week_target: v } } }))} />
              <NumberInput label="Pontos por ligação atendida" value={ranking.calls.call_points} disabled={disabled} onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, calls: { ...c.ranking.calls, call_points: v } } }))} />
              <NumberInput label="Pontos por ligação que faltou para a meta" value={ranking.calls.missing_penalty} disabled={disabled} hint="Semana de domingo a sábado; só pontua depois de encerrada." onChange={(v) => update((c) => ({ ...c, ranking: { ...c.ranking, calls: { ...c.ranking.calls, missing_penalty: v } } }))} />
            </div>
          </section>
        </div>
      </OverviewBlock>

      <OverviewBlock eyebrow="Feedback" title="Metas individuais do Feedback" subtitle="Registros, atendimentos e ligações são metas SEMANAIS (a tela ajusta ao período escolhido). Avaliação e tempos não mudam com o período.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <NumberInput label="Registros Operacional (mínimo)" value={feedback.operational} disabled={disabled} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, operational: v } }))} />
          <NumberInput label="Registro Financeiro (mínimo)" value={feedback.financial} disabled={disabled} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, financial: v } }))} />
          <NumberInput label="O.S. Aberta a Campo (máximo)" value={feedback.field} disabled={disabled} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, field: v } }))} />
          <NumberInput label="Atendimento OPASuite (mínimo)" value={feedback.opa_attendances} disabled={disabled} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, opa_attendances: v } }))} />
          <NumberInput label="Chamadas Atendidas (mínimo)" value={feedback.calls} disabled={disabled} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, calls: v } }))} />
          <NumberInput label="Avaliação Individual (mínimo)" step={0.05} value={feedback.rating} disabled={disabled} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, rating: v } }))} />
          <NumberInput label="Tempo Médio de Atendimento (máximo, segundos)" value={feedback.tma_seconds} disabled={disabled} hint={`= ${clock(feedback.tma_seconds)}`} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, tma_seconds: v } }))} />
          <NumberInput label="Tempo Médio de Resposta (máximo, segundos)" value={feedback.tmr_seconds} disabled={disabled} hint={`= ${clock(feedback.tmr_seconds)}`} onChange={(v) => update((c) => ({ ...c, feedback_goals: { ...c.feedback_goals, tmr_seconds: v } }))} />
        </div>
      </OverviewBlock>

      <OverviewBlock eyebrow="Indicadores do Suporte" title="Metas dos Indicadores" subtitle="Metas dos cartões da aba Indicadores do Suporte. A margem de Atenção também vale no Feedback.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <NumberInput label="CSAT (mínimo)" step={0.1} value={indicators.csat} disabled={disabled} onChange={(v) => update((c) => ({ ...c, indicator_goals: { ...c.indicator_goals, csat: v } }))} />
          <NumberInput label="TMR (máximo, segundos)" value={indicators.tmr_seconds} disabled={disabled} hint={`= ${clock(indicators.tmr_seconds)}`} onChange={(v) => update((c) => ({ ...c, indicator_goals: { ...c.indicator_goals, tmr_seconds: v } }))} />
          <NumberInput label="TMA (máximo, segundos)" value={indicators.tma_seconds} disabled={disabled} hint={`= ${clock(indicators.tma_seconds)}`} onChange={(v) => update((c) => ({ ...c, indicator_goals: { ...c.indicator_goals, tma_seconds: v } }))} />
          <NumberInput label="Resolutividade (mínimo)" value={indicators.resolutivity_percent} disabled={disabled} suffix="%" onChange={(v) => update((c) => ({ ...c, indicator_goals: { ...c.indicator_goals, resolutivity_percent: v } }))} />
          <NumberInput label="Margem de Atenção" value={indicators.attention_margin_percent} disabled={disabled} suffix="%" hint="Até esta distância da meta o status é Atenção; além, Evoluir." onChange={(v) => update((c) => ({ ...c, indicator_goals: { ...c.indicator_goals, attention_margin_percent: v } }))} />
        </div>
      </OverviewBlock>
    </div>
  );
}
