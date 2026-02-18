"""API v1 router assembly."""

from fastapi import APIRouter

from .generate import router as generate_router
from .interview import router as interview_router
from .knowledge import router as knowledge_router

router = APIRouter(prefix="/api/v1", tags=["api-v1"])
router.include_router(interview_router)
router.include_router(knowledge_router)
router.include_router(generate_router)
