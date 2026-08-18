# <FEATURE-ID> — Execution Plan

Produced by the Planner from an accepted Feature Contract. A plan states **how** an accepted
feature is decomposed. It does not change requirements, select a harness or model, or grant
approval.

## The required format lives in the Planner contract

Copy the `FEATURE EXECUTION PLAN` block from
[`agents/planner.md`](../agents/planner.md) — the section "Required output" — and fill it in
here. Do not transcribe it into this template: one authoritative definition, in the contract
that owns it, is what keeps a plan and the rules for plans from drifting apart.

The same contract owns the plan-validation checklist and the `PLAN_DEVIATION` record. Read it
before planning; this template does not restate it.

## What this file holds

1. the completed `FEATURE EXECUTION PLAN`;
2. the validation outcome for this plan — `PLAN_VALID` or `PLAN_INVALID`, with the objective
   issues when invalid;
3. every `PLAN_DEVIATION` recorded after the plan was frozen for execution.

A `PLAN_INVALID` result returns to the Planner with its issues. Do not correct the plan on
its behalf. After a `PLAN_VALID` plan is frozen, record changes as deviations rather than
editing the frozen plan in place.

## Task Contracts

Task Contracts are derived from the valid plan, using
[`templates/task.md`](task.md). A Builder never creates its own task.
[`workflows/execution.md`](../workflows/execution.md) defines when such a contract is
portable between harnesses and how an executor is assigned to it.
