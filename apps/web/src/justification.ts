/**
 * Régua de validação da justificativa do revisor, espelhando o que a API já exige em
 * `HumanDecision.note` (3 a 500 caracteres). Módulo puro para ser testável sem DOM: a
 * tela usa `maxLength` como defesa de digitação, mas quem barra o submit é este limite.
 */
export const JUSTIFICATION_MIN_LENGTH = 3;
export const JUSTIFICATION_MAX_LENGTH = 500;

/** `null` quando o texto é válido; senão a frase que a tela mostra ao revisor. */
export function justificationIssue(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed.length < JUSTIFICATION_MIN_LENGTH) {
    return "Escreva a justificativa nas suas palavras (mínimo de 3 caracteres).";
  }
  if (trimmed.length > JUSTIFICATION_MAX_LENGTH) {
    return "A justificativa não pode passar de 500 caracteres.";
  }
  return null;
}
