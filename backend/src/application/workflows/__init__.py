"""Application workflows (LangGraph orchestration layer).

Exports are loaded lazily to avoid importing heavyweight dependencies at module import
time (for example vector/embedding backends used by generate runtime).
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "WorkflowFacade": (".facade", "WorkflowFacade"),
    "InterviewWorkflow": (".interview", "InterviewWorkflow"),
    "InterviewWorkflowRuntime": (".interview", "InterviewWorkflowRuntime"),
    "run_interview_step": (".interview", "run_interview_step"),
    "KnowledgeWorkflow": (".knowledge", "KnowledgeWorkflow"),
    "KnowledgeWorkflowRuntime": (".knowledge", "KnowledgeWorkflowRuntime"),
    "run_knowledge_file": (".knowledge", "run_knowledge_file"),
    "GenerateWorkflow": (".generate", "GenerateWorkflow"),
    "GenerateWorkflowRuntime": (".generate", "GenerateWorkflowRuntime"),
    "run_generate": (".generate", "run_generate"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, symbol = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, symbol)
    globals()[name] = value
    return value
