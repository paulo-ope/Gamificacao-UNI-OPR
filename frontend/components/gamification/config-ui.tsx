"use client";

import * as Dialog from "@radix-ui/react-dialog";
import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronDown, MoreHorizontal, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { HTMLAttributes, ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Command, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Input, type InputProps } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { normalizeRegional, regionalName } from "@/lib/regional";
import { cn } from "@/lib/utils";

export const configSectionClass = "rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)]";
export const configCardClass = "rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]";
export const configSoftCardClass = "rounded-2xl border border-slate-200 bg-slate-50 p-4";
export const configSelectClass = "h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function AppInput({ className, ...props }: InputProps) {
  return <Input className={cn("h-11 rounded-xl", className)} {...props} />;
}

export function AppSwitch({
  checked,
  onCheckedChange,
  label,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2 py-1 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"
      )}
    >
      <span
        className={cn(
          "relative flex h-5 w-9 items-center rounded-full transition",
          checked ? "bg-emerald-500" : "bg-slate-300"
        )}
      >
        <span
          className={cn(
            "absolute h-4 w-4 rounded-full bg-white shadow-sm transition",
            checked ? "left-4" : "left-0.5"
          )}
        />
      </span>
      <span>{label ?? (checked ? "Ativo" : "Inativo")}</span>
    </button>
  );
}

// Reexportado do local compartilhado (components/ui/checkbox.tsx) - outros módulos (operações,
// admin) importam de lá diretamente; mantido aqui também para não quebrar imports existentes.
export { AppCheckbox } from "@/components/ui/checkbox";

