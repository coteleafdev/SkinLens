# -*- coding: utf-8 -*-
"""
src.restoration.registry — 복원 백엔드 레지스트리 (팩토리 패턴)

복원 백엔드를 등록하고 조회하는 팩토리 클래스입니다.

[EXTENSION 2026-05-24] 향후 새로운 복원 엔진 추가를 위한 레지스트리 기능 강화.
- 인스턴스 생성 팩토리 메서드 추가
- 설정 기반 엔진 선택 메서드 추가
- 엔진 메타데이터 조회 기능 추가
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from src.restoration.base import BaseRestorer

log = logging.getLogger(__name__)


class RestorerRegistry:
    """복원 백엔드 레지스트리 (싱글톤).
    
    사용법:
        # 엔진 등록
        @RestorerRegistry.register("codeformer_v1", aliases=["codeformer", "cf"])
        class CodeFormerRestorer(BaseRestorer):
            ...
        
        # 엔진 조회
        restorer_class = RestorerRegistry.get("codeformer")
        restorer = restorer_class(config={"repo": "/path/to/codeformer"})
        
        # 설정 기반 엔진 선택
        restorer = RestorerRegistry.create_from_config(config)
    """
    
    _instance: Optional["RestorerRegistry"] = None
    _restorers: Dict[str, type] = {}
    _aliases: Dict[str, str] = {}  # 별칭 -> 정식 이름 매핑
    _metadata: Dict[str, Dict[str, Any]] = {}  # 엔진 메타데이터
    
    def __new__(cls) -> "RestorerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(
        cls,
        name: str,
        aliases: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Callable:
        """복원 백엔드 클래스 등록 데코레이터.
        
        Args:
            name: 복원 백엔드 정식 이름
            aliases: 별칭 목록
            metadata: 엔진 메타데이터 (버전, 지원 디바이스 등)
        
        Returns:
            클래스 데코레이터
        """
        def decorator(restorer_class: type) -> type:
            # BaseRestorer 상속 확인
            if not issubclass(restorer_class, BaseRestorer):
                raise TypeError(
                    f"{restorer_class.__name__}는 BaseRestorer를 상속받아야 합니다."
                )
            
            # 이미 등록된 경우 확인
            if name in cls._restorers:
                # 동일한 클래스로 다시 등록하려는 경우: 무시
                if cls._restorers[name] is restorer_class:
                    return restorer_class
                # 다른 클래스로 덮어쓰려는 경우: 경고
                log.warning("복원 백엔드 이름이 이미 등록되어 있습니다: %s (다른 클래스로 덮어씀)", name)
            
            cls._restorers[name] = restorer_class
            
            # 메타데이터 저장
            if metadata:
                cls._metadata[name] = metadata
            else:
                cls._metadata[name] = {}
            
            # 별칭 등록
            if aliases:
                for alias in aliases:
                    # 이미 등록된 별칭 확인
                    if alias in cls._aliases:
                        # 동일한 백엔드로 등록된 경우: 무시
                        if cls._aliases[alias] == name:
                            continue
                        # 다른 백엔드로 덮어쓰려는 경우: 경고
                        log.warning("별칭이 이미 등록되어 있습니다: %s (다른 백엔드로 덮어씀)", alias)
                    cls._aliases[alias] = name
            
            log.debug("복원 백엔드 등록: %s (별칭: %s)", name, aliases or [])
            return restorer_class
        
        return decorator
    
    @classmethod
    def get(cls, name_or_alias: str) -> type:
        """복원 백엔드 클래스 조회.
        
        Args:
            name_or_alias: 복원 백엔드 이름 또는 별칭
        
        Returns:
            복원 백엔드 클래스
        
        Raises:
            ValueError: 등록되지 않은 복원 백엔드인 경우
        """
        # 정식 이름 확인
        if name_or_alias in cls._restorers:
            return cls._restorers[name_or_alias]
        
        # 별칭 확인
        if name_or_alias in cls._aliases:
            formal_name = cls._aliases[name_or_alias]
            return cls._restorers[formal_name]
        
        raise ValueError(f"등록되지 않은 복원 백엔드입니다: {name_or_alias}")
    
    @classmethod
    def list_available(cls) -> list[str]:
        """사용 가능한 복원 백엔드 목록."""
        return list(cls._restorers.keys())
    
    @classmethod
    def create(
        cls,
        name_or_alias: str,
        config: Optional[Dict[str, Any]] = None
    ) -> BaseRestorer:
        """복원 백엔드 인스턴스 생성 (팩토리 메서드).
        
        Args:
            name_or_alias: 복원 엔진 이름 또는 별칭
            config: 엔진 설정
        
        Returns:
            복원 엔진 인스턴스
        
        Raises:
            ValueError: 등록되지 않은 복원 엔진인 경우
        """
        restorer_class = cls.get(name_or_alias)
        return restorer_class(config=config)
    
    @classmethod
    def create_from_config(cls, config: Dict[str, Any]) -> BaseRestorer:
        """설정에서 복원 엔진 선택 및 인스턴스 생성.
        
        Args:
            config: 전체 설정 딕셔너리
                - restorer: 엔진 이름 또는 별칭
                - restorer_config: 엔진별 설정
        
        Returns:
            복원 엔진 인스턴스
        
        Raises:
            ValueError: 엔진 이름이 없거나 등록되지 않은 경우
        """
        restorer_name = config.get("restorer", "codeformer_v1")
        restorer_config = config.get("restorer_config", {})
        
        return cls.create(restorer_name, config=restorer_config)
    
    @classmethod
    def get_metadata(cls, name_or_alias: str) -> Dict[str, Any]:
        """엔진 메타데이터 조회.
        
        Args:
            name_or_alias: 엔진 이름 또는 별칭
        
        Returns:
            메타데이터 딕셔너리
        """
        # 정식 이름 확인
        formal_name = name_or_alias
        if name_or_alias in cls._aliases:
            formal_name = cls._aliases[name_or_alias]
        
        return cls._metadata.get(formal_name, {})
    
    @classmethod
    def clear(cls) -> None:
        """레지스트리 초기화 (테스트용)."""
        cls._restorers.clear()
        cls._aliases.clear()
        cls._metadata.clear()
