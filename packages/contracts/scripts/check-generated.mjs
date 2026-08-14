import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderContract } from "./render.mjs";

const packageDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const output = join(packageDir, "src", "scene.generated.ts");
const generated = await renderContract(join(packageDir, "scene.schema.json"));
const current = await readFile(output, "utf8").catch(() => "");

if (current !== generated) {
  console.error("Contrato TypeScript desatualizado. Execute `make contracts`.");
  process.exitCode = 1;
}

