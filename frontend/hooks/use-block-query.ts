"use client";

import { useEffect, useRef, useState, type DependencyList } from "react";

export type BlockQueryState<T> = {
  data: T | null;
  /** Primeira carga em andamento - recargas com dado na tela não voltam a `true`. */
  loading: boolean;
  /** Recarga em andamento com dado antigo ainda na tela. */
  refreshing: boolean;
  error: string | null;
};

/**
 * Um bloco de dashboard = uma fonte assíncrona + quatro estados. Este hook é esse par.
 *
 * Existe porque a Visão Geral repetia seis vezes o trio `useState(dado) / useState(status) /
 * useEffect(carregar)` - o começo do "empilhar código" que se quer evitar. Regras que ele
 * garante e que cada cópia manual esquecia em algum lugar:
 * - resposta atrasada de um filtro antigo nunca sobrescreve a do filtro novo (`active`);
 * - recarregar com dado na tela não pisca esqueleto (`refreshing` em vez de `loading`);
 * - `enabled: false` (sem permissão, sem filtro ainda) não dispara nada e limpa o estado.
 *
 * `load` recebe um `AbortSignal` para quem quiser cancelar de verdade; quem não usa, ignora.
 */
export function useBlockQuery<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
  options: { enabled?: boolean; fallbackError?: string } = {},
): BlockQueryState<T> {
  const enabled = options.enabled ?? true;
  const fallbackError = options.fallbackError ?? "Não foi possível carregar este indicador.";
  const [state, setState] = useState<BlockQueryState<T>>({ data: null, loading: enabled, refreshing: false, error: null });
  const hasDataRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      hasDataRef.current = false;
      setState({ data: null, loading: false, refreshing: false, error: null });
      return;
    }
    let active = true;
    const controller = new AbortController();
    setState((current) => ({
      ...current,
      loading: !hasDataRef.current,
      refreshing: hasDataRef.current,
      error: null,
    }));
    load(controller.signal)
      .then((data) => {
        if (!active) return;
        hasDataRef.current = true;
        setState({ data, loading: false, refreshing: false, error: null });
      })
      .catch((reason: unknown) => {
        if (!active || controller.signal.aborted) return;
        hasDataRef.current = false;
        setState({
          data: null,
          loading: false,
          refreshing: false,
          error: reason instanceof Error && reason.message ? reason.message : fallbackError,
        });
      });
    return () => {
      active = false;
      controller.abort();
    };
    // `load` é recriada a cada render por quem chama; as dependências reais são `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return state;
}
