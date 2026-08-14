/**
 * Helpers pequenos e tipados para inputs numéricos controlados que precisam ficar vazios durante
 * a edição em vez de forçar "0" - sem quebrar o `number` que o resto do app (e a API) espera.
 *
 * Bug que motivou isto: alguns campos guardavam o valor digitado como STRING crua (direto de
 * `event.target.value`, sem `Number(...)`) e começavam em `"0"`. Como o estado nunca era
 * reconvertido a cada tecla, o React nunca reescrevia o DOM - então digitar "500" depois do "0"
 * ficava concatenado como "0500" pra sempre, até um blur/submit que corrigisse. Nos ~30 outros
 * campos numéricos do app que já faziam `onChange={(e) => setX(Number(e.target.value))}` com
 * estado `number`, o problema nem aparece: a cada tecla o React reescreve o DOM com o número já
 * limpo. Estes helpers só padronizam esse padrão correto (estado `number`, string vazia só na
 * borda de exibição) pros lugares que precisavam de "campo vazio enquanto eu edito".
 *
 * Não usar em campos que são IDENTIFICADORES (telefone, CEP, CPF/CNPJ, login, código, patrimônio,
 * série) - neles zero à esquerda pode ser significativo e o valor nunca deveria passar por
 * `Number(...)`.
 */

/** Valor pra prop `value` de um input controlado por estado `number` - mostra vazio quando o
 * número não é finito (NaN, Infinity), nunca "0" só porque o campo está sendo limpo pelo usuário. */
export function numericInputValue(value: number): number | "" {
  return Number.isFinite(value) ? value : "";
}

/** Valor pra guardar no estado a partir do `onChange` de um input numérico - string vazia vira
 * `NaN` (não "0"), pra não repor um zero indevido enquanto o campo está sendo digitado. Trate o
 * `NaN` no blur/submit (ex.: `Number.isFinite(value) ? value : fallback`). */
export function parseNumericInput(value: string): number {
  return value === "" ? Number.NaN : Number(value);
}
