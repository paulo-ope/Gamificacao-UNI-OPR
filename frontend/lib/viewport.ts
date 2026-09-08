/**
 * Decide se um retângulo (coordenadas relativas à viewport, como `getBoundingClientRect`) está
 * dentro da área visível ou a `margin` pixels dela.
 *
 * Extraída de `components/ui/defer-until-visible.tsx` para ser testável em ambiente `node` (a
 * suíte do frontend não tem DOM): é a regra que decide "renderizar agora" quando o
 * `IntersectionObserver` não está disponível ou não dispara. Uma viewport de altura zero nunca
 * revela nada - é o estado de aba oculta/minimizada, e revelar ali só desperdiçaria o download.
 */
export function isWithinViewport(
  rect: { top: number; bottom: number },
  viewportHeight: number,
  margin = 0,
): boolean {
  if (viewportHeight <= 0) return false;
  return rect.bottom >= -margin && rect.top <= viewportHeight + margin;
}