export function AppCombobox({
  value,
  onChange,
  options,
  placeholder,
  searchPlaceholder = "Pesquisar...",
  emptyLabel = "Nenhuma opção encontrada.",
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string; description?: string }>;
  placeholder: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
  ariaLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const selected = options.find((option) => option.value === value) ?? null;
  const filtered = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    return options.filter((option) => [option.label, option.description ?? ""].join(" ").toLowerCase().includes(normalized));
  }, [options, search]);

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setSearch("");
      }}
    >
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={ariaLabel ?? placeholder}
          className={cn(configSelectClass, "flex items-center justify-between gap-2 text-left", className)}
        >
          <span className={selected ? "truncate text-slate-900" : "truncate text-slate-500"}>{selected?.label ?? placeholder}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={8}
          avoidCollisions
          collisionPadding={12}
          // pointerEvents: "auto" é essencial quando este combobox é usado dentro de um AppModal/
          // AppDrawer: o Radix Dialog (base do Sheet/Dialog) trava o <body> inteiro com
          // `pointer-events: none` enquanto está aberto (mecanismo de scroll-lock via
          // react-remove-scroll, visto ao vivo: <body data-scroll-locked="1" style="pointer-events:
          // none">), e só reativa pointer-events explicitamente no PRÓPRIO conteúdo do Dialog. Este
          // Popover vive num portal SEPARADO (irmão do Dialog no body, não descendente dele), então
          // herda o `none` do body e fica com clique E scroll bloqueados por dentro - mesmo estando
          // visualmente por cima (z-index não tem nenhum efeito sobre isso). Achado real: usuário
          // reportou que nem clicar nem rolar a lista funcionava dentro do drawer de colaborador.
          style={{ width: "var(--radix-popover-trigger-width)", pointerEvents: "auto" }}
          // z-[90]: precisa ficar ACIMA de qualquer modal/drawer do app - AppModal usa z-[80], o
          // Dialog/Sheet do shadcn usam z-[70] (ver dialog.tsx/sheet.tsx). Com z-50 (padrão anterior),
          // o popover deste combobox renderizava visualmente atrás do modal/drawer quando usado
          // dentro de um (mesmo empilhamento via portal no body).
          className="z-[90] flex max-h-[min(24rem,var(--radix-popover-content-available-height))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_18px_48px_rgba(15,23,42,0.14)]"
        >
          <Command className="flex min-h-0 flex-1 flex-col border-0 shadow-none">
            <CommandInput value={search} onChange={(event) => setSearch(event.target.value)} placeholder={searchPlaceholder} className="h-10 shrink-0" />
            {/*
              onWheel manual: o Radix Dialog/Sheet (AppModal/AppDrawer) usa react-remove-scroll, que
              registra um `shards` allowlist só com o próprio contentRef do Dialog e bloqueia o wheel
              de qualquer outro alvo via `document.addEventListener('wheel', ..., {passive:false})` +
              `preventDefault()`. O popover deste combobox vive num portal separado (irmão do conteúdo
              do Dialog, não descendente), então nunca entra nesse allowlist e o scroll nativo desta
              lista fica bloqueado mesmo com o fix de pointer-events acima (aquele é CSS; este
              bloqueio é feito em JS). stopPropagation() não resolve, pois o listener já roda antes de
              qualquer handler nosso. Por isso movemos scrollTop manualmente aqui - isso não é afetado
              pelo preventDefault do listener alheio, que só suprime o scroll NATIVO do navegador.
            */}
            <CommandList
              className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto"
              onWheel={(event) => {
                event.currentTarget.scrollTop += event.deltaY;
              }}
            >
              {filtered.map((option) => {
                const checked = option.value === value;
                return (
                  <CommandItem
                    key={option.value}
                    onClick={() => {
                      onChange(option.value);
                      setOpen(false);
                      setSearch("");
                    }}
                    className="flex items-start justify-between rounded-xl border border-transparent px-3 py-2.5 hover:border-slate-200 hover:bg-slate-50"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-slate-800">{option.label}</div>
                      {option.description ? <div className="mt-0.5 text-xs text-slate-500">{option.description}</div> : null}
                    </div>
                    <span
                      className={cn(
                        "ml-3 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        checked ? "border-uni-royal bg-uni-royal text-white" : "border-slate-300 bg-white text-transparent"
                      )}
                    >
                      <Check className="h-3 w-3" />
                    </span>
                  </CommandItem>
                );
              })}
              {filtered.length === 0 ? <div className="px-3 py-6 text-center text-sm text-slate-500">{emptyLabel}</div> : null}
            </CommandList>
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function AppMultiSelect({
  values,
  onChange,
  options,
  placeholder,
  searchPlaceholder = "Pesquisar...",
  emptyLabel = "Nenhuma opção encontrada.",
  ariaLabel,
  className,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  options: Array<{ value: string; label: string }>;
  placeholder: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
  ariaLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    return options.filter((option) => option.label.toLowerCase().includes(normalized));
  }, [options, search]);

  const summary =
    values.length === 0
      ? placeholder
      : values.length === 1
        ? options.find((option) => option.value === values[0])?.label ?? placeholder
        : `${values.length} selecionadas`;

  function toggle(value: string) {
    onChange(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setSearch("");
      }}
    >
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={ariaLabel ?? placeholder}
          className={cn(configSelectClass, "flex items-center justify-between gap-2 text-left", className)}
        >
          <span className={values.length ? "truncate text-slate-900" : "truncate text-slate-500"}>{summary}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={8}
          avoidCollisions
          collisionPadding={12}
          style={{ width: "var(--radix-popover-trigger-width)", pointerEvents: "auto" }}
          className="z-[90] flex max-h-[min(24rem,var(--radix-popover-content-available-height))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_18px_48px_rgba(15,23,42,0.14)]"
        >
          <Command className="flex min-h-0 flex-1 flex-col border-0 shadow-none">
            <CommandInput value={search} onChange={(event) => setSearch(event.target.value)} placeholder={searchPlaceholder} className="h-10 shrink-0" />
            <CommandList
              className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto"
              onWheel={(event) => {
                event.currentTarget.scrollTop += event.deltaY;
              }}
            >
              {filtered.map((option) => {
                const checked = values.includes(option.value);
                return (
                  <CommandItem
                    key={option.value}
                    onClick={() => toggle(option.value)}
                    className="flex items-center justify-between rounded-xl border border-transparent px-3 py-2.5 hover:border-slate-200 hover:bg-slate-50"
                  >
                    <span className="truncate text-sm font-medium text-slate-800">{option.label}</span>
                    <span
                      className={cn(
                        "ml-3 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        checked ? "border-[var(--uni-royal)] bg-[var(--uni-royal)] text-white" : "border-slate-300 bg-white text-transparent"
                      )}
                    >
                      <Check className="h-3 w-3" />
                    </span>
                  </CommandItem>
                );
              })}
              {filtered.length === 0 ? <div className="px-3 py-6 text-center text-sm text-slate-500">{emptyLabel}</div> : null}
            </CommandList>
            {values.length > 0 ? (
              <div className="mt-2 flex shrink-0 items-center justify-between border-t border-slate-100 pt-2">
                <span className="text-xs text-slate-500">
                  {values.length} selecionada{values.length > 1 ? "s" : ""}
                </span>
                <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => onChange([])}>
                  Limpar
                </Button>
              </div>
            ) : null}
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function RowActionMenu({
  items,
  ariaLabel = "Ações da linha",
}: {
  items: Array<{ label: string; onSelect: () => void; tone?: "default" | "danger" }>;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", handleOutsideClick);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("mousedown", handleOutsideClick);
      window.removeEventListener("keydown", handleEscape);
    };
  }, []);

  return (
    <div className="relative" ref={ref}>
      <Button type="button" variant="outline" size="icon" aria-label={ariaLabel} onClick={() => setOpen((current) => !current)}>
        <MoreHorizontal className="h-4 w-4" />
      </Button>
      {open ? (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] z-50 min-w-[180px] rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_18px_48px_rgba(15,23,42,0.14)]">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              className={cn(
                "flex w-full rounded-xl px-3 py-2 text-left text-sm transition hover:bg-slate-50",
                item.tone === "danger" ? "text-red-700 hover:bg-red-50" : "text-slate-700"
              )}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-header">
      <div>
        <h3 className="panel-title">{title}</h3>
        <p className="panel-subtitle">{description}</p>
      </div>
      {action ? <div className="flex flex-wrap gap-2">{action}</div> : null}
    </div>
  );
}

