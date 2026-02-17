# Layer Mapping V1 (Legacy -> DDD Target)

## Goal
First-pass mapping from current modules to target DDD layers.

## Mapping

### Domain
- Current: `src/domain/**`
- Target: `src/domain/**` (retain, enforce purity)

### Application
- Current orchestration-heavy modules:
  - `src/services/knowledge/**`
  - `src/services/interview/**`
  - `src/services/generate/**`
- Target:
  - workflow orchestration and use-case coordination move to `src/application/**`

### Infra
- Current:
  - `src/infrastructure/database/**`
  - `src/infrastructure/llm/**`
  - `src/infrastructure/utils/**`
- Target:
  - concrete adapters in `src/infra/**`
  - legacy `src/infrastructure/**` kept temporarily for transition

### Interfaces
- Current:
  - `src/app/api/**`
- Target:
  - transport adapters in `src/interfaces/**`
  - keep compatibility wiring in `src/app/**` until cutover

## Transition notes
- This is a migration map, not immediate hard move.
- Path migration should happen flow-by-flow with parity checks.
