import asyncio

from src.application.workflows.facade import WorkflowFacade


def test_execute_workflow_interview_dispatches_with_flush(monkeypatch):
    facade = WorkflowFacade(username="alice")
    captured: dict[str, object] = {}

    async def _fake_interview_step(self, *, thread_id, speaker=None, content=None, flush=False):
        captured["thread_id"] = thread_id
        captured["speaker"] = speaker
        captured["content"] = content
        captured["flush"] = flush
        return {"status": "ok"}

    monkeypatch.setattr(WorkflowFacade, "interview_step", _fake_interview_step)

    result = asyncio.run(
        facade.execute_workflow(
            workflow_id="interview",
            payload={
                "thread_id": "tid-1",
                "speaker": "user",
                "content": "hello",
                "flush": True,
            },
        )
    )

    assert result == {"status": "ok"}
    assert captured == {
        "thread_id": "tid-1",
        "speaker": "user",
        "content": "hello",
        "flush": True,
    }
