"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { isWithinViewport } from "@/lib/viewport";

/**
 * Só renderiza os filhos quando o bloco entra (ou está prestes a entrar) na área visível.
 *
 * Feito para os gráficos abaixo da dobra: cada componente de gráfico carrega o ECharts sob
 * demanda, mas "sob demanda" começa na primeira renderização - então um gráfico no fim da página
 * puxava ~1 MB de biblioteca junto com o topo da tela. Adiar até a rolagem deixa o topo pronto
 * primeiro.
 *
 * Dois caminhos decidem "ficou visível", e qualquer um deles basta:
 * - `IntersectionObserver`, o normal;
 * - a geometria (`getBoundingClientRect` a cada rolagem/redimensionamento, limitada a um quadro
 *   por `requestAnimationFrame`). Existe porque há ambientes em que o observer nunca dispara -
 *   confirmado em 2026-09-03 num navegador embutido, com um observer criado à mão sobre um
 *   elemento comprovadamente dentro da viewport. Sem esta segunda via, o bloco ficaria em
 *   esqueleto para sempre. A regra é "nunca sumir": sem `IntersectionObserver` algum, renderiza
 *   direto.
 */
export function DeferUntilVisible({
  children,
  placeholder,
  rootMargin = 240,
}: {
  children: ReactNode;
  placeholder?: ReactNode;
  /** Antecedência, em pixels, para começar a renderizar antes de o bloco aparecer de fato. */
  rootMargin?: number;
}) {
  const anchorRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (visible) return;
    const element = anchorRef.current;
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    const reveal = () => setVisible(true);

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) reveal();
      },
      { rootMargin: `${rootMargin}px` },
    );
    observer.observe(element);

    // Segunda via: geometria. `scroll` em modo captura pega a rolagem de QUALQUER contêiner (a
    // casca do ecossistema rola pelo `body`, não pela janela), e o rAF evita medir mais de uma
    // vez por quadro.
    let frame = 0;
    const measure = () => {
      frame = 0;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      if (isWithinViewport(element.getBoundingClientRect(), viewportHeight, rootMargin)) reveal();
    };
    const schedule = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(measure);
    };
    document.addEventListener("scroll", schedule, { capture: true, passive: true });
    window.addEventListener("resize", schedule, { passive: true });
    schedule();

    return () => {
      observer.disconnect();
      document.removeEventListener("scroll", schedule, { capture: true });
      window.removeEventListener("resize", schedule);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [visible, rootMargin]);

  return (
    <div ref={anchorRef}>
      {visible
        ? children
        : (placeholder ?? (
            <div className="h-[320px] animate-pulse rounded-xl bg-slate-100" aria-label="Carregando gráficos" aria-busy="true" />
          ))}
    </div>
  );
}
