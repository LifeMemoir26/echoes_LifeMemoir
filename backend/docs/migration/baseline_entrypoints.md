# Baseline Entrypoints

## Purpose
This document records the current (legacy) orchestration entrypoints before migrating to LangGraph.
It is the baseline reference for behavior parity checks.

## Current Primary Flows

### Knowledge flow
- Entry service: `src.services.knowledge.knowledge_service.KnowledgeService`
- Convenience API: `src.services.knowledge.knowledge_service.process_knowledge_file`
- Script entry: `backend/scripts/test_knowledge_extract.py`

### Interview flow
- Entry service: `src.services.interview.interview_service.InterviewService`
- Convenience API:
  - `src.services.interview.interview_service.create_interview_session`
  - `src.services.interview.interview_service.add_dialogue`
  - `src.services.interview.interview_service.get_interview_info`
- Script entry: `backend/scripts/test_interview_service.py`

### Generate flow
- Entry services:
  - `src.services.generate.generation_service.GenerationTimelineService`
  - `src.services.generate.generation_service.GenerationMemoirService`
- Convenience API:
  - `src.services.generate.generation_service.generate_timeline`
  - `src.services.generate.generation_service.generate_memoir`
- Script entry:
  - `backend/scripts/test_timeline_generation.py`
  - `backend/scripts/test_memoir_generation.py`

## Notes
- Legacy flow orchestration is currently scattered in `src/services/**`.
- Global concurrency behavior is managed by `src.infrastructure.llm.concurrency_manager`.
