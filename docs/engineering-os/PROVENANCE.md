# Proveniência do snapshot da Engineering OS

Status: Generated
Responsável: Engineering
Última revisão: 2026-08-18

Este diretório é um **espelho pinado** da camada global da Engineering OS, vendorizado para
que CI, colaborador novo e agente em nuvem enxerguem as mesmas regras que o operador carrega
por fora ([ADR-0034](../adr/0034-camada-global-vendorizada-e-pinada.md)). Os arquivos são
cópia fiel da origem, em inglês, e **não são editados aqui** — nem este registro, que é
gerado pelo script.

| Campo | Valor |
|---|---|
| Commit de origem | `72360d46c62ce0ed115c7733feb590a07ffd9fc3` |
| Estado da origem | `clean` |
| Sincronizado em | 2026-08-18 |
| Caminho de origem | `~/workspace/engineeringOS` |
| Arquivos espelhados | 26 |

## Ressincronizar

```bash
uv run python scripts/sync_engineering_os.py
```

Ressincronizar é ato deliberado, não rotina automática: o script recusa origem com árvore
suja e o diff resultante é revisado como qualquer outra mudança do repositório. Enquanto
não houver nova sincronização, o commit acima é a versão da camada global que vale para
este repositório.
