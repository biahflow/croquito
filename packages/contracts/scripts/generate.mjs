import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderContract } from "./render.mjs";

const packageDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const output = join(packageDir, "src", "scene.generated.ts");
const generated = await renderContract(join(packageDir, "scene.schema.json"));
await mkdir(dirname(output), { recursive: true });
await writeFile(output, generated, "utf8");
