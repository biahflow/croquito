# Proveniência do snapshot da Engineering OS

Status: Generated
Responsável: Engineering
Última revisão: 2026-08-26

Este diretório é um **espelho pinado** da camada global da Engineering OS, vendorizado para
que CI, colaborador novo e agente em nuvem enxerguem as mesmas regras que o operador carrega
por fora ([ADR-0034](../adr/0034-camada-global-vendorizada-e-pinada.md), pino por tag na
[ADR-0052](../adr/0052-pino-da-camada-global-por-tag-do-remoto.md)). Os arquivos são cópia
fiel da origem, em inglês, e **não são editados aqui** — nem este registro, que é gerado pelo
script.

| Campo | Valor |
|---|---|
| Origem | `https://github.com/biahflow/engineeringOS.git` |
| Tag de origem | `v0.1.0` |
| Commit de origem | `7bc938ec4527e5ee95f83fc1993bbd4961028c9c` |
| Sincronizado em | 2026-08-26 |
| Arquivos espelhados | 91 |

## Ressincronizar

Avançar o pino é trocar `PINNED_TAG` em `scripts/sync_engineering_os.py` e rodar:

```bash
uv run python scripts/sync_engineering_os.py
```

Ressincronizar é ato deliberado, não rotina automática: o script recusa referência que não
seja tag publicada, e o diff resultante é revisado como qualquer outra mudança do repositório.
Enquanto não houver nova sincronização, a tag acima é a versão da camada global que vale para
este repositório.
