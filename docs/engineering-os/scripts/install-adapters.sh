#!/usr/bin/env bash
#
# Render the harness adapters with an absolute Engineering OS root and install them at
# each harness's global instruction path.
#
# The adapters are bootstraps: they point a harness at this repository. They are not the
# rule set. Installing them does not grant a harness any authority that the Core denies.
#
# Usage:
#   scripts/install-adapters.sh              # install
#   scripts/install-adapters.sh --dry-run    # report what would change, write nothing
#
set -euo pipefail

EOS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0

case "${1:-}" in
  "")         DRY_RUN=0 ;;
  --dry-run)  DRY_RUN=1 ;;
  *)
    echo "unknown argument: $1" >&2
    echo "usage: $(basename "$0") [--dry-run]" >&2
    exit 2
    ;;
esac
if [ "$#" -gt 1 ]; then
  echo "unexpected extra arguments: ${*:2}" >&2
  exit 2
fi

# The Claude adapter is installed beside the operator's global instruction file, not as it.
# CLAUDE.md at that path is the operator's own document; it is imported by the operator, so
# personal preferences and the Engineering OS bootstrap stay in separate files and neither
# overwrites the other. Codex has no such convention, so its adapter is the global file.
CLAUDE_TARGET="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/engineering-os.md"
CODEX_TARGET="${CODEX_HOME:-$HOME/.codex}/AGENTS.md"

# Substitution is pure bash parameter expansion, never sed. A repository path containing
# `&`, `#`, or a backslash is substituted literally; sed would have mangled it silently and
# still reported success, leaving every import pointing at a path that does not exist.
render() {
  local source="$1" template
  if [ ! -f "$source" ]; then
    echo "missing adapter: $source" >&2
    return 1
  fi
  template="$(cat "$source")"
  printf '%s\n' "${template//\{\{EOS_ROOT\}\}/$EOS_ROOT}"
}

# A symlinked destination is refused rather than written through. Writing through the link
# would modify whatever the operator's dotfiles manage, in place, while the backup landed
# somewhere else entirely.
check_destination() {
  local destination="$1"
  if [ -L "$destination" ]; then
    echo "refusing to write through a symlink: $destination -> $(readlink "$destination")" >&2
    echo "resolve it manually, then re-run." >&2
    return 1
  fi
  if [ -e "$destination" ] && [ ! -f "$destination" ]; then
    echo "destination exists and is not a regular file: $destination" >&2
    return 1
  fi
  return 0
}

install_rendered() {
  local rendered="$1" destination="$2" directory backup
  directory="$(dirname "$destination")"

  if [ -f "$destination" ] && [ "$rendered" = "$(cat "$destination")" ]; then
    echo "UNCHANGED  $destination"
    return 0
  fi

  mkdir -p "$directory"

  # Never discard an existing instruction file. A pre-existing file at this path may be the
  # operator's own global instructions; it is preserved, never overwritten silently.
  if [ -e "$destination" ]; then
    backup="${destination}.backup.$(date +%Y%m%d%H%M%S)"
    cp -p "$destination" "$backup"
    echo "BACKED UP  $backup"
  fi

  printf '%s\n' "$rendered" > "$destination"
  echo "INSTALLED  $destination"
}

echo "Engineering OS root: $EOS_ROOT"

# Render and validate everything before writing anything. A partial install leaves two
# harnesses under different Cores, which workflows/execution.md defines as a defect.
CLAUDE_RENDERED="$(render "$EOS_ROOT/adapters/claude/CLAUDE.md")"
CODEX_RENDERED="$(render "$EOS_ROOT/adapters/codex/AGENTS.md")"
check_destination "$CLAUDE_TARGET"
check_destination "$CODEX_TARGET"

if [ "$DRY_RUN" -eq 1 ]; then
  for destination in "$CLAUDE_TARGET" "$CODEX_TARGET"; do
    if [ -e "$destination" ]; then
      echo "WOULD REPLACE  $destination  (existing file would be backed up)"
    else
      echo "WOULD CREATE   $destination"
    fi
  done
  echo
  echo "Dry run. Nothing was written."
  exit 0
fi

install_rendered "$CLAUDE_RENDERED" "$CLAUDE_TARGET"
install_rendered "$CODEX_RENDERED" "$CODEX_TARGET"

cat <<NOTE

Installed files are generated output. Edit the adapters under adapters/ and re-run this
script; do not edit the installed copies.

Claude Code loads $CLAUDE_TARGET only if the global instruction file imports it. Confirm
that ${CLAUDE_CONFIG_DIR:-\$HOME/.claude}/CLAUDE.md contains this line:

    @$CLAUDE_TARGET

Verify the result in each harness before relying on it. A bootstrap that is present but not
loaded is not global context.
NOTE
