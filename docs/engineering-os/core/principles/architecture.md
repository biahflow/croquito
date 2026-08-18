# Architecture Principles

## Boundaries are contracts

Make module ownership, public interfaces, data ownership, and failure modes explicit. Do not leak internal implementation details through public contracts.

## Prefer existing patterns

Use the project’s established structure, dependency direction, error handling, logging, and testing conventions. Introduce a new pattern only when its benefit is clear and documented.

## Design for change, not speculation

Choose simple, observable designs that satisfy current requirements. Do not add layers, services, or abstractions solely for hypothetical future needs.

## Protect data boundaries

Preserve authorization, tenant isolation, input validation, and data integrity at every boundary. Treat external input and cross-service data as untrusted.

## Document consequential decisions

Create an ADR when a choice has durable impact on architecture, operations, security, or cost. Keep ADRs short and include context, decision, consequences, and alternatives considered.
