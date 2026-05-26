# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.pigmentation_analyzer — 색소 분석기 전략

현재 알고리즘(v1)을 BaseAnalyzer 인터페이스로 래핑합니다.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.pigmentation import analyze_pigmentation


class PigmentationAnalyzerV1(BaseAnalyzer):
    """색소 분석기 v1 (현재 알고리즘).
    
    기존 analyze_pigmentation() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """색소 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
                - bp_melasma: 기미 브레이크포인트
                - bp_freckle_count: 주근깨 개수 브레이크포인트
                - bp_pih: PIH 브레이크포인트
                - freckle_params: 주근깨 파라미터
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """색소 분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리 (사용하지 않음)
            **kwargs: 추가 파라미터
                - stat: 피부 통계 (필수)
        
        Returns:
            {"melasma_score": float, "freckle_score": float, "pih_score": float}
        """
        self.validate_input(face, skin_mask, regions)
        
        stat = kwargs.get("stat")
        if stat is None:
            raise ValueError("stat 파라미터가 필요합니다.")
        
        # 설정에서 브레이크포인트 로드
        bp_melasma = self.get_config("bp_melasma")
        bp_freckle_count = self.get_config("bp_freckle_count")
        bp_pih = self.get_config("bp_pih")
        freckle_params = self.get_config("freckle_params")
        
        # 기존 함수 호출
        return analyze_pigmentation(
            face=face,
            skin_mask=skin_mask,
            stat=stat,
            bp_melasma=bp_melasma,
            bp_freckle_count=bp_freckle_count,
            bp_pih=bp_pih,
            freckle_params=freckle_params,
        )
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "pigmentation_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"


class PigmentationAnalyzerV2(BaseAnalyzer):
    """색소 분석기 v2 (새로운 알고리즘 예시).
    
    딥러닝 기반 색소 분석 예시입니다.
    실제 구현 시에는 모델 로드 및 추론 로직이 필요합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """색소 분석기 v2 초기화.
        
        Args:
            config: 분석기 설정
                - model_path: 딥러닝 모델 경로
                - confidence_threshold: 신뢰도 임계값
        """
        super().__init__(config)
        # 실제 구현 시에는 여기서 모델 로드
        # self.model = load_model(self.get_config("model_path"))
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """색소 분석 수행 (딥러닝 기반).
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터
        
        Returns:
            {"melasma_score": float, "freckle_score": float, "pih_score": float}
        """
        self.validate_input(face, skin_mask, regions)
        
        # 실제 구현 시에는 딥러닝 추론
        # predictions = self.model.predict(face, skin_mask)
        
        # 예시: 하드코딩된 결과 (실제 구현 시 제거)
        return {
            "melasma_score": 80.0,
            "freckle_score": 85.0,
            "pih_score": 75.0,
        }
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "pigmentation_v2"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "2.0.0"
