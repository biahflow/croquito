# F-045 T3 — A tela: desfazer no cartão, com o efeito à vista

- **feature_id**: F-045
- **task_id**: T3
- **role**: builder
- **depends_on**: [T2]
- **required_capabilities**: READ, WRITE (`apps/web/src/orcamento`), VALIDATE
- **risk**: MÉDIO — `OrcamentoApp.tsx` vivo; a etapa de códigos é o coração da jornada.
- **relative_effort**: M

## O pacote de design é a especificação

[`../mock/README.md`](../mock/README.md) revisão 1 e o HTML ao lado. As seis decisões valem
como requisito — em especial o **motivo obrigatório**, o **efeito escrito antes do clique**, o
**botão que muda de nome** com o pacote fechado e a **lista de desfeitos**.

## Scope

1. `revogacao.ts` — módulo puro: caixa, validação do motivo, pedido, `desfeitosDoItem` e
   `pacoteFechado`.
2. `api.ts`/`requests.ts` — `postCodeRevocation` e o corpo com `note` obrigatória.
3. `OrcamentoApp.tsx` — botão no cartão do pacote, `CaixaDeDesfazerCodigo`,
   `ListaDeDesfeitos` e o handler que redesenha a partir da resposta.
4. `labels.ts` e `styles.css` — copy em português; **nenhuma cor nova**.

## Out of Scope

- A tela da jornada de **medição** (a rota existe; a superfície não foi desenhada).
- Qualquer decisão sobre o unknown 1.

## Acceptance Criteria

1. Sem motivo, o botão que grava fica desabilitado.
2. Com pacote fechado, o aviso aparece e o botão diz "Desfazer e reabrir o pacote".
3. As três linhas de efeito aparecem, inclusive a do precedente que some.
4. A lista de desfeitos mostra motivo, autor e instante; par reconfirmado sai dela.
5. Trocar de elemento fecha a caixa.
6. Cor nunca é o único indicador; nenhum controle inerte é desenhado.

## Validation

```bash
npm --workspace @croquito/web run test -- src/orcamento/revogacao.test.tsx
make check
```

## Resultado

Entregue em 2026-08-28. 11 testes em `apps/web/src/orcamento/revogacao.test.tsx`, e os dois
componentes conferidos renderizados com a folha real do app.
