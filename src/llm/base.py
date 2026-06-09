# -*- coding: utf-8 -*-
"""

[DEPRECATED] 이 모듈은 병렬 LLM 추상화의 일부입니다. 외부 소비자가 없으며,
활성 경로는 src.llm.llm_providers.LLMProvider / create_provider() 입니다(=표준).
신규 코드는 본 모듈/클래스를 사용하지 마세요. 제거는 사용처 재확인 후 별도 진행 권장.
src.llm.base — LLM 추상 인터페이스

Strategy Pattern을 사용하여 다양한 LLM을 유연하게 교체할 수 있습니다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional


class BaseLLM(ABC):
    """LLM 추상 기반 클래스."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """LLM 초기화.
        
        Args:
            config: LLM 설정
                - api_key_env: API 키 환경 변수명
                - model: 모델 이름
                - timeout_sec: 타임아웃 (초)
                - max_retries: 최대 재시도 횟수
        """
        self.config = config or {}
    
    @abstractmethod
    def generate_report(
        self,
        image_path: str | Path,
        measurements: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """피부 분석 보고서 생성.
        
        Args:
            image_path: 이미지 경로
            measurements: 측정 항목 딕셔너리
            **kwargs: 추가 파라미터
                - provide_scores: 점수 제공 여부
                - dual_mode: 듀얼 이미지 모드 여부
                - original_measurements: 원본 측정 항목 (듀얼 모드)
                - restored_image_path: 복원 이미지 경로 (듀얼 모드)
        
        Returns:
            보고서 딕셔너리
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """LLM 이름."""
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """알고리즘 버전."""
        pass
    
    def validate_config(self, required_keys: list[str]) -> None:
        """설정 유효성 검사.
        
        Args:
            required_keys: 필수 키 목록
        
        Raises:
            ValueError: 필수 키가 없는 경우
        """
        missing_keys = [key for key in required_keys if key not in self.config]
        if missing_keys:
            raise ValueError(f"필수 설정 키가 없습니다: {missing_keys}")
    
    def get_config(self, key: str, default=None):
        """설정 값을 가져옵니다.
        
        Args:
            key: 설정 키
            default: 기본값
        
        Returns:
            설정 값 또는 기본값
        """
        return self.config.get(key, default)
