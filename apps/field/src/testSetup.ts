// Injeta um IndexedDB em memória no ambiente do vitest (node puro, sem browser). Sem isto
// `new Dexie(...)` falha porque `indexedDB`/`IDBKeyRange` não existem em `globalThis`.
import "fake-indexeddb/auto";