export function StepHeroCard({
  step,
  title,
  description,
  accent = "teal",
}: {
  step: string;
  title: string;
  description: string;
  accent?: "teal" | "blue" | "amber";
}) {
  const accentClass =
    accent === "blue"
      ? "border-blue-200 bg-blue-50 text-uni-royal"
      : accent === "amber"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-blue-200 bg-blue-50 text-uni-royal";

  return (
    <div className={cn(configCardClass, "flex items-start gap-4")}>
      <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border text-lg font-semibold", accentClass)}>
        {step}
      </div>
      <div>
        <div className="text-lg font-semibold text-slate-950">{title}</div>
        <div className="mt-1 text-sm text-slate-500">{description}</div>
      </div>
    </div>
  );
}

export function GuidanceCard({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className={configCardClass}>
      <div className="text-sm font-semibold text-slate-950">{title}</div>
      <div className="mt-1 text-sm text-slate-500">{description}</div>
    </div>
  );
}

export function FilterToolbar({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-wrap gap-3 border-b border-slate-200 bg-slate-50/80 px-5 py-4", className)} {...props} />;
}

export function ToolbarSearch({
  value,
  onChange,
  placeholder,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <div className={cn("relative min-w-[280px] flex-1", className)}>
      <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
      <AppInput value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="pl-9" />
    </div>
  );
}

export function ToolbarCount({ children }: { children: ReactNode }) {
  return <div className="ml-auto flex items-center text-xs font-medium text-slate-500">{children}</div>;
}

export function DataTableFrame({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("overflow-hidden rounded-b-[24px] border-t border-slate-200", className)} {...props} />;
}

export function StatusBadge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "success" | "warning" | "danger" | "info" | "neutral";
  children: ReactNode;
  className?: string;
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : tone === "danger"
          ? "border-red-200 bg-red-50 text-red-700"
          : tone === "info"
            ? "border-blue-200 bg-blue-50 text-uni-royal"
            : "border-slate-200 bg-slate-50 text-slate-700";
  return <Badge className={cn(toneClass, className)}>{children}</Badge>;
}

// Substitui as versões duplicadas de "iniciais em círculo colorido" que existiam soltas em
// audit-panel.tsx e point-balance-panel.tsx (com tamanho/cor diferentes entre si) por um único
// componente compartilhado. Mostra a foto (se `photoUrl` vier preenchido - já como object URL de
// um blob buscado com autenticação, não uma URL pública) e cai pras iniciais coloridas (hash simples
// do nome, pra variar a cor em vez do tom fixo único que os dois lugares antigos usavam).
const AVATAR_COLOR_CLASSES = [
  "bg-uni-royal",
  "bg-sky-600",
  "bg-violet-600",
  "bg-rose-600",
  "bg-amber-600",
  "bg-emerald-600",
  "bg-indigo-600",
];

const AVATAR_SIZE_CLASSES: Record<"sm" | "md" | "lg", string> = {
  sm: "h-6 w-6 text-[10px]",
  md: "h-8 w-8 text-[11px]",
  lg: "h-11 w-11 text-sm",
};

function initialsFromName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function colorClassForName(name: string) {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) >>> 0;
  }
  return AVATAR_COLOR_CLASSES[hash % AVATAR_COLOR_CLASSES.length];
}

export function Avatar({
  name,
  photoUrl,
  size = "md",
  className,
}: {
  name: string;
  photoUrl?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizeClass = AVATAR_SIZE_CLASSES[size];
  if (photoUrl) {
    return <img src={photoUrl} alt={name} className={cn("shrink-0 rounded-full object-cover", sizeClass, className)} />;
  }
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold text-white",
        sizeClass,
        colorClassForName(name || "?"),
        className
      )}
    >
      {initialsFromName(name || "?")}
    </div>
  );
}

