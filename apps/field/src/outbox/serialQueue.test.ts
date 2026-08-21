import { describe, expect, it } from "vitest";

import { createSerialQueue } from "./serialQueue";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("createSerialQueue", () => {
  it("executa as tarefas uma por vez, na ordem de chegada", async () => {
    const queue = createSerialQueue();
    const first = deferred<void>();
    const order: string[] = [];

    const p1 = queue(async () => {
      order.push("start-1");
      await first.promise;
      order.push("end-1");
      return 1;
    });
    const p2 = queue(async () => {
      order.push("start-2");
      return 2;
    });

    // A segunda tarefa NÃO começa enquanto a primeira não termina — é o que impede dois
    // toques rápidos de lerem o mesmo estado e o segundo sobrescrever o primeiro.
    await Promise.resolve();
    expect(order).toEqual(["start-1"]);

    first.resolve();
    expect(await p1).toBe(1);
    expect(await p2).toBe(2);
    expect(order).toEqual(["start-1", "end-1", "start-2"]);
  });

  it("uma tarefa que falha não quebra a fila para as seguintes", async () => {
    const queue = createSerialQueue();

    const failing = queue(async () => {
      throw new Error("boom");
    });
    const next = queue(async () => "ok");

    await expect(failing).rejects.toThrow("boom");
    expect(await next).toBe("ok");
  });
});
