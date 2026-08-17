import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderContract } from "./render.mjs";

const packageDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(
  await readFile(join(packageDir, "contracts.manifest.json"), "utf8"),
);

for (const entry of manifest) {
  const schemaPath = join(packageDir, entry.schema);
  const outputPath = join(packageDir, entry.typescript);
  const generated = await renderContract(schemaPath);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, generated, "utf8");
}
