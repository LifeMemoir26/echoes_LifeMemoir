# Contributing

## Backend Structure Rules

- Keep backend architecture and migration documents under `backend/docs/`.
- Keep automated tests under `backend/tests/` with pytest-discoverable naming (`test_*.py`).
- Keep `backend/scripts/` for tooling/operations only; do not add test cases there.

## Development Commands

```bash
cd backend

# Run tests
pytest -q tests

# Run layer dependency guard
python scripts/check_layer_dependencies.py
```