export function uniqueRegionals(values: string[]) {
  return Array.from(new Set(values.map((item) => normalizeRegional(item)).filter(Boolean)));
}

export function RegionalMultiSelect({
  options,
  selected,
  onChange,
  disabled = false,
}: {
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return options.filter((item) => regionalName(item).toLowerCase().includes(normalizedQuery));
  }, [options, query]);

  const toggle = (regional: string) => {
    if (selected.includes(regional)) {
      onChange(selected.filter((item) => item !== regional));
      return;
    }
    onChange([...selected, regional]);
  };

  return (
    <div className="grid gap-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "flex min-h-11 items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 text-left shadow-sm transition",
          disabled ? "cursor-not-allowed bg-slate-100 text-slate-400" : "hover:border-slate-300 hover:bg-slate-50",
        )}
      >
        <div className="min-w-0">
          <div className="text-sm font-medium text-slate-900">
            {selected.length > 0
              ? `${selected.length} ${selected.length === 1 ? "filial selecionada" : "filiais selecionadas"}`
              : "Selecionar filiais"}
          </div>
          <div className="truncate text-xs text-slate-500">
            {selected.length > 0
              ? selected.slice(0, 3).map((item) => regionalName(item)).join(", ")
              : "Busque e marque as filiais que entram no escopo."}
          </div>
        </div>
        <Badge className="border-slate-200 bg-slate-50 text-slate-600">{selected.length}</Badge>
      </button>

      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {selected.map((regional) => (
            <span
              key={regional}
              className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700"
            >
              {regionalName(regional)}
              {!disabled ? (
                <button type="button" onClick={() => toggle(regional)} className="text-sky-500 transition hover:text-sky-700">
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}

      {open ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_18px_48px_rgba(15,23,42,0.12)]">
          <Command className="border-0 shadow-none">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
              <CommandInput
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Buscar filial..."
                className="pl-9"
              />
            </div>
            <CommandList className="mt-3 max-h-64 space-y-1">
              {filteredOptions.map((regional) => {
                const checked = selected.includes(regional);
                return (
                  <CommandItem
                    key={regional}
                    onClick={() => toggle(regional)}
                    className="flex items-center justify-between rounded-xl border border-transparent px-3 py-2.5 hover:border-slate-200 hover:bg-slate-50"
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          "flex h-4 w-4 items-center justify-center rounded border",
                          checked ? "border-uni-royal bg-uni-royal text-white" : "border-slate-300 bg-white text-transparent",
                        )}
                      >
                        <Check className="h-3 w-3" />
                      </span>
                      <span className="text-sm text-slate-700">{regionalName(regional)}</span>
                    </div>
                  </CommandItem>
                );
              })}
              {filteredOptions.length === 0 ? (
                <div className="px-3 py-6 text-center text-sm text-slate-500">Nenhuma filial encontrada para a busca.</div>
              ) : null}
            </CommandList>
          </Command>
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
            <button
              type="button"
              className="text-sm font-medium text-slate-500 transition hover:text-slate-800"
              onClick={() => onChange([])}
            >
              Limpar seleção
            </button>
            <Button type="button" size="sm" variant="secondary" onClick={() => setOpen(false)}>
              Fechar
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center">
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-sm text-slate-500">{description}</div>
    </div>
  );
}

export function LoadingState({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">{children}</div>;
}

export function ErrorState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-8 text-center">
      <div className="text-sm font-semibold text-red-900">{title}</div>
      <div className="mt-1 text-sm text-red-700">{description}</div>
    </div>
  );
}

export function AppModal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  const sizeClass = size === "sm" ? "sm:max-w-md" : size === "lg" ? "sm:max-w-3xl" : "sm:max-w-xl";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/35" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[80] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-[24px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.2)] outline-none focus-visible:ring-2 focus-visible:ring-ring",
            sizeClass
          )}
        >
          <div className="border-b px-6 py-5 pr-14">
            <Dialog.Title className="text-lg font-semibold text-slate-950">{title}</Dialog.Title>
            {description ? <Dialog.Description className="mt-1 text-sm text-slate-500">{description}</Dialog.Description> : null}
          </div>
          <div className="max-h-[70vh] overflow-auto px-6 py-5">{children}</div>
          {footer ? <div className="flex flex-wrap justify-end gap-2 border-t px-6 py-4">{footer}</div> : null}
          <Dialog.Close className="absolute right-4 top-4 rounded-md p-1 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <X className="h-5 w-5" />
            <span className="sr-only">Fechar</span>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function AppDrawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  widthClassName = "sm:max-w-3xl",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  widthClassName?: string;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className={widthClassName}>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        <div className="grid gap-5 overflow-y-auto px-6 py-6">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
