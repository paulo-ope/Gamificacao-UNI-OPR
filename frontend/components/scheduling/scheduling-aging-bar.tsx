"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SchedulingBucket } from "@/lib/scheduling-api";

const BUCKET_COLORS: Record<string, string> = {
  hoje: "bg-blue-500",
  "1_2_dias": "bg-amber-400",
  "3_7_dias": "bg-orange-500",
  acima_7_dias: "bg-red-600",
};

// Versão compacta do envelhecimento da fila para o painel "Hoje" - uma barra segmentada em vez de
// 4 números soltos (pedido do usuário 2026-08-31). A tabela completa de O.S. continua na aba
// Rankings/Fila.
export function SchedulingAgingBar({
  buckets,
  onSelectBucket,
}: {
  buckets: SchedulingBucket[];
  onSelectBucket: (bucket: string, label: string, count: number) => void;
}) {
  const total = Math.max(1, buckets.reduce((sum, bucket) => sum + bucket.count, 0));

  return (
    <Card className="rounded-2xl border-slate-200 bg-white shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold text-slate-950">Envelhecimento da fila</CardTitle>
        <p className="text-xs text-slate-500">O.S. abertas ainda sem nenhum agendamento.</p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="flex h-5 gap-0.5 overflow-hidden rounded-md">
          {buckets.map((bucket) => (
            <button
              key={bucket.bucket}
              type="button"
              disabled={!bucket.count}
              title={`${bucket.label}: ${bucket.count}`}
              onClick={() => onSelectBucket(bucket.bucket, bucket.label, bucket.count)}
              style={{ width: `${(bucket.count / total) * 100}%` }}
              className={`min-w-[2px] ${BUCKET_COLORS[bucket.bucket] || "bg-slate-300"} enabled:cursor-pointer disabled:cursor-default`}
            />
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
          {buckets.map((bucket) => (
            <span key={bucket.bucket} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${BUCKET_COLORS[bucket.bucket] || "bg-slate-300"}`} />
              {bucket.label} <span className="font-semibold text-slate-900">{bucket.count}</span>
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
