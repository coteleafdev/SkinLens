# -*- coding: utf-8 -*-
"""
src.skin.analyzers.registry — 분석기 등록 및 팩토리

분석기 클래스를 등록하고 인스턴스를 생성하는 레지스트리입니다.

사용 예:
    # 분석기 등록
    @AnalyzerRegistry.register("pigmentation_v1")
    class PigmentationAnalyzerV1(BaseAnalyzer):
        ...
    
    # 분석기 생성
    analyzer = AnalyzerRegistry.get("pigmentation_v1", config={...})
    
    # 측정항목 기반 분석기 생성
    analyzer = AnalyzerRegistry.get_for_measurement("melasma_score", config={...})
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Type

from src.skin.analyzers.base import BaseAnalyzer

log = logging.getLogger(__name__)


class AnalyzerRegistry:
    """분석기 등록 및 팩토리 클래스."""
    
    _analyzers: Dict[str, Type[BaseAnalyzer]] = {}
    _aliases: Dict[str, str] = {}  # 별칭 매핑
    
    @classmethod
    def register(
        cls,
        name: str,
        aliases: Optional[list[str]] = None,
    ) -> Callable[[Type[BaseAnalyzer]], Type[BaseAnalyzer]]:
        """분석기 등록 데코레이터.
        
        Args:
            name: 분석기 고유 이름 (예: "pigmentation_v1")
            aliases: 별칭 목록 (예: ["pigmentation", "pig_v1"])
        
        Returns:
            데코레이터 함수
        
        사용 예:
            @AnalyzerRegistry.register("pigmentation_v1", aliases=["pigmentation"])
            class PigmentationAnalyzerV1(BaseAnalyzer):
                ...
        """
        def decorator(analyzer_class: Type[BaseAnalyzer]) -> Type[BaseAnalyzer]:
            # 이미 등록된 경우 확인
            if name in cls._analyzers:
                # 동일한 클래스로 다시 등록하려는 경우: 무시
                if cls._analyzers[name] is analyzer_class:
                    return analyzer_class
                # 다른 클래스로 덮어쓰려는 경우: 경고
                log.warning("분석기 이름이 이미 등록되어 있습니다: %s (다른 클래스로 덮어씀)", name)
            
            cls._analyzers[name] = analyzer_class
            
            # 별칭 등록
            if aliases:
                for alias in aliases:
                    # 이미 등록된 별칭 확인
                    if alias in cls._aliases:
                        # 동일한 분석기로 등록된 경우: 무시
                        if cls._aliases[alias] == name:
                            continue
                        # 다른 분석기로 덮어쓰려는 경우: 경고
                        log.warning("별칭이 이미 등록되어 있습니다: %s (다른 분석기로 덮어씀)", alias)
                    cls._aliases[alias] = name
            
            log.debug("분석기 등록: %s (별칭: %s)", name, aliases or [])
            return analyzer_class
        
        return decorator
    
    @classmethod
    def get(
        cls,
        name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> BaseAnalyzer:
        """분석기 인스턴스 생성.
        
        Args:
            name: 분석기 이름 또는 별칭
            config: 분석기 설정
        
        Returns:
            분석기 인스턴스
        
        Raises:
            ValueError: 알 수 없는 분석기인 경우
        """
        # 별칭 확인
        actual_name = cls._aliases.get(name, name)
        
        if actual_name not in cls._analyzers:
            available = ", ".join(cls.list_available())
            raise ValueError(
                f"알 수 없는 분석기: {name}. "
                f"사용 가능한 분석기: {available}"
            )
        
        analyzer_class = cls._analyzers[actual_name]
        return analyzer_class(config)
    
    @classmethod
    def list_available(cls) -> list[str]:
        """사용 가능한 분석기 목록 반환.
        
        Returns:
            분석기 이름 목록
        """
        return list(cls._analyzers.keys())
    
    @classmethod
    def list_aliases(cls) -> Dict[str, str]:
        """별칭 매핑 반환.
        
        Returns:
            {별칭: 실제 이름} 딕셔너리
        """
        return cls._aliases.copy()
    
    @classmethod
    def unregister(cls, name: str) -> None:
        """분석기 등록 해제.
        
        Args:
            name: 분석기 이름 또는 별칭
        """
        actual_name = cls._aliases.get(name, name)
        
        if actual_name in cls._analyzers:
            del cls._analyzers[actual_name]
            log.info("분석기 등록 해제: %s", actual_name)
        
        # 관련 별칭 제거
        aliases_to_remove = [k for k, v in cls._aliases.items() if v == actual_name]
        for alias in aliases_to_remove:
            del cls._aliases[alias]
    
    @classmethod
    def clear(cls) -> None:
        """모든 분석기 등록 해제 (테스트용)."""
        cls._analyzers.clear()
        cls._aliases.clear()
        log.info("모든 분석기 등록 해제")
    
    @classmethod
    def _load_measurement_analyzer_mapping(cls) -> Dict[str, str]:
        """config.json에서 측정항목 → 분석기 매핑 로드.
        
        Returns:
            {측정항목: 분석기 이름} 딕셔너리
        """
        try:
            from src.scoring.config._config import _load_scoring_config
            config = _load_scoring_config()
            if config and "measurement_analyzers" in config:
                return config["measurement_analyzers"]
        except Exception as e:
            log.warning(f"측정항목 분석기 매핑 로드 실패: {e}")
        return {}
    
    @classmethod
    def get_for_measurement(
        cls,
        measurement_key: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> BaseAnalyzer:
        """측정항목 기반 분석기 인스턴스 생성.
        
        Args:
            measurement_key: 측정항목 키 (예: "melasma_score")
            config: 분석기 설정
        
        Returns:
            분석기 인스턴스
        
        Raises:
            ValueError: 측정항목에 매핑된 분석기가 없는 경우
        """
        mapping = cls._load_measurement_analyzer_mapping()
        
        if measurement_key not in mapping:
            available = ", ".join(mapping.keys())
            raise ValueError(
                f"측정항목에 매핑된 분석기가 없습니다: {measurement_key}. "
                f"사용 가능한 측정항목: {available}"
            )
        
        analyzer_name = mapping[measurement_key]
        return cls.get(analyzer_name, config)
