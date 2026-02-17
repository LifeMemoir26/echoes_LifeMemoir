"""Reducer registry with missing-reducer protection."""

from __future__ import annotations

from typing import Any, Callable


ReducerFn = Callable[[Any, Any], Any]


class ReducerRegistry:
    """Registry for explicit reducer definitions."""

    def __init__(self) -> None:
        self._reducers: dict[str, ReducerFn] = {}

    def register(self, field_name: str, reducer: ReducerFn) -> None:
        self._reducers[field_name] = reducer

    def get(self, field_name: str) -> ReducerFn:
        if field_name not in self._reducers:
            raise KeyError(f"Missing reducer for field: {field_name}")
        return self._reducers[field_name]

    def has(self, field_name: str) -> bool:
        return field_name in self._reducers

    def ensure(self, fields: list[str]) -> None:
        missing = [f for f in fields if f not in self._reducers]
        if missing:
            raise ValueError(f"Reducers required but missing: {', '.join(missing)}")
