# Protocolo de mudança de prompts e modelos

Status: Accepted  
Responsável: AI Engineering  
Última revisão: 2026-08-10

## Mudanças cobertas

- Texto/instruções do prompt.
- Schema e parser.
- Modelo, snapshot, provider ou parâmetros.
- Roteamento, retry, crop ou resolução de imagem.
- Normalização e consenso.

## Processo

1. Registrar motivação e falha observada.
2. Congelar baseline: código, prompts, models e dataset version.
3. Criar candidate com nova versão.
4. Rodar testes determinísticos.
5. Rodar eval autorizada no mesmo conjunto e uma única vez por candidate.
6. Comparar por caso/campo, não só média.
7. Revisar false-confident errors e custo.
8. Aprovar ou rejeitar explicitamente.
9. Publicar configuração com feature flag/canary quando aplicável.
10. Monitorar e manter rollback imediato.

## Evidência de aprovação

O change record contém:

- Motivo e owner.
- Diff sem dados sensíveis.
- IDs de baseline/candidate.
- Métricas e regressões conhecidas.
- Domain review quando resultado geométrico muda.
- Plano e gatilho de rollback.

## Proibições

- Escolher o melhor de várias execuções não declaradas.
- Alterar golden answer para acomodar o modelo.
- Promover por percepção em poucos screenshots.
- Trocar alias sem capturar model ID efetivo.
- Fazer ajuste direto em produção sem eval.

## Rollback

Configuração anterior permanece implantável. Rollback é acionado por aumento de
false-confident errors, schema failures, custo fora do budget, incidentes de
privacidade ou regressão golden.

