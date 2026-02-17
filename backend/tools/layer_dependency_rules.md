# Layer Dependency Rules

Target layers:
- src/domain
- src/application
- src/infra
- src/interfaces

Allowed dependencies:
- interfaces -> application, domain
- application -> domain
- infra -> domain
- domain -> (none of the above layers)

Disallowed examples:
- domain -> application
- domain -> infra
- domain -> interfaces
- application -> interfaces
- application -> infra (direct concrete dependency)
- infra -> application
- infra -> interfaces
