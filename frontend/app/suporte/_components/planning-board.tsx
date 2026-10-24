"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import type { SupportPlanItem, SupportPlanStatus } from "@/lib/types";

import {
  KIND_LABEL,
  PRIORITY_LABEL,
  STATUS_LABEL,
  assigneesLabel,
  avatarColor,
  deadlineInfo,
  initials,
  progressPercent,
  type DeadlineTone,
} from "./planning-format";

// Quadro (kanban) da aba Especialista/Analista: cabeçalho colorido por coluna com contador, cartões
// compactos com barra de prazo e iniciais dos responsáveis. Só apresentação e arrastar: o atraso e o
// status de verdade vêm da API, e quem grava a mudança de coluna é o painel (`onMove`).

// Cores da marca UNI (tailwind: `uni-*`). Vermelho e âmbar ficam só como cor de alerta (bloqueado,
// atenção, atrasado), como no manual da marca.
const COLUMN_STYLE: Record<SupportPlanStatus, { header: string; body: string }> = {
  planned: { header: "bg-uni-ink text-white", body: "bg-uni-mist/70" },
  in_progress: { header: "bg-uni-royal text-white", body: "bg-uni-mist" },
  blocked: { header: "bg-red-600 text-white", body: "bg-red-50" },
  done: { header: "bg-uni-turquoise text-uni-ink", body: "bg-uni-turquoise/10" },
  canceled: { header: "bg-slate-400 text-white", body: "bg-slate-100" },
};

const BAR_COLOR: Record<DeadlineTone, string> = {
  ok: "bg-uni-turquoise",
  warn: "bg-amber-500",
  late: "bg-red-500",
  done: "bg-uni-turquoise",
  none: "bg-slate-300",
};

const BADGE_COLOR: Record<DeadlineTone, string> = {
  ok: "text-teal-700",
  warn: "text-amber-600",
  late: "text-red-600",
  done: "text-teal-700",
  none: "text-slate-400",
};

const PRIORITY_CHIP: Record<SupportPlanItem["priority"], string> = {
  low: "bg-slate-200 text-slate-700",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-500 text-white",
};

const KIND_CHIP: Record<SupportPlanItem["kind"], string> = {
  project: "bg-uni-midnight text-white",
  task: "bg-uni-mist text-uni-impact",
};

function Avatars({ item }: { item: SupportPlanItem }) {
  if (!item.assignees.length) return null;
  return (
    <div className="flex shrink-0 -space-x-1.5" aria-label={assigneesLabel(item)}>
      {item.assignees.slice(0, 3).map((person) => (
        <span
          key={person.id}
          title={person.name}
          className={`flex h-7 w-7 items-center justify-center rounded-full border-2 border-white text-[10px] font-bold ${avatarColor(person.id)}`}
        >
          {initials(person.name)}
        </span>
      ))}
    </div>
  );
}

type CardProps = {
  item: SupportPlanItem;
  draggable: boolean;
  onOpen: (id: number) => void;
  onDragStart: (item: SupportPlanItem) => void;
  onDragEnd: () => void;
};

