# -*- coding: utf-8 -*-
"""
src.skin.analyzers.base — 분석 알고리즘 추상 기반 클래스

모든 분석 알고리즘은 BaseAnalyzer를 상속받아야 합니다.
이를 통해 알고리즘 교체 및 A/B 테스트가 용이해집니다.

사용 예:
    class MyAnalyzer(BaseAnalyzer):
        def analyze(self, face, skin_mask, regions, **kwargs):
            # 분석 로직
            return {"score": 75.0}
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import numpy as np


class BaseAnalyzer(ABC):
    """분석 알고리즘 추상 기반 클래스.
    
    모든 분석기는 이 클래스를 상속받아야 합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """분석기 초기화.
        
        Args:
            config: 분석기 설정 딕셔너리. 알고리즘별 파라미터 포함.
        """
        self.config = config or {}
    
    @abstractmethod
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터 (stat, debug 등)
        
        Returns:
            분석 결과 딕셔너리 (예: {"melasma_score": 75.0, "freckle_score": 80.0})
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """분석기 이름 (예: "pigmentation_v1")."""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """알고리즘 버전 (예: "1.0.0")."""
        pass
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """설정 값 조회.
        
        Args:
            key: 설정 키
            default: 기본값
        
        Returns:
            설정 값
        """
        return self.config.get(key, default)
    
    def validate_input(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
    ) -> None:
        """입력 유효성 검증.
        
        Args:
            face: 얼굴 영상
            skin_mask: 피부 마스크
            regions: ROI 영역
        
        Raises:
            ValueError: 입력이 유효하지 않은 경우
        """
        if face is None or face.size == 0:
            raise ValueError("face가 비어있습니다.")
        if skin_mask is None or skin_mask.size == 0:
            raise ValueError("skin_mask가 비어있습니다.")
        if not isinstance(regions, dict) or len(regions) == 0:
            raise ValueError("regions가 비어있습니다.")
