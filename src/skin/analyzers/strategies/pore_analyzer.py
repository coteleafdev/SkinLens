# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.pore_analyzer — 모공 분석기 전략

현재 알고리즘(v1)을 BaseAnalyzer 인터페이스로 래핑합니다.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.pore import analyze_pores


class PoreAnalyzerV1(BaseAnalyzer):
    """모공 분석기 v1 (현재 알고리즘).
    
    기존 analyze_pores() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """모공 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
                - blob_params: Blob 탐지 파라미터
                - clahe_clip: CLAHE clip limit
                - clahe_tile: CLAHE tile grid size
                - bp_pore_density: 모공 밀도 브레이크포인트
                - bp_sagging_lap: 모공 늘어짐 브레이크포인트
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """모공 분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255) - 사용하지 않음
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터
        
        Returns:
            {"pore_size_score": float, "pore_count": int, "pore_sagging_score": float}
        """
        self.validate_input(face, skin_mask, regions)
        
        # 설정에서 파라미터 로드
        blob_params = self.get_config("blob_params", {})
        clahe_clip = self.get_config("clahe_clip", 2.2)
        clahe_tile = self.get_config("clahe_tile", (8, 8))
        bp_pore_density = self.get_config("bp_pore_density")
        bp_sagging_lap = self.get_config("bp_sagging_lap")
        
        # 기존 함수 호출
        return analyze_pores(
            face=face,
            regions=regions,
            blob_params=blob_params,
            clahe_clip=clahe_clip,
            clahe_tile=clahe_tile,
            bp_pore_density=bp_pore_density,
            bp_sagging_lap=bp_sagging_lap,
        )
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "pore_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
