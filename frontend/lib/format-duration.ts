// Formata segundos pra exibição sem arredondar pra minuto/hora inteiro — TMR
// pequeno perde precisão se "89s" virasse só "1 min". Formato:
// `14 s` / `1 min 29 s` / `1 h 02 min 15 s`. Usado em TMA, TMR humano, TMR
// geral e 1ª resposta no módulo SGP Suporte.
export function secondsLabel(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const totalSeconds = Math.max(0, Math.round(value));
  if (totalSeconds < 60) return `${totalSeconds} s`;

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const paddedSeconds = String(seconds).padStart(2, "0");

  if (hours === 0) return `${minutes} min ${paddedSeconds} s`;
  return `${hours} h ${String(minutes).padStart(2, "0")} min ${paddedSeconds} s`;
}
