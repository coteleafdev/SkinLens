# -*- coding: utf-8 -*-
"""
src.llm.registry — LLM 레지스트리 (팩토리 패턴)

LLM을 등록하고 조회하는 팩토리 클래스입니다.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)


class LLMRegistry:
    """LLM 레지스트리 (싱글톤)."""
    
    _instance: Optional["LLMRegistry"] = None
    _llms: Dict[str, type] = {}
    _aliases: Dict[str, str] = {}  # 별칭 -> 정식 이름 매핑
    
    def __new__(cls) -> "LLMRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, name: str, aliases: Optional[list[str]] = None) -> Callable:
        """LLM 클래스 등록 데코레이터.
        
        Args:
            name: LLM 정식 이름
            aliases: 별칭 목록
        
        Returns:
            클래스 데코레이터
        """
        def decorator(llm_class: type) -> type:
            # 이미 등록된 경우 확인
            if name in cls._llms:
                # 동일한 클래스로 다시 등록하려는 경우: 무시
                if cls._llms[name] is llm_class:
                    return llm_class
                # 다른 클래스로 덮어쓰려는 경우: 경고
                log.warning("LLM 이름이 이미 등록되어 있습니다: %s (다른 클래스로 덮어씀)", name)
            
            cls._llms[name] = llm_class
            
            # 별칭 등록
            if aliases:
                for alias in aliases:
                    # 이미 등록된 별칭 확인
                    if alias in cls._aliases:
                        # 동일한 LLM으로 등록된 경우: 무시
                        if cls._aliases[alias] == name:
                            continue
                        # 다른 LLM으로 덮어쓰려는 경우: 경고
                        log.warning("별칭이 이미 등록되어 있습니다: %s (다른 LLM으로 덮어씀)", alias)
                    cls._aliases[alias] = name
            
            log.debug("LLM 등록: %s (별칭: %s)", name, aliases or [])
            return llm_class
        
        return decorator
    
    @classmethod
    def get(cls, name_or_alias: str) -> type:
        """LLM 클래스 조회.
        
        Args:
            name_or_alias: LLM 이름 또는 별칭
        
        Returns:
            LLM 클래스
        
        Raises:
            ValueError: 등록되지 않은 LLM인 경우
        """
        # 정식 이름 확인
        if name_or_alias in cls._llms:
            return cls._llms[name_or_alias]
        
        # 별칭 확인
        if name_or_alias in cls._aliases:
            formal_name = cls._aliases[name_or_alias]
            return cls._llms[formal_name]
        
        raise ValueError(f"등록되지 않은 LLM입니다: {name_or_alias}")
    
    @classmethod
    def list_available(cls) -> list[str]:
        """사용 가능한 LLM 목록."""
        return list(cls._llms.keys())
    
    @classmethod
    def clear(cls) -> None:
        """레지스트리 초기화 (테스트용)."""
        cls._llms.clear()
        cls._aliases.clear()
