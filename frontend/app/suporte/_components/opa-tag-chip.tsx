import type { SupportContactRadarTag } from "@/lib/types";

// Etiqueta do OPA na cor que ela tem lá. O cadastro da etiqueta traz `cor` (yellow, blue, red, gray, green, purple,
// orange). As classes precisam ser strings literais completas: o Tailwind não enxerga classe montada por interpolação.
const OPA_TAG_CLASS: Record<string, string> = {
  gray: "border-slate-300 bg-slate-100 text-slate-700",
  red: "border-red-200 bg-red-50 text-red-700",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  green: "border-emerald-200 bg-emerald-50 text-emerald-700",
  yellow: "border-amber-200 bg-amber-50 text-amber-800",
  purple: "border-violet-200 bg-violet-50 text-violet-700",
  orange: "border-orange-200 bg-orange-50 text-orange-800",
};

export function opaTagClass(color: string | null | undefined) {
  return OPA_TAG_CLASS[(color ?? "").toLowerCase()] ?? OPA_TAG_CLASS.gray;
}

export function OpaTagChip({ tag }: { tag: Pick<SupportContactRadarTag, "name" | "color"> & Partial<Pick<SupportContactRadarTag, "id" | "known">> }) {
  // Etiqueta sem cadastro mostra o id do OPA ao passar o mouse, para dar para achar o nome lá e cadastrá-lo.
  const title = tag.known === false && tag.id ? `${tag.name} (id ${tag.id})` : tag.name;
  return (
    <span className={`inline-flex max-w-[16rem] items-center rounded-md border px-2 py-0.5 text-[11px] font-medium leading-tight ${opaTagClass(tag.color)}`} title={title}>
      <span className="truncate">{tag.name}</span>
    </span>
  );
}

/** Chip neutro (cinza), como o OPA mostra o departamento ao lado das etiquetas. */
export function OpaDepartmentChip({ name }: { name: string }) {
  return <OpaTagChip tag={{ name, color: "gray" }} />;
}
