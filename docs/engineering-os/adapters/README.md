# Adapters

An adapter is a bootstrap: the smallest document that points one harness at this
repository. It carries no rules of its own, and it cannot grant a harness authority the
Core denies.

| Harness | Adapter | Installed at |
| --- | --- | --- |
| Claude Code | `claude/CLAUDE.md` | `${CLAUDE_CONFIG_DIR:-~/.claude}/engineering-os.md` |
| Codex | `codex/AGENTS.md` | `${CODEX_HOME:-~/.codex}/AGENTS.md` |

The Claude adapter is installed beside the global instruction file rather than as it:
`CLAUDE.md` at that path is the operator's own document, and it imports the adapter with
`@${CLAUDE_CONFIG_DIR:-~/.claude}/engineering-os.md`. Personal preferences and the
Engineering OS bootstrap stay in separate files, and reinstalling never overwrites the
operator's. Codex has no equivalent import convention, so its adapter is the global file.

## Why adapters are rendered, not copied

Both harnesses read their global instruction file from a fixed path outside this
repository. A relative reference resolved from that path does not reach this repository,
so every reference to the source of truth must be absolute. Hardcoding one operator's
absolute path in a versioned file makes the repository non-portable.

The adapters therefore carry the `{{EOS_ROOT}}` placeholder, and
[`../scripts/install-adapters.sh`](../scripts/install-adapters.sh) resolves it to this
checkout's absolute path at install time:

```bash
scripts/install-adapters.sh --dry-run   # inspect
scripts/install-adapters.sh             # install
```

The substitution is literal: a checkout path containing `&`, `#`, or a backslash is
inserted unchanged. An existing file at a destination is backed up, never discarded — that
path may hold the operator's own global instructions — and a destination that is a symlink is
refused rather than written through, because writing through the link would modify whatever
manages it while the backup landed somewhere else. Both adapters are rendered and validated
before either is written, so a failure does not leave the two harnesses under different
Cores.

## Resolution order

```text
Global adapter → Core → project instructions → task
```

Both adapters must reach the same Core documents and the same agent contracts. An
asymmetry between them is a defect: it means the same task carries different rules
depending on which harness picked it up. [`../workflows/execution.md`](../workflows/execution.md)
defines what the two harnesses must share for a Task Contract to be portable between them.

## Installing is not verifying

A rendered file at the right path is not evidence that a harness loaded it. Confirm in
each harness that the Core is present before treating global context as operational.
