# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.acne_analyzer — 트러블 분석기 전략

현재 알고리즘(v1)을 BaseAnalyzer 인터페이스로 래핑합니다.
tone_elasticity.py에서 트러블 관련 로직을 독립시켰습니다.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.tone_elasticity import analyze_acne_marks


class AcneAnalyzerV1(BaseAnalyzer):
    """트러블 분석기 v1 (현재 알고리즘).
    
    기존 analyze_acne_marks() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """트러블 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
                - bp_acne: 여드름 브레이크포인트
                - bp_pap: PIH 브레이크포인트
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """트러블 분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리 (사용하지 않음)
            **kwargs: 추가 파라미터
                - stat: 피부 통계 (필수)
        
        Returns:
            {"acne_score": float, "post_acne_pigment_score": float}
        """
        self.validate_input(face, skin_mask, regions)
        
        stat = kwargs.get("stat")
        if stat is None:
            raise ValueError("stat 파라미터가 필요합니다.")
        
        # 설정에서 브레이크포인트 로드
        bp_acne = self.get_config("bp_acne")
        bp_pap = self.get_config("bp_pap")
        
        # 기존 함수 호출
        result = analyze_acne_marks(
            face=face,
            skin_mask=skin_mask,
            stat=stat,
            bp_acne=bp_acne,
            bp_pap=bp_pap,
        )
        
        # focal_lesion 직교 신호 전달 (analyze_acne_marks에서 이미 계산됨)
        # tone_elasticity.py에서 focal_lesion을 density_score로 반환하도록 수정함
        # 여기서는 그 값을 그대로 전달
        if "focal_lesion" not in result:
            # fallback: acne_score를 사용 (이전 버전 호환성)
            result["focal_lesion"] = result.get("acne_score", 50.0)
        
        return result
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "acne_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
