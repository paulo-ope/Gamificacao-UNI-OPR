import { GitBranch, Stethoscope } from "lucide-react";

import { Badge } from "@/components/ui/badge";

type OrderAuditTagData = {
  diagnosis_action_type: string | null;
  diagnosis_penalty_reason: string | null;
  recurrence_related_os_code: string | null;
  recurrence_days_between: number | null;
};

type Props = {
  order: OrderAuditTagData;
};

export function OrderAuditTags({ order }: Props) {
  const isDiagnosisAnnulled = order.diagnosis_action_type === "cancel_points";
  const hasRecurrence = Boolean(order.recurrence_related_os_code);

  if (!isDiagnosisAnnulled && !hasRecurrence) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {isDiagnosisAnnulled ? (
        <Badge className="border-rose-200 bg-rose-50 text-rose-800">
          <Stethoscope className="h-3.5 w-3.5" />
          Anulada por diagnóstico
        </Badge>
      ) : null}
      {hasRecurrence ? (
        <Badge className="border-amber-200 bg-amber-50 text-amber-900">
          <GitBranch className="h-3.5 w-3.5" />
          Reincidência: O.S. posterior {order.recurrence_related_os_code}
        </Badge>
      ) : null}
      {isDiagnosisAnnulled && order.diagnosis_penalty_reason ? (
        <p className="basis-full text-xs text-rose-800">{order.diagnosis_penalty_reason}</p>
      ) : null}
      {hasRecurrence && order.recurrence_days_between !== null ? (
        <p className="basis-full text-xs text-amber-900">A O.S. posterior foi concluída {order.recurrence_days_between} dias depois.</p>
      ) : null}
    </div>
  );
}
