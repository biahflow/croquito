# ADR-0042: Eventos de domínio por outbox transacional com publicação em Pub/Sub

Status: Proposed  
Data: 2026-08-21 (broker Pub/Sub decidido pelo usuário em sessão; o aceite
formal deste ADR é o gate humano pendente)  
Responsável: Product / Engineering

> Nota de numeração: o número 0041 está reservado pela F-029 (ator-máquina na
> decisão), em elaboração em outra sessão. Em caso de colisão na integração,
> este documento é renumerado — o conteúdo prevalece sobre o número.

## Contexto

A metodologia de valor da Biahflow (baseline AS-IS → TO-BE medido → valor
realizado) precisa que o croquito exporte fatos operacionais para o portal do
cliente (repositório próprio), que consolida métricas de automação, e no
futuro integra ERPs. Hoje o croquito não emite nada para fora: a fila
SQS/Pub-Sub existente é comando interno API↔worker (`ProcessingQueue`,
`PubSubProcessingQueue`), sem webhook, exportação ou barramento.

O requisito do usuário é consumo **desacoplado**: o portal não chama a API do
croquito para saber o que aconteceu.

## Decisão

1. **Outbox transacional**: todo fato relevante grava uma linha na tabela
   `domain_events` **na mesma transação** da mudança de estado que o produziu
   (API junto de `_record_audit`; worker junto dos `UPDATE` de stage). O fato
   nunca se perde nem é publicado sem ter acontecido.
2. **Porta `DomainEventPublisher`** com adapters, no padrão já existente de
   seleção de fila por configuração. Um relay idempotente
   (`croquito-demo publish-events`) drena a outbox e publica.
3. **Broker: Pub/Sub** (tópico dedicado, `CROQUITO_DOMAIN_EVENTS_TOPIC`),
   porque o ambiente hospedado já opera GCP/Pub-Sub com credenciais e padrões
   estabelecidos (ADR-0025). RabbitMQ/Kafka permanecem possíveis como novos
   adapters atrás da mesma porta, sem tocar produtores.
4. **Contrato versionado por tipo** (`croquito.<entidade>.<fato>.v1`),
   documentado em
   [events-contract.md](../features/F-031-value-events/events-contract.md);
   payload obedece à política de logs (IDs, durações, contagens, custo —
   nunca conteúdo). Entrega at-least-once; consumidor deduplica por
   `event_id`.

## Consequências

- O portal consome do broker sem acoplamento com a API; ERPs integram no
  portal, não aqui.
- `domain_events` cresce com o uso; a fatia 1 não implementa retenção/poda —
  consequência aceita, revisitada quando houver volume real.
- O relay é um processo a operar no hosted (agendado ou contínuo); até lá, a
  outbox acumula sem perda.
- A infraestrutura do tópico é provisionada como código na integração (gate
  humano); nenhum recurso é criado nesta rodada.

## Alternativas consideradas

- **Endpoint pull na API** (`GET /v1/events`): acoplaria o portal à API e à
  sua autenticação; rejeitado pelo requisito de desacoplamento.
- **Webhook push do croquito para o portal**: exige registro de endpoints,
  assinatura e retry/DLQ próprios — custo maior que o broker gerenciado que
  já operamos.
- **Publicar direto do request path (sem outbox)**: perde eventos em falha de
  broker e publica fatos de transações abortadas; rejeitado.
- **RabbitMQ/Kafka agora**: tecnologia nova sem operação estabelecida no
  hosted; adiado — a porta preserva a opção.
