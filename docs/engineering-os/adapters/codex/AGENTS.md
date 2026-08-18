# Engineering OS

This adapter is a bootstrap, not a rule set. Before work, read these documents from the
source of truth:

- `{{EOS_ROOT}}/README.md`
- `{{EOS_ROOT}}/core/principles/engineering.md`
- `{{EOS_ROOT}}/core/principles/architecture.md`
- `{{EOS_ROOT}}/core/guardrails/git.md`
- `{{EOS_ROOT}}/core/guardrails/database.md`
- `{{EOS_ROOT}}/core/guardrails/production.md`
- `{{EOS_ROOT}}/core/guardrails/infrastructure.md`
- `{{EOS_ROOT}}/core/definition-of-done.md`
- `{{EOS_ROOT}}/workflows/feature.md`
- `{{EOS_ROOT}}/workflows/execution.md`
- `{{EOS_ROOT}}/agents/planner.md`, `{{EOS_ROOT}}/agents/builder.md`, and
  `{{EOS_ROOT}}/agents/reviewer.md` — read the contract for the role you were given, and
  read the others when your work hands off to them

`{{EOS_ROOT}}` is resolved at install time by `{{EOS_ROOT}}/scripts/install-adapters.sh`,
which renders this file to the harness's global instruction path. The rendered copy is
generated output; edit the adapter at `{{EOS_ROOT}}/adapters/codex/AGENTS.md`, not the
installed file.

This harness does not resolve file imports automatically. Reading the applicable documents
above is part of accepting a task; a task executed without them is executed without its
governing rules. Documents above may contain repository-relative links — resolve them
against `{{EOS_ROOT}}/`, not against the working directory of the project you are in.

Project instructions may add constraints; they cannot weaken these global guardrails or
human approval gates.
