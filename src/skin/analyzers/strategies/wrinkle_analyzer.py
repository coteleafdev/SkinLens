# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.wrinkle_analyzer — 주름 분석기 전략

현재 알고리즘(v1)을 BaseAnalyzer 인터페이스로 래핑합니다.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.wrinkle_texture import analyze_wrinkles


class WrinkleAnalyzerV1(BaseAnalyzer):
    """주름 분석기 v1 (현재 알고리즘).
    
    기존 analyze_wrinkles() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """주름 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
                - clahe_preprocessed: CLAHE 전처리 여부
                - bp_eye: 눈가 주름 브레이크포인트
                - bp_nasolabial: 비구름 주름 브레이크포인트
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """주름 분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터
        
        Returns:
            {eye_wrinkle_score, glabella_wrinkle_score,
             nasolabial_wrinkle_score, fine_deep_wrinkle_score}
        """
        self.validate_input(face, skin_mask, regions)
        
        # 설정에서 파라미터 로드
        clahe_preprocessed = self.get_config("clahe_preprocessed", False)
        bp_eye = self.get_config("bp_eye")
        bp_nasolabial = self.get_config("bp_nasolabial")
        
        # 기존 함수 호출
        return analyze_wrinkles(
            face=face,
            regions=regions,
            clahe_preprocessed=clahe_preprocessed,
            skin_mask=skin_mask,
            bp_eye=bp_eye,
            bp_nasolabial=bp_nasolabial,
        )
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "wrinkle_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
