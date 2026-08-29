/**
 * Máscaras visuais de CPF e telefone. Formatam só a EXIBIÇÃO enquanto a pessoa digita - o valor
 * enviado ao backend é sempre normalizado (`onlyDigits`) antes do envio, nunca a string mascarada.
 * O backend é sempre quem valida de verdade (`is_valid_cpf` em app/services/documents.py); a
 * validação aqui é só feedback imediato, nunca substitui a checagem do servidor.
 */

export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "");
}

export function formatCpf(value: string): string {
  const digits = onlyDigits(value).slice(0, 11);
  const part1 = digits.slice(0, 3);
  const part2 = digits.slice(3, 6);
  const part3 = digits.slice(6, 9);
  const part4 = digits.slice(9, 11);
  let result = part1;
  if (part2) result += `.${part2}`;
  if (part3) result += `.${part3}`;
  if (part4) result += `-${part4}`;
  return result;
}

export function formatPhone(value: string): string {
  const digits = onlyDigits(value).slice(0, 11);
  if (digits.length <= 10) {
    // Fixo: (00) 0000-0000
    const ddd = digits.slice(0, 2);
    const first = digits.slice(2, 6);
    const second = digits.slice(6, 10);
    let result = ddd ? `(${ddd}` : "";
    if (ddd.length === 2) result += ") ";
    result += first;
    if (second) result += `-${second}`;
    return result;
  }
  // Celular: (00) 00000-0000
  const ddd = digits.slice(0, 2);
  const first = digits.slice(2, 7);
  const second = digits.slice(7, 11);
  let result = ddd ? `(${ddd}` : "";
  if (ddd.length === 2) result += ") ";
  result += first;
  if (second) result += `-${second}`;
  return result;
}

/** Mesmo algoritmo de dígito verificador do backend (módulo 11) - feedback imediato na tela, não
 *  substitui a validação do servidor (ver docstring do arquivo). */
export function isValidCpf(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 11 || /^(\d)\1{10}$/.test(digits)) return false;

  function checkDigit(base: string): number {
    const weight = base.length + 1;
    let total = 0;
    for (let index = 0; index < base.length; index += 1) {
      total += Number(base[index]) * (weight - index);
    }
    const remainder = (total * 10) % 11;
    return remainder === 10 ? 0 : remainder;
  }

  const firstCheck = checkDigit(digits.slice(0, 9));
  const secondCheck = checkDigit(digits.slice(0, 9) + String(firstCheck));
  return digits.slice(-2) === `${firstCheck}${secondCheck}`;
}
