/**
 * Duração escrita da gravação — "0:12" da prancha 7a. Função pura, testável em node puro,
 * fora do componente (mesma disciplina de `ui/syncViewModel.ts`: o texto do estado nasce
 * de função pura, não de JSX).
 */
export function formatElapsed(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
