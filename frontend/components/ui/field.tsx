"use client";

import { createContext, useContext, useId, type HTMLAttributes } from "react";

const FieldIdContext = createContext<string | undefined>(undefined);

/** Associates a field's visible Label and control without repeated or hardcoded IDs. */
export function Field({ children, ...props }: HTMLAttributes<HTMLDivElement>) {
  const id = useId();
  return <FieldIdContext.Provider value={id}><div {...props}>{children}</div></FieldIdContext.Provider>;
}

export function useFieldControlId(explicitId?: string) {
  const fieldId = useContext(FieldIdContext);
  return explicitId ?? fieldId;
}
