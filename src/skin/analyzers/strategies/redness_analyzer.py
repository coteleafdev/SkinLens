# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.redness_analyzer — 홍조 분석기 전략

현재 알고리즘(v1)을 BaseAnalyzer 인터페이스로 래핑합니다.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.redness import analyze_redness


class RednessAnalyzerV1(BaseAnalyzer):
    """홍조 분석기 v1 (현재 알고리즘).
    
    기존 analyze_redness() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """홍조 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
                - clahe_clip: CLAHE clip limit
                - clahe_tile: CLAHE tile grid size
                - bp_redness: 홍조 브레이크포인트
                - bp_pie: PIE 브레이크포인트
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """홍조 분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터
                - stat: 피부 통계 (필수)
        
        Returns:
            {"redness_score": float, "post_inflammatory_erythema_score": float}
        """
        self.validate_input(face, skin_mask, regions)
        
        stat = kwargs.get("stat")
        if stat is None:
            raise ValueError("stat 파라미터가 필요합니다.")
        
        # 설정에서 파라미터 로드
        clahe_clip = self.get_config("clahe_clip", 2.0)
        clahe_tile = self.get_config("clahe_tile", (8, 8))
        bp_redness = self.get_config("bp_redness")
        bp_pie = self.get_config("bp_pie")
        
        # 기존 함수 호출
        return analyze_redness(
            face=face,
            skin_mask=skin_mask,
            regions=regions,
            stat=stat,
            clahe_clip=clahe_clip,
            clahe_tile=clahe_tile,
            bp_redness=bp_redness,
            bp_pie=bp_pie,
        )
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "redness_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
