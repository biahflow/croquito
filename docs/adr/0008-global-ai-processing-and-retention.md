# ADR-0008: Processamento global controlado e retenção de sete dias

Status: Accepted  
Data: 2026-08-10  
Responsável: Security / Product

## Contexto

Modelos escolhidos podem processar fora do Brasil. Documentos de engenharia são
sensíveis e não devem permanecer indefinidamente.

## Decisão

Permitir APIs comerciais com roteamento global, informar o usuário e enviar apenas
páginas/recortes necessários. Expirar originais, intermediários, readings e
exports em sete dias; oferecer exclusão imediata.

## Alternativas

- Brasil-only: incompatível com a estratégia atual de modelos.
- Persistência indefinida: rejeitada por risco e falta de necessidade no MVP.

## Consequências

- Consentimento e transparência são requisitos de UX.
- Storage e banco precisam de reconciliação de lifecycle.
- Métricas anônimas podem permanecer sem conteúdo.

## Riscos e mitigação

Exposição de dados: minimização, criptografia, signed URLs, logging de payload
desabilitado e contratos de fornecedores.

