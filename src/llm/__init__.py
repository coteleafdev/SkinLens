# -*- coding: utf-8 -*-
"""
src.llm — LLM 패키지

Strategy Pattern을 사용하여 다양한 LLM을 유연하게 교체할 수 있습니다.
[REFACTOR P3] PromptManager 추가: 프롬프트 버전 관리 및 A/B 테스트 지원.

[추상화 안내] 활성/표준 LLM 추상화는 src.llm.llm_providers.LLMProvider 입니다.
아래 export(BaseLLM/LLMRegistry/register_all_llms/PromptManager)는 하위호환용이며 deprecated.
"""
from __future__ import annotations

from src.llm.base import BaseLLM
from src.llm.registry import LLMRegistry
from src.llm.strategies.register_llms import register_all_llms
from src.llm.prompt_manager import PromptManager, get_prompt_manager

__all__ = [
    "BaseLLM",
    "LLMRegistry",
    "register_all_llms",
    "PromptManager",
    "get_prompt_manager",
]