function ItemCard({ item, draggable, onOpen, onDragStart, onDragEnd }: CardProps) {
  const deadline = deadlineInfo(item);
  const finished = item.status === "done" || item.status === "canceled";
  return (
    <li
      draggable={draggable}
      onDragStart={(event) => {
        event.stopPropagation();
        window.getSelection()?.removeAllRanges();
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(item.id));
        // A imagem do arrasto é só este cartão, nunca a coluna nem um texto selecionado.
        event.dataTransfer.setDragImage(event.currentTarget, 24, 24);
        onDragStart(item);
      }}
      onDragEnd={onDragEnd}
      className={draggable ? "cursor-grab select-none active:cursor-grabbing" : "select-none"}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => onOpen(item.id)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen(item.id);
          }
        }}
        className="grid w-full gap-2 rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:-translate-y-px hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-uni-royal"
      >
        <div className="flex items-start gap-2">
          <p className={`min-w-0 flex-1 text-[13px] font-medium leading-snug ${finished ? "text-slate-400 line-through" : "text-slate-900"}`}>{item.title}</p>
          <Avatars item={item} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${KIND_CHIP[item.kind]}`}>
            {KIND_LABEL[item.kind]}
          </span>
          {item.priority !== "low" ? (
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${PRIORITY_CHIP[item.priority]}`}>{PRIORITY_LABEL[item.priority]}</span>
          ) : null}
          {item.parent_title ? <span className="max-w-full truncate text-[11px] text-slate-500">{item.parent_title}</span> : null}
        </div>
        {item.kind === "project" && item.tasks_total ? (
          <p className="text-[11px] tabular-nums text-slate-500">
            {item.tasks_done} de {item.tasks_total} tarefas · {progressPercent(item)}%
          </p>
        ) : null}
        <div className="grid gap-1">
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <span className="truncate text-slate-500">{deadline.detail}</span>
            {deadline.badge ? <span className={`shrink-0 font-semibold ${BADGE_COLOR[deadline.tone]}`}>{deadline.badge}</span> : null}
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-200" role="presentation">
            <div className={`h-full rounded-full ${BAR_COLOR[deadline.tone]}`} style={{ width: `${deadline.percent}%` }} />
          </div>
        </div>
      </div>
    </li>
  );
}

type BoardProps = {
  items: SupportPlanItem[];
  columns: SupportPlanStatus[];
  canMove: boolean;
  onOpen: (id: number) => void;
  onMove: (item: SupportPlanItem, to: SupportPlanStatus) => void;
  /** Mostra "Criar tarefa…" no pé da coluna Planejado; null esconde (sem permissão de escrita). */
  onCreate: (() => void) | null;
};

export function PlanningBoard({ items, columns, canMove, onOpen, onMove, onCreate }: BoardProps) {
  const [dragging, setDragging] = useState<SupportPlanItem | null>(null);
  const [over, setOver] = useState<SupportPlanStatus | null>(null);
  return (
    <div className={`grid items-start gap-4 md:grid-cols-2 ${columns.length > 4 ? "xl:grid-cols-5" : "xl:grid-cols-4"}`}>
      {columns.map((status) => {
        const column = items.filter((item) => item.status === status);
        const accepting = dragging !== null && dragging.status !== status;
        const style = COLUMN_STYLE[status];
        return (
          <section
            key={status}
            aria-label={STATUS_LABEL[status]}
            onDragOver={(event) => {
              if (accepting) {
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                setOver(status);
              }
            }}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver((current) => (current === status ? null : current));
            }}
            onDrop={(event) => {
              event.preventDefault();
              const item = dragging;
              setDragging(null);
              setOver(null);
              if (item && item.status !== status) onMove(item, status);
            }}
            className={`select-none overflow-hidden rounded-xl shadow-sm transition ${style.body} ${over === status ? "ring-2 ring-uni-royal" : ""}`}
          >
            <h3 className={`flex items-center justify-between px-4 py-2.5 text-sm font-semibold ${style.header}`}>
              {STATUS_LABEL[status]}
              <span className="rounded-full bg-white/25 px-2 py-0.5 text-xs tabular-nums">{column.length}</span>
            </h3>
            <div className="grid gap-2.5 p-3">
              {column.length ? (
                <ul className="grid gap-2.5">
                  {column.map((item) => (
                    <ItemCard
                      key={item.id}
                      item={item}
                      draggable={canMove && !item.archived}
                      onOpen={onOpen}
                      onDragStart={setDragging}
                      onDragEnd={() => {
                        setDragging(null);
                        setOver(null);
                      }}
                    />
                  ))}
                </ul>
              ) : (
                <p className="py-6 text-center text-xs text-slate-400">{accepting ? "Solte aqui." : "Nada aqui."}</p>
              )}
              {status === "planned" && onCreate ? (
                <button
                  type="button"
                  onClick={onCreate}
                  className="flex items-center gap-1.5 rounded-md px-1 py-1.5 text-left text-sm text-slate-500 underline-offset-2 hover:text-uni-royal hover:underline"
                >
                  <Plus size={14} aria-hidden="true" />
                  Criar tarefa…
                </button>
              ) : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}
