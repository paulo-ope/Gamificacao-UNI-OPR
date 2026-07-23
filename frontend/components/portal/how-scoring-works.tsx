import { ArrowRight, CheckCircle2, CircleHelp, ClipboardList, ShieldCheck, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { PortalRules } from "@/lib/types";

type Props = { rules: PortalRules };

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

function text(item: Record<string, string | number | boolean | null>, key: string, fallback = "") {
  const value = item[key];
  return typeof value === "string" && value ? value : fallback;
}

function number(item: Record<string, string | number | boolean | null>, key: string) {
  return typeof item[key] === "number" ? item[key] as number : 0;
}

export function HowScoringWorks({ rules }: Props) {
  const subjects = rules.subjects
    .filter((item) => number(item, "points") > 0)
    .sort((left, right) => text(left, "os_subject").localeCompare(text(right, "os_subject"), "pt-BR"));
  const groups = rules.groups
    .filter((item) => number(item, "default_points") > 0)
    .sort((left, right) => number(right, "default_points") - number(left, "default_points"))
    .slice(0, 4);

  return (
    <section className="space-y-5">
      <div className="rounded-lg border bg-white p-4 sm:p-7">
        <Badge className="border-[#2d5fff]/25 bg-[#2d5fff]/10 text-[#0028f3]">Guia rápido</Badge>
        <h2 className="mt-3 text-xl font-semibold leading-tight sm:text-2xl">Como meus pontos entram no ranking?</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">Uma O.S. pontua pelo valor configurado para o seu assunto. Depois, o sistema verifica se alguma regra pode reduzir, anular ou ajustar esse valor.</p>
        <div className="mt-6 grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] lg:items-stretch">
          <div className="rounded-lg border border-[#2d5fff]/25 bg-[#2d5fff]/10 p-4"><ClipboardList className="h-5 w-5 text-[#0028f3]" /><p className="mt-3 font-semibold">1. A O.S. é concluída</p><p className="mt-1 text-sm text-slate-600">A O.S. entra no fechamento do período.</p></div>
          <ArrowRight className="m-auto hidden h-5 w-5 text-slate-400 lg:block" />
          <div className="rounded-lg border border-slate-200 p-4"><CircleHelp className="h-5 w-5 text-slate-600" /><p className="mt-3 font-semibold">2. O assunto tem valor configurado</p><p className="mt-1 text-sm text-slate-600">Cada assunto paga exatamente o valor mostrado abaixo.</p></div>
          <ArrowRight className="m-auto hidden h-5 w-5 text-slate-400 lg:block" />
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4"><ShieldCheck className="h-5 w-5 text-amber-800" /><p className="mt-3 font-semibold">3. As regras são verificadas</p><p className="mt-1 text-sm text-slate-600">Garantia, recorrência, SLA ou diagnóstico podem alterar o ponto.</p></div>
          <ArrowRight className="m-auto hidden h-5 w-5 text-slate-400 lg:block" />
          <div className="rounded-lg border border-[#27d9bf]/40 bg-[#27d9bf]/10 p-4"><Sparkles className="h-5 w-5 text-[#0028f3]" /><p className="mt-3 font-semibold">4. O ponto entra no ranking</p><p className="mt-1 text-sm text-slate-600">O resultado passa pela saúde operacional e compõe seu fechamento.</p></div>
        </div>
      </div>

      <section className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="rounded-lg border bg-white p-4 sm:p-5">
          <h3 className="font-semibold">O que normalmente faz um ponto não entrar?</h3>
          <p className="mt-1 text-sm text-slate-600">Não é um desconto sem explicação. Existe uma regra ligada à O.S.</p>
          <div className="mt-5 space-y-3">
            <div className="flex gap-3"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" /><div><p className="text-sm font-medium">Recorrência ou retorno</p><p className="text-xs text-slate-500">Quando a O.S. se encaixa em uma regra de retorno do mesmo atendimento.</p></div></div>
            <div className="flex gap-3"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" /><div><p className="text-sm font-medium">Garantia, SLA ou diagnóstico</p><p className="text-xs text-slate-500">A regra pode reduzir ou anular o ponto, sempre visível na sua O.S.</p></div></div>
            <div className="flex gap-3"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" /><div><p className="text-sm font-medium">Assunto sem regra cadastrada</p><p className="text-xs text-slate-500">A O.S. fica marcada para acompanhamento, não some sem explicação.</p></div></div>
          </div>
        </div>
        <div className="overflow-hidden rounded-lg border bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4 sm:p-5"><div className="min-w-0"><h3 className="font-semibold">O que está configurado para pagar</h3><p className="mt-1 text-sm text-slate-600">Valores atuais por assunto, antes de qualquer regra de desconto ou anulação.</p></div><Badge className="border-[#2d5fff]/25 bg-[#2d5fff]/10 text-[#0028f3]">{subjects.length} assuntos</Badge></div>
          <div className="divide-y">
            {subjects.map((subject) => <div key={text(subject, "id", text(subject, "os_subject"))} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center sm:px-5"><div className="min-w-0"><p className="font-medium">{text(subject, "os_subject", "Assunto")}</p><p className="mt-1 text-xs text-slate-500">{text(subject, "group_name", "Grupo configurado")} · {text(subject, "point_source", "Valor configurado")}</p></div><div className="sm:text-right"><p className="text-lg font-semibold text-[#0028f3]">Paga {numberFormat.format(number(subject, "points"))} pts</p><p className="text-xs text-slate-500">por O.S. concluída</p></div></div>)}
            {!subjects.length ? <p className="p-4 text-sm text-slate-500 sm:p-5">Nenhum assunto com pontuação configurada.</p> : null}
          </div>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4 sm:p-5">
        <h3 className="font-semibold">Valores padrão dos grupos</h3>
        <p className="mt-1 text-sm text-slate-600">Este é o valor que o grupo paga quando o assunto não tem um valor específico configurado.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {groups.map((group) => <div key={text(group, "id", text(group, "name"))} className="border-l-4 border-[#2d5fff] bg-[#2d5fff]/5 p-4"><p className="text-sm font-medium">{text(group, "name", "Grupo")}</p><p className="mt-1 text-xs text-slate-500">{text(group, "description", "Pontuação conforme assunto")}</p><p className="mt-3 font-semibold text-[#0028f3]">Paga {numberFormat.format(number(group, "default_points"))} pts</p><p className="mt-1 text-xs text-slate-500">valor padrão do grupo</p></div>)}
          {!groups.length ? <p className="text-sm text-slate-500">Nenhum grupo ativo configurado.</p> : null}
        </div>
      </section>
    </section>
  );
}
