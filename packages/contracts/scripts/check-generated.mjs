import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderBarrel, renderContract } from "./render.mjs";

const packageDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(
  await readFile(join(packageDir, "contracts.manifest.json"), "utf8"),
);

const stale = [];
for (const entry of manifest) {
  const schemaPath = join(packageDir, entry.schema);
  const outputPath = join(packageDir, entry.typescript);
  const generated = await renderContract(schemaPath);
  const current = await readFile(outputPath, "utf8").catch(() => "");
  if (current !== generated) {
    stale.push(entry.typescript);
  }
}

const barrelPath = join(packageDir, "src", "index.ts");
const generatedBarrel = renderBarrel(manifest);
const currentBarrel = await readFile(barrelPath, "utf8").catch(() => "");
if (currentBarrel !== generatedBarrel) {
  stale.push("src/index.ts");
}

if (stale.length > 0) {
  for (const path of stale) {
    console.error(`Contrato TypeScript desatualizado: ${path}. Execute \`make contracts\`.`);
  }
  process.exitCode = 1;
}
