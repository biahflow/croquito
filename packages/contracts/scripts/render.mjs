import { compileFromFile } from "json-schema-to-typescript";

export async function renderContract(schemaPath) {
  return compileFromFile(schemaPath, {
    bannerComment:
      "/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */",
    style: {
      bracketSpacing: true,
      printWidth: 100,
      semi: true,
      singleQuote: false,
      tabWidth: 2,
      trailingComma: "all"
    }
  });
}

/**
 * Barril único reexportando todos os módulos `typescript` do manifesto. Gerado junto com
 * os contratos para que um modelo novo no manifesto sem entrada aqui reprove o mesmo
 * drift gate (`check-generated.mjs`).
 *
 * Cada módulo é reexportado sob um namespace nomeado pelo `model` do manifesto (ex.:
 * `SceneRevision`, `TakeoffPacket`) em vez de `export * from`: os seis geradores
 * produzem tipos auxiliares homônimos (`Id`, `Note`, `Action`, ...) para propriedades de
 * schema, e um `export *` plano vira erro de exportação ambígua (TS2308) assim que
 * qualquer consumidor importar qualquer coisa do barril.
 */
export function renderBarrel(manifest) {
  const lines = manifest.map((entry) => {
    const specifier = entry.typescript.replace(/^src\//, "./").replace(/\.ts$/, "");
    return `export * as ${entry.model} from "${specifier}";`;
  });
  return [
    "/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */",
    "",
    ...lines,
    "",
  ].join("\n");
}

