# T1 — BUILD REPORT

```text
BUILD REPORT

Status: BUILD_COMPLETE
Files changed: deploy/nginx.conf; docs/features/F-007-tela-de-login/tasks/T1-build-report.md
Validation executed: BASELINE — make check (PASS); docker build -f docker/web.Dockerfile -t croquito-web-t1-baseline . (PASS). FINAL — git diff --check (PASS); make check (PASS); docker build -f docker/web.Dockerfile -t croquito-web-t1 . (PASS); container runtime with curl against /, /login, /revisao/ and /medicao/ (PASS); docker exec croquito-web-t1 nginx -t (PASS)
Validation skipped: none
Unavailable capabilities: none; Docker daemon access was available through approved escalation
Assumptions: the existing web image continues to place the SPA index at /revisao/index.html and the Vite build continues to emit assets below /revisao/assets/, both confirmed by the final image and curl checks
Remaining risks: deployment and merge were not performed; both remain outside this task and require the applicable human workflow gates
Human decisions required: none within T1
```
