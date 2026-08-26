---
task_id: HC-006
title: "Implement User Authentication Backend"
description: "Build JWT-based auth system with database schema migration"
role: builder
requires:
  - implementation
  - testing
  - database_migration
dependencies: []
created_at: 2026-08-23T18:00:00Z
estimated_effort_hours: 16
priority: high
---

## Task: HC-006 - User Authentication Backend

### Objective

Implement a complete JWT-based user authentication system with:
- Database schema for users (PostgreSQL migration)
- API endpoints for login, logout, token refresh
- Password hashing with bcrypt
- Comprehensive unit tests
- Integration tests with real database

### Acceptance Criteria

- [ ] Database migration creates `users` table with proper constraints
- [ ] Login endpoint returns valid JWT token
- [ ] Logout endpoint invalidates token
- [ ] Token refresh endpoint issues new valid token
- [ ] Password stored as bcrypt hash (never plain text)
- [ ] All unit tests pass (90%+ coverage)
- [ ] Integration tests pass against test database
- [ ] No security vulnerabilities (OWASP Top 10)
- [ ] Documentation updated with auth flow diagram

### Scope

**In Scope:**
- Database schema design and migration
- JWT token generation and validation
- Password hashing and verification
- API endpoints (login, logout, refresh)
- Unit and integration tests
- Security review by reviewer agent

**Out of Scope:**
- OAuth/SAML/SSO integration (future task)
- Email-based authentication (future task)
- 2FA implementation (future task)
- Frontend auth UI (separate frontend task)

### Technical Context

- **Backend Framework:** NestJS 9+
- **Database:** PostgreSQL 14+
- **Auth Library:** jsonwebtoken, bcryptjs
- **Test Framework:** Jest
- **Architecture:** Follows `core/principles/architecture.md`

### Validation Profiles

```yaml
profiles:
  unit_tests:
    command: npm test -- --coverage
    passing_criteria: "90%+ coverage, all tests passing"
    
  integration_tests:
    command: npm run test:e2e
    passing_criteria: "all e2e tests passing"
    
  lint:
    command: npm run lint
    passing_criteria: "0 errors, 0 warnings"
    
  type_check:
    command: npm run typecheck
    passing_criteria: "0 type errors"
    
  security_audit:
    command: npm audit
    passing_criteria: "0 critical vulnerabilities"
```

### Subtasks (DAG)

```
HC-006-A: Schema Migration (depends: none)
  └─ HC-006-B: Backend Implementation (depends: HC-006-A)
     ├─ HC-006-C: Unit Tests (depends: HC-006-B)
     └─ HC-006-D: Integration Tests (depends: HC-006-B)
     └─ HC-006-E: Architecture Review (depends: HC-006-B, HC-006-C, HC-006-D)
```

### Resources

- ADR: `adr/005-jwt-auth-strategy.md`
- PRD: `docs/PRD-user-auth.md`
- Related tasks: HC-005 (API scaffold), HC-007 (frontend auth)

### Definition of Done

From `core/definition-of-done.md`:
- ✓ Implementation matches specification
- ✓ ADRs respected
- ✓ Tests pass (unit + integration)
- ✓ Linting + type-check pass
- ✓ No secrets in code
- ✓ Documentation updated
- ✓ Diff is focused and reviewable
- ✓ No approval gates bypassed

### Assumptions

- PostgreSQL database is accessible during development
- bcryptjs version 5.0+ is available
- JWT secret is stored in environment variables (not committed)
- Team has reviewed and approved ADR-005

### Risks

- **Risk 1:** Token expiration edge cases (mitigation: extensive testing)
- **Risk 2:** Database connection pooling under load (mitigation: load testing)
- **Risk 3:** Bcrypt performance on slow hardware (mitigation: configurable rounds)
- **Risk 4:** JWT token stored in cookies vs localStorage (mitigation: security review required)

### Approval Gates

- **Human Decision 1:** Architecture review approved by reviewer agent
- **Human Decision 2:** Security audit approved (no critical vulns)
- **Human Decision 3:** Final merge approval by project lead
