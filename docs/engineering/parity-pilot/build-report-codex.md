BUILD REPORT

Status: BUILD_COMPLETE
Files changed: docs/INDEX.md; docs/engineering/parity-pilot/build-report-codex.md
Validation executed: `grep -n "imutável" docs/INDEX.md` — no matches (expected exit 1); `UV_CACHE_DIR=/private/tmp/uv-cache-croquito uv run python scripts/check_docs.py` — exit 0; `make check` — exit 0; `git status --porcelain` — exactly the two contract lines
Validation skipped: none
Unavailable capabilities: none
Assumptions: `Última revisão: 2026-08-18` was already current and remained unchanged; the ADR link is relative to `docs/INDEX.md` and therefore uses `adr/README.md`
Remaining risks: none
Human decisions required: none
