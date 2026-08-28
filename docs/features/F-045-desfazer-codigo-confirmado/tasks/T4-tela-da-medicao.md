# F-045 T4 — A mesma superfície na jornada de medição

- **feature_id**: F-045
- **task_id**: T4
- **role**: builder
- **depends_on**: [T2, T3]
- **required_capabilities**: READ, WRITE (`apps/web/src`, `apps/web/src/medicao`), VALIDATE
- **risk**: MÉDIO — `MedicaoApp.tsx` vivo, e o módulo puro sai de dentro do orçamento.
- **relative_effort**: S

## Por que existe

A rota irmã (`POST /v1/valuation-rounds/{id}/code-assignments/revocations`) foi entregue e
testada na T2, e ficou **sem tela**. Uma rota sem superfície é capacidade que só o time sabe
que existe. A revisão 1 do pacote de design registrou isso como questão aberta; a **revisão
2** a fechou.

## O pacote de design é a especificação

[`../mock/README.md`](../mock/README.md) revisão 2 — **aprovada em 2026-08-28** —, decisão 7
e estado 6: na medição a frase
do pacote **vira lista**, e cada código recebe o mesmo ato — mesma caixa, mesma copy, mesmo
aviso de reabertura.

## Scope

1. **Mover o módulo puro** de `orcamento/revogacao.ts` para `apps/web/src/codeRevocation.ts`,
   com o tipo `CodeRevocationDraft` junto. As duas jornadas passam a importá-lo da raiz; o
   `api.ts` de cada uma reexporta o tipo para quem já o importava de lá.
2. `medicao/api.ts` e `medicao/requests.ts` — `postCodeRevocation` e `codeRevocationBody`.
3. `medicao/labels.ts` — a copy, **sem a linha do precedente**.
4. `medicao/MedicaoApp.tsx` — a lista do pacote com um botão por código,
   `CaixaDeDesfazerCodigo`, `ListaDeDesfeitos` e o handler.
5. `medicao/styles.css` — `.desfazer-caixa`, `.desfeitos`, `.lista-simples`, `.aviso-atencao`
   e `.codigo-desfeito`. **Nenhuma cor nova**: o âmbar é o de `.aviso-fixo`.

## Out of Scope

- Qualquer mudança de domínio, rota ou contrato — tudo já existe desde a T2.
- A recusa depois da aprovação: ela é do orçamento-base, onde a aprovação nominal existe.
- A linha "apaga o precedente…": o índice é da pré-licitação, e prometê-lo aqui seria falso.

## Acceptance Criteria

1. A frase do pacote vira lista, e cada código tem "Desfazer este código".
2. A caixa pede motivo, escreve o efeito em **duas** linhas e não menciona precedente.
3. Com pacote fechado, o aviso aparece e o botão diz "Desfazer e reabrir o pacote".
4. A lista de desfeitos mostra o código riscado, o selo escrito e o motivo.
5. O módulo puro passa a ter uma implementação só, importada pelas duas jornadas.
6. Nenhum teste existente afrouxado; `medicao/` continua sem importar de `orcamento/`.

## Validation

```bash
npm --workspace @croquito/web run test
make check
make test
```

## Resultado

Entregue em 2026-08-28. 6 testes novos em `apps/web/src/medicao/revogacao.test.tsx`; os 11 do
módulo puro migraram para `apps/web/src/codeRevocation.test.tsx`.
