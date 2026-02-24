"""Workflow base class for LangGraph orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
import time
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import StateGraph

from .checkpointing import create_checkpointer
from .errors import map_exception_to_app_error
from .tracing import record_event, summarize_payload


class WorkflowBase(ABC):
    """Common compile/invoke behavior for workflow implementations."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self._compiled = None

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Return uncompiled StateGraph builder."""

    def traced_node(self, node_name: str, handler):
        """Wrap node handler with runtime tracing events.

        The inner wrapper accepts (state, config) per LangGraph convention.
        thread_id is read from config["configurable"]["thread_id"] — NOT from state.
        """

        async def _wrapped(state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
            configurable = (config or {}).get("configurable") or {}
            thread_id = configurable.get("thread_id", "unknown-thread")
            input_summary = summarize_payload(state)
            start = time.perf_counter()
            record_event(
                thread_id=thread_id,
                workflow_id=self.workflow_id,
                node=node_name,
                event="start",
                trace_id=thread_id,
                input_summary=input_summary,
            )

            try:
                output = await handler(state)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                record_event(
                    thread_id=thread_id,
                    workflow_id=self.workflow_id,
                    node=node_name,
                    event="error",
                    trace_id=thread_id,
                    elapsed_ms=elapsed_ms,
                    input_summary=input_summary,
                    error_summary=str(exc),
                )
                raise

            elapsed_ms = (time.perf_counter() - start) * 1000
            output_summary = summarize_payload(output)
            errors = output.get("errors", []) if isinstance(output, dict) else []
            has_error = isinstance(output, dict) and bool(errors)
            event = "error" if has_error else "end"
            error_summary = summarize_payload(errors[0]) if has_error else None
            record_event(
                thread_id=thread_id,
                workflow_id=self.workflow_id,
                node=node_name,
                event=event,
                trace_id=thread_id,
                elapsed_ms=elapsed_ms,
                input_summary=input_summary,
                output_summary=output_summary,
                error_summary=error_summary,
            )
            if has_error and isinstance(errors, list):
                first = errors[0] if errors else {}
                retryable = bool(first.get("retryable")) if isinstance(first, dict) else False
                if retryable:
                    record_event(
                        thread_id=thread_id,
                        workflow_id=self.workflow_id,
                        node=node_name,
                        event="retry",
                        trace_id=thread_id,
                        elapsed_ms=elapsed_ms,
                        retry_count=0,
                        input_summary=input_summary,
                        output_summary=output_summary,
                    )
            return output

        return _wrapped

    def compile(self, use_checkpointer: bool = True):
        graph = self.build_graph()
        if use_checkpointer:
            self._compiled = graph.compile(checkpointer=create_checkpointer())
        else:
            self._compiled = graph.compile()
        return self._compiled

    async def ainvoke(self, initial_state: dict[str, Any], thread_id: str) -> dict[str, Any]:
        if self._compiled is None:
            self.compile(use_checkpointer=True)

        config = {"configurable": {"thread_id": thread_id}}
        try:
            return await self._compiled.ainvoke(initial_state, config=config)
        except Exception as exc:
            app_error = map_exception_to_app_error(
                exc,
                trace_id=thread_id,
                failed_node=initial_state.get("failed_node"),
            )
            return {
                **initial_state,
                "status": "failed",
                "failed_node": initial_state.get("failed_node", "unknown"),
                "errors": [app_error.model_dump()],
            }

    async def astream_updates(
        self, initial_state: dict[str, Any], thread_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream per-node updates using LangGraph stream_mode='updates'.

        Each yielded item is {node_name: node_output_dict}.
        On graph exception, yields {"__error__": {...}} and stops.
        """
        if self._compiled is None:
            self.compile(use_checkpointer=True)

        config = {"configurable": {"thread_id": thread_id}}
        try:
            async for update in self._compiled.astream(initial_state, config=config, stream_mode="updates"):
                yield update
        except Exception as exc:
            app_error = map_exception_to_app_error(
                exc,
                trace_id=thread_id,
                failed_node=initial_state.get("failed_node"),
            )
            yield {"__error__": {"status": "failed", "errors": [app_error.model_dump()]}}
