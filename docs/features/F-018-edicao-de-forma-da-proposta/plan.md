# F-018 — Plano de implementação

Gates cumpridos: [ADR-0050](../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md)
aceito em 2026-08-23 e [Design Approval Package](mock/README.md) revisão 1 **aprovado por ato
humano em 2026-08-27**.

## A ordem é ditada pelo invariante, não por conveniência

O risco central é **adulterar a observação**: se a correção sobrescrever a proposta da máquina,
o produto perde a única medida objetiva de quanto o modelo erra. O ADR resolve isso com um
conjunto de proveniência própria, e por isso o invariante entra **primeiro**, no domínio, antes
de existir qualquer rota que possa gravar uma correção sem origem.

Depois vem a persistência, porque `detector_version` é do conjunto: correção e observação não
cabem no mesmo `proposals_json`, e isso é coluna nova. Só então a rota, e por último a tela —
que é a única parte que pode ser refeita sem custo de dado.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [O invariante no domínio: proveniência, derivação e pontuação ausente](tasks/T1-invariante-no-dominio.md) | **Entregue** |
| T2 | [Coluna própria e a rota de correção](tasks/T2-persistencia-e-rota.md) | **Entregue** |
| T3 | [A correção na tela: alças, união e superadas](tasks/T3-correcao-na-tela.md) | **Entregue** |

## O que a execução decidiu diferente do plano

1. **`quality_score` opcional espalhou-se mais do que o ADR previa.** O ADR nomeia a
   consequência ("quem ordena por qualidade passa a tratar `None`"); a execução encontrou
   **quatro** consumidores: a ordenação do detector, o limiar do overlay, a eval de extração e
   o delta do refino. Cada um recebeu a decisão explícita — proposta sem pontuação vai para o
   fim do próprio tipo, é sempre desenhada no overlay, conta como cobertura zero na eval e
   viaja como ausência no delta.
2. **A guarda de "já decidida" precisou ser repetida na fronteira.** O pacote de design
   resolve na tela (o ato aparece desabilitado), mas quem chama a rota direto não passa pela
   tela — a rota recusa com `PROPOSAL_ALREADY_DECIDED`.
3. **Círculo ficou fora.** O pacote de design não cobre corrigir centro e raio, e inventar
   quatro vértices para um círculo produziria uma forma que ninguém desenhou. A tela recusa com
   o motivo escrito. É `PLAN_DEVIATION` declarado, não omissão.

## Integração

Branch e PR próprios. A migração `0019` encadeia na `0018`; a numeração final é assunto do
rebase de integração, e o encadeamento relativo é que precisa sobreviver a ele.

## Human gates

- ADR e Design Approval: **cumpridos**.
- Merge do PR e aplicação da migração no ambiente hospedado: atos humanos.
- Aceite numa rodada real, com o caso do Guaxindiba V3.
