"use client";

import { useEffect, useState } from "react";

// Atrasa a propagação de um valor que muda a cada tecla (ex.: campo de busca) para não disparar
// uma chamada de API por caractere digitado - a auditoria refazia a busca inteira a cada letra,
// mostrando "carregando" o tempo todo enquanto o usuário digitava (achado real).
export function useDebouncedValue<T>(value: T, delayMs = 400): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs, value]);

  return debounced;
}
