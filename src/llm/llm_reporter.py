"""llm_reporter.py — LLM Skin Reporter 핵심 모듈 (Mixin 합성 파사드).

[구조변경] 2,155 LOC God 클래스를 생성/파싱 Mixin + 공유 모듈로 분리.
공개 클래스 LlmSkinReporter 및 import 경로 불변. 메서드 본문 무수정.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.llm.llm_config import (
    get_default_model,
    get_default_max_retries,
    get_default_provider,
)
from src.llm.llm_model_manager import (
    list_available_models,
    _load_llm_api_key,
)
from src.llm.llm_metadata import _get_metric_meta
from src.llm.llm_formatters import (
    _grade_label,
    _analyze_opinion_sentiment,
    _adjust_score_based_on_opinion,
    MetricOpinion,
    SkinLLMReport,
)
from src.llm.llm_prompt_builder import (
    _build_system_prompt,
    _build_user_prompt,
    _build_dual_image_prompt,
    _build_reference_guided_prompt,
)
from src.llm.llm_providers import create_provider, LLMProvider
from src.skin.core.config_parser import get_llm_api_config, get_measurement_count

log = logging.getLogger(__name__)
from src.llm.llm_reporter_common import (
    _METRIC_META,
    _get_metric_trust_level,
    _apply_advanced_score_correction,
    _apply_score_correction,
    _monitor_score_difference,
    _is_response_truncated,
    _identify_missing_fields,
    _build_field_completion_prompt,
    _merge_json_responses,
)
from src.llm.llm_generation import ReportGenerationMixin
from src.llm.llm_parsing import ResponseParsingMixin


class LlmSkinReporter(ReportGenerationMixin, ResponseParsingMixin):
    """
    원본 이미지 + 측정 점수 → LLM (LLM Vision) → 소견 생성

    Parameters
    ----------
    api_key : str, optional
        Google AI Studio API 키 (https://aistudio.google.com/app/apikey)
        지정하지 않으면 config/secrets.json에서 자동 로드합니다.
    model_name : str
        사용할 LLM 모델. Vision 기능이 있는 모델만 가능.
        기본값: "gemini-2.5-flash"
    max_retries : int
        API 호출 실패 시 재시도 횟수
    retry_delay : float
        재시도 간격(초)
    progress_callback : Callable[[str], None], optional
        진행 상황을 전달받을 콜백 함수
    """


    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        provider: Optional[str] = None,  # 프로바이더 이름 (gemini, openai, etc.)
        product_repository: Optional[Any] = None,  # ProductRepository 의존성 주입
    ) -> None:
        # config.json에서 기본값 로드
        if model_name is None:
            model_name = get_default_model()
        if max_retries is None:
            max_retries = get_default_max_retries()
        if provider is None:
            provider = get_default_provider()
        
        # 모델명에서 LLM 제공자 이름 추출 (예: gemini-2.5-flash-image → gemini)
        self.model_name = model_name
        # provider가 지정되지 않으면 모델명에서 추출 (fallback)
        if provider is None:
            # [FIX P1-12] 알려진 모델명 패턴 매핑
            model_to_provider = {
                "gemini": "gemini",
                "gpt": "openai",
                "claude": "anthropic",
                "openai": "openai",
                "anthropic": "anthropic",
            }
            # 경로에서 파일명 추출 (예: models/gemini-2.5-pro → gemini-2.5-pro)
            base_name = model_name.split('/')[-1] if '/' in model_name else model_name
            # 파일명에서 제공자 추출 (예: gemini-2.5-pro → gemini)
            extracted = base_name.split('-')[0] if '-' in base_name else base_name
            provider = model_to_provider.get(extracted.lower(), extracted)
            log.warning("LLM provider가 지정되지 않아 모델명에서 추출했습니다: %s → %s. config.json에 provider 필드를 추가하는 것을 권장합니다.", model_name, provider)
        self.provider_name = provider
        
        # API 설정 로드
        api_config = get_llm_api_config()
        
        # 점수 보정 설정 로그 출력
        score_correction_config = api_config.get("score_correction", {})
        score_correction_enabled = score_correction_config.get("enabled", False)
        score_correction_mode = score_correction_config.get("mode", "hybrid")
        analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
        llm_weight = score_correction_config.get("llm_weight", 0.3)
        
        dynamic_weighting_config = score_correction_config.get("dynamic_weighting", {})
        dynamic_weighting_enabled = dynamic_weighting_config.get("enabled", False)
        score_difference_threshold = dynamic_weighting_config.get("score_difference_threshold", 15.0)
        
        monitoring_config = score_correction_config.get("monitoring", {})
        warning_threshold = monitoring_config.get("warning_threshold", 20.0)
        critical_threshold = monitoring_config.get("critical_threshold", 40.0)
        
        log.info(
            f"[LLM 설정] 점수 보정: enabled={score_correction_enabled}, mode={score_correction_mode}, "
            f"analyzer_weight={analyzer_weight}, llm_weight={llm_weight}"
        )
        log.info(
            f"[LLM 설정] 동적 가중치: enabled={dynamic_weighting_enabled}, "
            f"score_difference_threshold={score_difference_threshold}"
        )
        log.info(
            f"[LLM 설정] 모니터링: warning_threshold={warning_threshold}, critical_threshold={critical_threshold}"
        )

        # api_key가 지정되지 않으면 secrets.json에서 로드
        if api_key is None:
            api_key = _load_llm_api_key(provider)

        if not api_key:
            raise ValueError("LLM API 키가 설정되지 않았습니다. config.secrets.json 또는 환경 변수를 확인하세요.")
        
        # 프로바이더 생성 및 설정
        self._provider: LLMProvider = create_provider(
            provider_name=provider,
            api_key=api_key,
            model_name=model_name,
            temperature=api_config["temperature"],
            max_output_tokens=api_config["max_output_tokens_single"],
        )
        self._provider.configure()
        
        # 사용 가능한 모델 목록 출력
        try:
            available_models = self._provider.list_models()
            if available_models:
                log.info(f"[LLM] 사용 가능한 모델 {len(available_models)}개 중 '{model_name}' 사용")
                log.debug(f"[LLM] 사용 가능한 모델 목록: {', '.join(available_models[:5])}...")
        except Exception as e:
            log.warning(f"[LLM] 사용 가능한 모델 목록 조회 실패: {e}")
        
        log.info(f"[LLM] LLMSkinReporter 초기화 완료 (provider={provider}, model={model_name})")
        self.max_retries = max_retries if max_retries is not None else api_config["max_retries"]
        self.retry_delay = retry_delay if retry_delay is not None else api_config["retry_delay"]
        self.progress_callback = progress_callback
        self._product_repository = product_repository  # 의존성 주입된 ProductRepository
        self.temperature = api_config["temperature"]
        self.temperature_scoring = api_config.get("temperature_scoring", 0.15)
        self.temperature_opinion = api_config.get("temperature_opinion", 0.7)
        self.max_output_tokens_single = api_config["max_output_tokens_single"]
        self.max_output_tokens_dual = api_config["max_output_tokens_dual"]

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------


    def generate_report(
        self,
        image_path: str | Path,
        provide_scores: bool = True,  # 점수 제공 여부
    ) -> SkinLLMReport:
        """이미지 경로 → 전체 분석 + LLM 소견
        
        Args:
            image_path: 분석할 이미지 경로
            provide_scores: 점수 제공 여부 (True면 LLM가 점수를 산출, False면 원본 점수 사용)
        
        Returns:
            SkinLLMReport: LLM 소견이 포함된 보고서

        Note:
            이 함수는 Layer B(보고서 항목) 기준으로 동작합니다.
            measurements_report(Layer B)를 사용하며, 없을 경우 measurements(Layer A)를 폴백으로 사용합니다.
            하지만 Layer A는 10개 항목만 있으므로 일부 항목이 누락될 수 있습니다.
        """
        from src.scoring.skin_scoring import SkinAnalyzer

        analyzer = SkinAnalyzer()
        analysis_result: Dict[str, Any] = analyzer.analyze_all(str(image_path))
        
        # Layer B 우선, 없으면 Layer A 폴백
        measurements_report: Dict[str, Any] = analysis_result.get("measurements_report") or analysis_result.get("measurements", {})
        overall_score: float = analysis_result.get("overall_score", 0)
        perceived_age: float = analysis_result.get("perceived_age", 0)
        
        return self.generate_report_from_measurements(
            image_path,
            measurements_report,
            overall_score,
            perceived_age,
            provide_scores=provide_scores,
        )


    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: List[Path],
        max_output_tokens: int,
        temperature: Optional[float] = None,
    ) -> str:
        """LLM API 호출 (단일 시도)

        참고: 이전 버전에서는 _call_llm_with_retry였으나, 재시도 로직이
        상위 호출부(generate_report, generate_dual_report)로 이동되어
        단일 시도만 수행하도록 단순화되었습니다.
        """
        # temperature가 제공되지 않으면 기본값 사용
        if temperature is None:
            temperature = self.temperature
        # 이미지 로드
        import PIL.Image
        images: List[Any] = []
        for img_path in image_paths:
            img = PIL.Image.open(img_path)
            images.append(img)

        # 프로바이더를 통한 API 호출
        response_text: str = self._provider.generate_content(
            prompts=[system_prompt, user_prompt],
            images=images,
            temperature=temperature,
        )

        log.info(f"[LLM] API 호출 성공, 응답 길이: {len(response_text)}")
        log.info(f"[LLM] 응답 내용: {response_text[:500]}...")
        log.debug(f"[LLM] 전체 응답:\n{response_text}")
        return response_text



# [FIX] 원본에 없던 별칭 — llm_utils.py 가 LLMSkinReporter(대문자) 를 import
LLMSkinReporter = LlmSkinReporter

__all__ = ["LlmSkinReporter", "LLMSkinReporter"]
