# Versioning

Engineering OS is consumed as a **pinned mirror**: each project vendors a complete copy of
this repository and records which version it copied. The pin is what makes the global layer
reachable from CI, from a new collaborator's checkout, and from an agent running in the
cloud — none of which can see the operator's machine.

A pin is only useful if the thing it points at cannot move. Releases are therefore cut as
annotated Git tags in `MAJOR.MINOR.PATCH` form, prefixed with `v`:

```text
v0.1.0
```

The tag is immutable. Repointing an existing tag is not a release; it silently changes the
rules under every project that already pinned it.

## What each number means

This repository ships rules, not an API. The question that decides the number is: **does a
project that was compliant before this change stay compliant after it?**

| Bump | Meaning | Examples |
| --- | --- | --- |
| `MAJOR` | A project that was compliant may no longer be. The change tightens a guardrail, adds a required artifact, or changes the shape of a contract. | A new mandatory field in `BUILD REPORT`; a human gate added to a workflow that had none; a Definition of Done item that did not exist. |
| `MINOR` | Additive. A compliant project stays compliant without doing anything. | A new workflow document; a new template; a guardrail relaxed; a new optional adapter. |
| `PATCH` | No rule changed. | Typo, broken link, formatting, clarified wording that does not alter what is required. |

When a change is arguably `MINOR` and arguably `MAJOR`, it is `MAJOR`. The cost of an
unexpected `MAJOR` is a project reading a changelog; the cost of a hidden one is a project
believing it is compliant when it is not.

While the major version is `0`, `MINOR` carries breaking changes — the layer is still
settling and consumers pin explicitly.

## Cutting a release

Releases are cut from `main`, never from a branch:

```bash
git checkout main && git pull
scripts/check-links.py && scripts/check-tracked-artifacts.py
git tag -a v0.1.0 -m "Engineering OS v0.1.0"
git push origin v0.1.0
```

Pushing the tag runs [`.github/workflows/release.yml`](.github/workflows/release.yml), which
refuses a tag that is not valid SemVer, refuses a tag whose commit is not reachable from
`main`, re-runs the full validation, and publishes a GitHub Release.

## Advancing a consumer's pin

Advancing a pin is a reviewed change in the consumer repository, never an automatic job. The
consumer's sync fetches the tag, rewrites its mirror, and records the tag and the commit it
resolved to. The resulting diff is reviewed like any other change.

Until a consumer advances its pin, the version it names **is** the global layer for that
repository — including for an executor whose personal bootstrap points at a newer checkout.
The drift is visible and dated rather than silent.
