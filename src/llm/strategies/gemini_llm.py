# -*- coding: utf-8 -*-
"""
src.llm.strategies.gemini_llm — Gemini LLM 구현

현재 Gemini LLM 알고리즘을 BaseLLM 인터페이스로 래핑합니다.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.llm.base import BaseLLM
from src.llm.llm_skin_report import LlmSkinReporter

log = logging.getLogger(__name__)


class GeminiLLM(BaseLLM):
    """Gemini LLM v1 (현재 알고리즘).
    
    기존 LlmSkinReporter를 래핑합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Gemini LLM v1 초기화.
        
        Args:
            config: LLM 설정
                - api_key: API 키
                - model: 모델 이름 (기본 "gemini-2.5-flash")
                - timeout_sec: 타임아웃 (초)
                - max_retries: 최대 재시도 횟수
        """
        super().__init__(config)
        
        # LlmSkinReporter 초기화
        self._reporter = LlmSkinReporter(
            api_key=self.get_config("api_key"),
            model_name=self.get_config("model", "gemini-2.5-flash"),
            max_retries=self.get_config("max_retries", 3),
        )
    
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
                - provide_scores: 점수 제공 여부 (기본 True)
                - dual_mode: 듀얼 이미지 모드 여부
                - original_measurements: 원본 측정 항목 (듀얼 모드)
                - restored_image_path: 복원 이미지 경로 (듀얼 모드)
        
        Returns:
            보고서 딕셔너리
        """
        provide_scores = kwargs.get("provide_scores", True)
        dual_mode = kwargs.get("dual_mode", False)
        
        if dual_mode:
            # 듀얼 이미지 모드
            original_measurements = kwargs.get("original_measurements", {})
            restored_image_path = kwargs.get("restored_image_path")
            
            if not original_measurements or not restored_image_path:
                raise ValueError("듀얼 모드에서는 original_measurements와 restored_image_path가 필요합니다.")
            
            return self._reporter.generate_report_from_dual_images(
                orig_image_path=image_path,
                ideal_image_path=restored_image_path,
                orig_measurements_report=original_measurements,
                ideal_measurements_report=measurements,
                orig_overall_score=original_measurements.get("overall_score", 0),
                orig_perceived_age=original_measurements.get("perceived_age", 0),
                ideal_overall_score=measurements.get("overall_score", 0),
                ideal_perceived_age=measurements.get("perceived_age", 0),
                provide_scores=provide_scores,
            )
        else:
            # 단일 이미지 모드
            return self._reporter.generate_report(
                image_path=image_path,
                measurements_report=measurements,
                provide_scores=provide_scores,
            )
    
    def get_name(self) -> str:
        """LLM 이름."""
        return "gemini_v1"
    
    def get_version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
