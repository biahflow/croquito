# Design Approval Package — F-038, o item de legenda é um pacote de serviços

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: Approved (2026-08-26)  
Date: 2026-08-26  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> O comportamento que esta interface expõe é do
> [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md), **aceito por ato
> humano em 2026-08-25**. O que se decide aqui é a interface, não a regra.

## Ressalva sobre o que este pacote é

**Este pacote não traz telas capturadas.** As revisões anteriores deste repositório (F-033,
F-037) registraram composições visuais produzidas antes do aceite; aqui a aprovação foi
exercida sobre a **direção de interface descrita em texto** — a mudança de "escolher um
código" para "montar um pacote", mais o ato de fechamento — sem que um mock visual tivesse
sido produzido.

O registro fica assim de propósito: inventar telas depois do aceite para preencher a pasta
transformaria evidência em ficção. Se a execução da #81 revelar decisões visuais que o texto
abaixo não resolve, elas abrem **revisão 2**, com pacote próprio e aceite próprio.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a direção de interface descrita em "Decisões que este pacote carrega" — seleção múltipla de códigos por item de legenda, ato explícito de fechamento de pacote, e a memória de cálculo passando a existir na jornada do orçamento |
| Aprovado por | Daniel Campos |
| Data | 2026-08-26 |
| Revisão aprovada | 1 |
| Explicitamente **não** coberto | a composição visual (não há telas neste pacote); a copy final; os nomes de rotas e códigos de erro, que são do plano; o comportamento, que é do ADR-0053 e já foi aceito |

## Decisões que este pacote carrega

1. **A escolha de código deixa de ser exclusiva.** Hoje a etapa `codigos`
   (`apps/web/src/orcamento/OrcamentoApp.tsx`) guarda a escolha em `codeChoice`, um objeto
   único, com um botão "Escolher este código". Passa a acumular códigos, cada um com a
   parcela de quantidade que aquele elemento contribui.

2. **Fechar o pacote é um ato próprio, e não acontece sozinho.** É o que distingue "item
   resolvido" de "item pela metade". Um elemento com um de seis códigos confirmados aparece
   como **pendente** — nunca como pronto —, e o boletim não fecha sem o ato.

3. **A memória de cálculo passa a existir na jornada do orçamento.** Hoje `calc_sheets` não
   é referenciado em nenhum arquivo de `apps/web/src/orcamento/`; a memória só é renderizada
   na medição (`apps/web/src/medicao/MedicaoApp.tsx`). Com a matriz, ela é o artefato que
   explica de onde veio cada quantidade, e precisa ser visível onde a quantidade é montada.

4. **Nada nasce pré-marcado.** Vale aqui a mesma regra das jornadas anteriores: sugestão é
   sugestão, e a confirmação é ato humano rastreável.

5. **Cor não é o único indicador.** Estado de pacote aberto, parcela parcial e serviço
   derivado de outro precisam de rótulo textual, não só de cor — e aviso crítico não é
   escondido atrás de interação.

6. **A parcela parcial é declarada, com nota.** Os 170 m² de limpeza dentro dos 418,12 do
   piso não saem de conta nenhuma; a tela pede o número e a justificativa, e mostra o teto
   do elemento.

## Referências

- [Feature Contract](../feature.md)
- [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md)
