# -*- coding: utf-8 -*-
"""
src.llm.strategies.register_llms — LLM 자동 등록

앱 시작 시 이 모듈을 import하여 모든 LLM을 레지스트리에 등록합니다.

사용 예:
    from src.llm.strategies.register_llms import register_all_llms
    register_all_llms()
"""
from __future__ import annotations

import logging

from src.llm.registry import LLMRegistry
from src.llm.strategies.gemini_llm import GeminiLLM

log = logging.getLogger(__name__)


def register_all_llms() -> None:
    """모든 LLM을 레지스트리에 등록."""
    # Gemini 등록
    LLMRegistry.register("gemini_v1", aliases=["gemini", "gemini_flash", "gemini_pro"])(GeminiLLM)
    
    log.info("모든 LLM 등록 완료: %s", LLMRegistry.list_available())


# 모듈 import 시 자동 등록 (선택적)
# register_all_llms()
