# Behavior Equivalence Criteria

## Scope
This defines how we judge equivalence between legacy orchestration and LangGraph orchestration.

## Required parity dimensions
1. Output shape parity
- Required top-level fields must exist.
- Required nested structures must preserve contract types.

2. Error model parity
- Equivalent failure classes must map to stable error codes.
- Retryable vs non-retryable classification must be preserved.

3. Side-effect parity
- Database writes and vector updates must be semantically equivalent.
- No duplicate writes for a single logical execution.

4. Concurrency semantics parity
- Key rotation and cooldown behavior must remain consistent.
- Timeout and cancellation behavior must stay deterministic.

## Non-parity allowances
- Internal node ordering may differ if final semantics are equivalent.
- Logs and internal tracing format may evolve.

## Baseline validation checklist
- Run legacy and LangGraph flows with same input set.
- Compare normalized outputs and side effects.
- Record differences and classify as expected/unexpected.

## Required evidence artifacts
- Input sample set
- Diff report
- Error mapping report
- Side-effect verification report
