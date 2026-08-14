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

