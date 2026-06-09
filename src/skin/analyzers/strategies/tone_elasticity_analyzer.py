# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.tone_elasticity_analyzer — 톤·탄력 분석기 전략

현재 알고리즘(v1)을 BaseAnalyzer 인터페이스로 래핑합니다.
[REFACTOR] 트러블(acne) 분석을 독립된 AcneAnalyzer로 분리.
이제 톤, 탄력, 다크서클, 피지, 인지나이만 분석합니다.

[REFACTOR 2026-05-23] 완전 독립성 확보 - 내부에서 주름 분석 로직 포함
외부 wrinkle 분석기 의존성 제거로 병렬 실행 최적화
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.tone_elasticity import (
    analyze_tone,
    analyze_elasticity,
    analyze_dark_circle,
    analyze_sebum,
    analyze_perceived_age,
)
from src.skin.analyzers.wrinkle_texture import analyze_wrinkles

log = logging.getLogger(__name__)


class ToneElasticityAnalyzerV1(BaseAnalyzer):
    """톤·탄력 분석기 v1 (현재 알고리즘).
    
    기존 tone_elasticity.py 함수들을 래핑합니다.
    [REFACTOR] 트러블(acne) 분석 제거 - 독립된 AcneAnalyzer 사용.
    [REFACTOR 2026-05-23] 완전 독립성 확보 - 내부에서 주름 분석 로직 포함
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """톤·탄력 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """톤·탄력 분석 수행 (트러블 제외).
        
        [REFACTOR 2026-05-23] 완전 독립성 확보 - 외부 wrinkle 의존성 제거
        내부에서 필요한 주름 분석을 직접 수행하여 병렬 실행 가능
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터
                - stat: 피부 통계 (필요한 경우)
                - clahe_preprocessed: CLAHE 전처리된 이미지 (주름 분석에 필요)
        
        Returns:
            {skin_tone_score, dullness_score, uneven_tone_score,
             jawline_blur_score, cheek_sagging_score, elasticity_score,
             dark_circle_score,
             sebum_score,
             perceived_age}
        """
        self.validate_input(face, skin_mask, regions)
        
        results = {}
        
        # 톤 분석
        tone_result = analyze_tone(face, regions, skin_mask)
        results.update(tone_result)
        
        # [REFACTOR 2026-05-23] 내부에서 주름 분석 수행 (완전 독립성)
        # 외부 wrinkle 분석기 의존성 제거
        clahe_preprocessed = kwargs.get("clahe_preprocessed")
        if clahe_preprocessed is None:
            log.warning("clahe_preprocessed가 제공되지 않았습니다. 주름 분석 건너뜀.")
            eye_wrinkle_score = 50.0
            wrinkles = None
        else:
            # 내부에서 주름 분석 수행
            wrinkles = analyze_wrinkles(
                face, regions,
                clahe_preprocessed=clahe_preprocessed,
                skin_mask=skin_mask,
            )
            eye_wrinkle_score = wrinkles.get("eye_wrinkle_score", 50.0)
        
        # 탄력 분석 (내부에서 계산한 eye_wrinkle_score 사용)
        elasticity_result = analyze_elasticity(face, regions)
        results.update(elasticity_result)
        
        # 다크서클 분석
        dark_circle_score = analyze_dark_circle(regions)
        results["dark_circle_score"] = dark_circle_score
        
        # 피지 분석
        sebum_result = analyze_sebum(face, regions, skin_mask)
        results.update(sebum_result)
        
        # 인지나이 분석 (내부에서 계산한 wrinkles 결과 사용)
        if wrinkles is not None:
            lines_score = float(np.mean([
                wrinkles.get("fine_deep_wrinkle_score", 50.0),
                wrinkles.get("glabella_wrinkle_score", 50.0),
                wrinkles.get("nasolabial_wrinkle_score", 50.0),
            ]))
            perceived_age = analyze_perceived_age(
                face,
                eye_wrinkle_score=wrinkles.get("eye_wrinkle_score", 50.0),
                lines_score=lines_score,
            )
            results["perceived_age"] = perceived_age
        else:
            log.warning("주름 분석 결과가 없어 인지나이 계산 건너뜀.")
        
        return results
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "tone_elasticity_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
