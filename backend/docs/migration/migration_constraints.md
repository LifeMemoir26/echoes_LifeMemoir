# Migration Constraints

## Branch and collaboration constraints
- Develop only in the current local branch.
- Do not push or upload code to any remote/cloud.
- Do not merge branches unless explicitly requested.

## Delivery constraints
- Keep external API contracts stable during migration.
- Preserve behavior equivalence unless a requirement explicitly changes behavior.
- Use incremental, reversible changes.

## Runtime constraints
- Keep existing concurrency semantics during transition:
  - key rotation
  - cooldown on 429
  - retry/backoff
  - timeout and cancellation controls

## Quality constraints
- Every migration phase must have:
  - verifiable acceptance checks
  - rollback path
  - parity evidence against baseline
