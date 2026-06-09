# -*- coding: utf-8 -*-
"""

[DEPRECATED] 이 모듈은 병렬 LLM 추상화의 일부입니다. 외부 소비자가 없으며,
활성 경로는 src.llm.llm_providers.LLMProvider / create_provider() 입니다(=표준).
신규 코드는 본 모듈/클래스를 사용하지 마세요. 제거는 사용처 재확인 후 별도 진행 권장.
src.llm.strategies — LLM 전략 클래스 패키지

각 LLM 구현이 포함됩니다.
"""
from __future__ import annotations

from src.llm.strategies.gemini_llm import GeminiLLM

__all__ = [
    "GeminiLLM",
]
