# Engineering Principles

## Understand before changing

Inspect the relevant implementation, tests, project instructions, and architecture decisions before proposing or making a change. Reuse established patterns when they solve the same problem.

## Make small, reviewable changes

Prefer the smallest change that satisfies the accepted requirement. Do not mix unrelated refactors, formatting churn, or dependency upgrades into feature work.

## Validate deterministically

A task is not complete because an agent says so. Use the strongest applicable deterministic checks: tests, linting, type checking, build, security scanning, and policy validation.

## Preserve architecture

Respect existing ADRs and project conventions. If fulfilling the request requires a new architectural direction or contradicts an ADR, stop and request explicit human approval.

## State uncertainty explicitly

Never invent business requirements. Record assumptions, unknowns, and remaining risks in the work output.

## Keep humans in authority

Agents can inspect, implement, test, and recommend. They cannot approve their own work. Explicit human approval is required for production changes, destructive migrations or data changes, security exceptions, and architectural changes that alter module ownership, public interfaces, data ownership, or a durable technology or operational decision.
