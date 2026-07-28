"use client";

import type { OperationOrder } from "@/lib/operations-api";

function TextPanel({
  title,
  value,
}: {
  title: string;
  value: string | null;
}) {
  if (!value?.trim()) return null;
  return (
    <details
      className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 open:bg-white"
      onClick={(event) => event.stopPropagation()}
    >
      <summary className="cursor-pointer select-none font-semibold text-slate-800">
        {title}
      </summary>
      <p className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap break-words leading-5 text-slate-700">
        {value}
      </p>
    </details>
  );
}

export function OperationsOrderTextPanels({
  order,
}: {
  order: Pick<OperationOrder, "service_address" | "service_description" | "technical_report">;
}) {
  if (!order.service_address && !order.service_description && !order.technical_report) return null;
  return (
    <div className="mt-3 grid gap-2">
      <TextPanel title="Endereço da O.S." value={order.service_address} />
      <TextPanel title="Descrição do serviço" value={order.service_description} />
      <TextPanel title="Relato técnico" value={order.technical_report} />
    </div>
  );
}
