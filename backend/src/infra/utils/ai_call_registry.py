"""
AI调用注册表 - 记录每个AI调用的标记和位置信息
"""

# AI调用标记到位置的映射表
AI_CALL_REGISTRY = {
    # 知识提取模块
    "extract_character_profile": "backend/src/application/knowledge/extraction/extractor/character_profile_extractor.py::CharacterProfileExtractor.extract()",
    "extract_event_summaries": "backend/src/application/knowledge/extraction/extractor/event_summary_extractor.py::EventSummaryExtractor.extract_summaries()",
    "extract_life_events": "backend/src/application/knowledge/extraction/extractor/life_event_extractor.py::LifeEventExtractor.extract()",
    
    # 知识精炼模块
    "refine_personality": "backend/src/application/knowledge/refinement/refiner/character_profile_refiner.py::CharacterProfileRefiner._refine_personality()",
    "refine_worldview": "backend/src/application/knowledge/refinement/refiner/character_profile_refiner.py::CharacterProfileRefiner._refine_worldview()",
    "refine_aliases": "backend/src/application/knowledge/refinement/refiner/character_profile_refiner.py::CharacterProfileRefiner._refine_aliases()",
    "summarize_event_details": "backend/src/application/knowledge/refinement/refiner/event_details_refiner.py::EventDetailsRefiner._summarize_event_details()",
    "refine_uncertain_events": "backend/src/application/knowledge/refinement/refiner/uncertain_event_refiner.py::UncertainEventRefiner.refine_events()",
    "refine_precise_events": "backend/src/application/knowledge/refinement/refiner/event_refiner.py::EventRefiner.refine_events()",
    
    # 采访模块
    "extract_from_database_events": "backend/src/application/interview/actuator/pending_event_initializer.py::PendingEventInitializer._extract_from_database_events()",
    "extract_from_chunks": "backend/src/application/interview/actuator/pending_event_initializer.py::PendingEventInitializer._extract_from_chunks()",
    "extract_dialogue_summaries": "backend/src/application/interview/actuator/summary_processor.py::SummaryProcessor.extract()",
    "extract_event_supplements": "backend/src/application/interview/actuator/supplement_extractor.py::SupplementExtractor.extract()::process_supplements()",
    "analyze_interview_emotions": "backend/src/application/interview/actuator/supplement_extractor.py::SupplementExtractor.extract()::process_suggestions()",
    "extract_pending_event_details": "backend/src/application/interview/actuator/pending_event_processor.py::PendingEventProcessor._extract_pending_event_details()",
    "merge_pending_event_content": "backend/src/application/interview/actuator/pending_event_processor.py::PendingEventProcessor._merge_content()",
    
    # 生成模块
    "generate_memoir": "backend/src/application/generate/generator/memoir_generator.py::MemoirGenerator.generate_memoir()",
    "select_significant_events": "backend/src/application/generate/generator/timeline_generator.py::TimelineGenerator.select_events()",
    "generate_timeline_entries": "backend/src/application/generate/generator/timeline_generator.py::TimelineGenerator.generate_timeline_entries()",
}


def get_call_location(tag: str) -> str:
    """
    根据标记获取调用位置
    
    Args:
        tag: AI调用标记（如 "extract_character_profile"）
        
    Returns:
        调用位置字符串，如果未找到返回 "未知位置"
    """
    return AI_CALL_REGISTRY.get(tag, "未知位置")
