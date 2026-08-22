/**
 * Fila serial de tarefas assíncronas. Dois toques rápidos em campo não podem correr em
 * paralelo: cada comando precisa ler o estado que o anterior persistiu, senão o segundo
 * `saveSurvey` sobrescreve o survey sem o resultado do primeiro (perda de ação
 * confirmada — o NFR central da F-032). Quem enfileira recebe a promise da própria
 * tarefa; uma tarefa que falha não quebra a fila para as seguintes.
 */
export type SerialQueue = <T>(task: () => Promise<T>) => Promise<T>;

export function createSerialQueue(): SerialQueue {
  let tail: Promise<unknown> = Promise.resolve();
  return function enqueue<T>(task: () => Promise<T>): Promise<T> {
    const result = tail.then(task, task);
    tail = result.catch(() => undefined);
    return result;
  };
}
