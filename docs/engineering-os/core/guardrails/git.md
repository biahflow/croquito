# Git Guardrails

Agents must:

- inspect the working tree before editing;
- preserve unrelated user changes;
- keep commits focused and understandable when commits are requested;
- report files changed and checks executed.

Agents must not:

- rewrite shared history, force-push, or delete branches without explicit approval;
- discard, reset, or overwrite user work to simplify a task;
- commit secrets, generated local state, or unrelated changes;
- merge, open, or approve pull requests without explicit authorization.
