"""
CÔTELEAF 피부 분석 → Google LLM API 소견 생성 모듈 (Backward Compatibility Wrapper)
========================================================================================

이 파일은 하위 호환성을 위해 유지되는 래퍼입니다.
실제 기능은 다음 모듈로 분리되었습니다:
  - llm_config.py: 설정 관리
  - llm_model_manager.py: 모델 관리
  - llm_metadata.py: 메타데이터 관리
  - llm_formatters.py: 포맷터 및 데이터 클래스
  - llm_prompt_builder.py: 프롬프트 빌더
  - llm_reporter.py: LLMSkinReporter 핵심 클래스
  - llm_utils.py: 유틸리티 함수

새로운 코드에서는 각 모듈을 직접 임포트하여 사용하세요.
"""

from __future__ import annotations

# Re-export all public APIs for backward compatibility
from src.llm.llm_config import (
    get_default_model,
    get_default_timeout_sec,
    get_default_max_retries,
)

from src.llm.llm_model_manager import (
    list_available_models,
    check_model_availability,
    _load_llm_api_key,
)

from src.llm.llm_metadata import (
    _get_metric_meta,
    _get_score_criteria,
)

from src.llm.llm_formatters import (
    _safe_format,
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
)

from src.llm.llm_reporter import LlmSkinReporter

from src.llm.llm_utils import (
    log_report,
    report_to_dict,
    save_report_json,
    analyze_and_report,
)


__all__ = [
    # Config
    "get_default_model",
    "get_default_timeout_sec",
    "get_default_max_retries",
    # Model Manager
    "list_available_models",
    "check_model_availability",
    "_load_llm_api_key",
    # Metadata
    "_get_metric_meta",
    "_get_score_criteria",
    # Formatters
    "_safe_format",
    "_grade_label",
    "_analyze_opinion_sentiment",
    "_adjust_score_based_on_opinion",
    "MetricOpinion",
    "SkinLLMReport",
    # Prompt Builder
    "_build_system_prompt",
    "_build_user_prompt",
    "_build_dual_image_prompt",
    # Reporter
    "LlmSkinReporter",
    # Utils
    "log_report",
    "report_to_dict",
    "save_report_json",
    "analyze_and_report",
]
