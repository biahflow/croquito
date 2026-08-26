# Trunk-Based Delivery, HML and Production Promotion

## Purpose

Define a vendor-neutral release convention for projects that choose trunk-based development with `main` as the integration trunk, automatic homologation deployment from `main`, and explicit production promotion from an immutable release tag created from an already integrated `main` commit.

Projects own concrete CI/CD commands, environments, tag syntax, rollout strategy and platform implementation.

## Core model

```text
short-lived task branch/worktree
  ↓
PR + required CI
  ↓
HUMAN MERGE GATE
  ↓
main
  ↓
post-merge CI
  ↓
BUILD ONCE immutable artifact
  ↓
automatic HML deployment of that artifact
  ↓
HML validation
  ↓
release tag created from approved main commit
  ↓
PROMOTE SAME artifact/digest
  ↓
PROD
```

> Merge promotes an immutable artifact to homologation. A release tag promotes that same homologated artifact to production.

## Trunk-based constraints

Projects using this workflow SHOULD keep one protected long-lived integration branch (`main`), use short-lived task branches/worktrees, integrate frequently through reviewed PRs, use feature flags when incomplete functionality must be integrated, and avoid long-lived `develop`, `release/*`, HML or PROD branches as the normal delivery path.

Hotfixes MUST converge back to `main`.

## Build once, promote many

The normative release invariant is:

```text
source SHA X
  ↓
build artifact once
  ↓
record immutable digest D
  ↓
verify D
  ↓
deploy D to HML
  ↓
validate HML running D
  ↓
release decision/tag for SHA X
  ↓
promote/copy/reference D without rebuild
  ↓
deploy D to PROD
```

Production MUST NOT rebuild application source that was already built and homologated for the release candidate.

The promoted object SHOULD be identified by immutable digest rather than only by a mutable tag. A human-friendly release tag may point to the source SHA and/or be attached to the promoted image, but the deployment evidence must retain the artifact digest.

If HML and PROD use different registries/projects, promotion SHOULD copy the manifest/blob by digest or retag the existing immutable manifest. It MUST NOT execute a new application build.

## Homologation from main

After human merge:

```text
main updated
  ↓
post-merge CI
  ↓
build immutable artifact for main SHA
  ↓
record SHA + digest
  ↓
HML deploy by digest
  ↓
HML smoke/integration/runtime validation
  ↓
verify runtime revision uses expected digest
```

HML is a projection of `main`, not a separate source-of-truth branch.

The project SHOULD expose which `main` SHA and artifact digest are deployed to HML and whether post-merge CI, deploy and runtime validation succeeded.

## Production by immutable tag and artifact promotion

Production SHOULD be triggered from an immutable release tag pointing to a commit already reachable from protected `main` and already homologated with a known artifact digest.

```text
main SHA X
  ↓
artifact digest D built once
  ↓
HML running D and green
  ↓
human/business release decision
  ↓
tag X as release
  ↓
promote D
  ↓
PROD runs D
```

The production workflow MUST verify deterministically before deployment:

1. the tag target is reachable from protected `main`;
2. the tagged SHA has a recorded HML artifact digest;
3. HML validation for that exact digest succeeded;
4. the artifact still exists and its digest matches the recorded evidence;
5. production will deploy/promote the same digest, not rebuild source.

Tag creation is a release decision, not an implementation side effect. The Builder MUST NOT create a production tag merely because a task completed.

## Environment states

Recommended states:

```text
MERGED_TO_MAIN
POST_MERGE_CI_PENDING
POST_MERGE_CI_FAILED
POST_MERGE_CI_GREEN
ARTIFACT_BUILDING
ARTIFACT_READY
HML_DEPLOYING
HML_DEPLOY_FAILED
HML_READY
READY_FOR_PRODUCTION
PRODUCTION_PROMOTING
PRODUCTION_DEPLOYING
PRODUCTION_DEPLOY_FAILED
PRODUCTION_READY
```

`PR merged` is not equivalent to `PRODUCTION_READY`.

## HML validation

Projects SHOULD define deterministic post-deploy evidence appropriate to risk: health/readiness, migrations, smoke tests, integration probes, browser/E2E flows, observability checks, deployment SHA verification and deployed artifact-digest verification.

## Production safety

Production promotion SHOULD:

- preserve the exact immutable digest validated in HML;
- avoid Docker/application rebuild steps;
- copy/retag manifests only when registry topology requires it;
- verify tag-to-main ancestry;
- verify HML SHA/digest evidence;
- preserve audit links among release tag, source SHA, artifact digest, HML run and PROD run;
- support rollback by redeploying a previously known-good digest.

## Hotfixes

```text
fix branch from current main
→ focused PR / emergency gate
→ main
→ build once
→ HML or documented emergency validation of the artifact
→ release tag
→ promote same artifact
→ PROD
```

Do not repair production only on a divergent branch.

## Evidence

Release evidence SHOULD capture:

- main SHA;
- integrated PRs;
- post-merge CI run/result;
- artifact repository/name;
- immutable artifact digest;
- HML deployment run/result;
- HML runtime SHA/digest;
- HML validation result;
- release tag;
- production promotion/deployment run/result;
- PROD runtime SHA/digest;
- required human release approval.

The key proof is:

```text
HML artifact digest == PROD artifact digest
```

## FinOps

CI polling, SHA/tag ancestry verification, digest lookup, manifest copy/retag, artifact promotion, deployment status retrieval and release evidence serialization are deterministic operations and MUST NOT invoke an LLM merely for convenience.
