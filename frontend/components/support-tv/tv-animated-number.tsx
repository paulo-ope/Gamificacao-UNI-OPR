"use client";

import { useEffect, useRef, useState } from "react";

const DURATION_MS = 700;

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Número que desliza até o novo valor em vez de trocar de repente: numa TV a mudança fica perceptível
// sem piscar nada. Respeita `prefers-reduced-motion` (aí troca direto). Valor ausente (`null`) nunca
// vira 0 - mostra o traço.
export function AnimatedNumber({ value, format }: { value: number | null; format: (value: number) => string }) {
  const [display, setDisplay] = useState<number | null>(value);
  const shown = useRef<number | null>(value);

  useEffect(() => {
    if (value === null || shown.current === null || prefersReducedMotion() || shown.current === value) {
      shown.current = value;
      setDisplay(value);
      return;
    }
    const from = shown.current;
    const startedAt = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / DURATION_MS);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = from + (value - from) * eased;
      shown.current = next;
      setDisplay(next);
      if (progress < 1) frame = requestAnimationFrame(step);
      else {
        shown.current = value;
        setDisplay(value);
      }
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <>{display === null ? "—" : format(display)}</>;
}
