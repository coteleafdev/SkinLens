"""LlmSkinReporter 공유 임포트·상수·헬퍼.

[구조변경] 거대 클래스 분해 시 생성/파싱 Mixin 이 공유하는 모듈레벨 헬퍼와
임포트를 이곳에 모은다. (순환참조 방지: facade/mixin 이 이 모듈을 import)
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

# 측정항목 메타데이터 (동적 로드)
_METRIC_META: List[tuple[str, str, str, bool]] = _get_metric_meta()


def _get_metric_trust_level(metric_key: str, config: dict) -> str:
    """측정항목의 신뢰도 레벨 조회
    
    Args:
        metric_key: 측정항목 키 (예: 'melasma_score')
        config: LLM 설정 dict
    
    Returns:
        신뢰도 레벨 ('verified', 'partially_verified', 'unverified')
    """
    metric_trust_levels = config.get("score_correction", {}).get("metric_trust_levels", {})
    
    for level, metrics in metric_trust_levels.items():
        if metric_key in metrics:
            return level
    
    # 기본값: 미검증
    log.debug(f"[신뢰도 레벨] {metric_key}에 대한 신뢰도 레벨 없음, 기본값 'unverified' 사용")
    return "unverified"


def _apply_advanced_score_correction(
    analyzer_score: float,
    llm_score: float,
    metric_key: str,
    config: dict,
    consistency_score: Optional[float] = None,
) -> float:
    """고급 점수 보정 로직 (신뢰도 기반)
    
    Args:
        analyzer_score: 자체 분석기 점수
        llm_score: LLM이 측정한 점수
        metric_key: 측정항목 키
        config: LLM 설정 dict
        consistency_score: 일관성 점수 (선택적)
    
    Returns:
        보정된 점수
    """
    # 1. 항목별 신뢰도 레벨 확인
    trust_level = _get_metric_trust_level(metric_key, config)
    
    # 2. 신뢰도 레벨별 가중치 및 임계값 조회
    trust_level_weights = config.get("score_correction", {}).get("trust_level_weights", {})
    level_config = trust_level_weights.get(trust_level, {})
    
    analyzer_weight = level_config.get("analyzer_weight", 0.5)
    llm_weight = level_config.get("llm_weight", 0.5)
    difference_threshold = level_config.get("difference_threshold", 15.0)
    
    log.debug(f"[고급 보정] {metric_key}: 신뢰도={trust_level}, 가중치(분석기={analyzer_weight}, LLM={llm_weight}), 임계값={difference_threshold}")
    
    # 3. 일관성 점수 반영 (활성화된 경우)
    consistency_config = config.get("score_correction", {}).get("consistency_scoring", {})
    if consistency_config.get("enabled", False) and consistency_score is not None:
        high_threshold = consistency_config.get("high_consistency_threshold", 90.0)
        low_threshold = consistency_config.get("low_consistency_threshold", 70.0)
        weight_adjustment = consistency_config.get("weight_adjustment", 0.1)
        
        if consistency_score >= high_threshold:
            analyzer_weight = min(1.0, analyzer_weight + weight_adjustment)
            llm_weight = max(0.0, llm_weight - weight_adjustment)
            log.debug(f"[고급 보정] 일관성 점수 높음 ({consistency_score}): 분석기 가중치 +{weight_adjustment}")
        elif consistency_score < low_threshold:
            analyzer_weight = max(0.0, analyzer_weight - weight_adjustment)
            llm_weight = min(1.0, llm_weight + weight_adjustment)
            log.debug(f"[고급 보정] 일관성 점수 낮음 ({consistency_score}): 분석기 가중치 -{weight_adjustment}")
    
    # 4. 점수 차이 확인 및 처리
    score_diff = abs(analyzer_score - llm_score)
    if score_diff >= difference_threshold:
        if trust_level == "verified":
            log.info(f"[고급 보정] {metric_key}: 점수 차이 {score_diff:.1f} >= 임계값 {difference_threshold}, 분석기 점수 사용 (검증됨)")
            return analyzer_score
        elif trust_level == "unverified":
            log.info(f"[고급 보정] {metric_key}: 점수 차이 {score_diff:.1f} >= 임계값 {difference_threshold}, LLM 점수 사용 (미검증)")
            return llm_score
        else:
            # 부분 검증: 기본 가중치 적용
            log.debug(f"[고급 보정] {metric_key}: 점수 차이 {score_diff:.1f} >= 임계값 {difference_threshold}, 기본 가중치 적용 (부분 검증)")
    
    # 5. 하이브리드 계산
    total_weight = analyzer_weight + llm_weight
    if abs(total_weight - 1.0) > 0.01:
        analyzer_weight /= total_weight
        llm_weight /= total_weight
    
    # [FIX P0] llm_weight * llm_weight → llm_score * llm_weight
    corrected_score = analyzer_score * analyzer_weight + llm_score * llm_weight
    log.debug(f"[고급 보정] {metric_key}: 분석기={analyzer_score}({analyzer_weight}) + LLM={llm_score}({llm_weight}) = {corrected_score}")
    return corrected_score


def _apply_score_correction(
    analyzer_score: float,
    llm_score: float,
    mode: str = "hybrid",
    analyzer_weight: float = 0.7,
    llm_weight: float = 0.3,
    dynamic_weighting: bool = False,
    score_difference_threshold: float = 15.0,
    prefer_llm_on_large_diff: bool = False,
    metric_key: Optional[str] = None,
    config: Optional[dict] = None,
) -> float:
    """점수 보정 로직
    
    Args:
        analyzer_score: 자체 분석기 점수
        llm_score: LLM이 측정한 점수
        mode: 보정 모드 ('analyzer', 'llm', 'hybrid', 'advanced')
        analyzer_weight: 자체 분석기 가중치 (hybrid 모드에서만 사용)
        llm_weight: LLM 가중치 (hybrid 모드에서만 사용)
        dynamic_weighting: 동적 가중치 조정 활성화 여부
        score_difference_threshold: 동적 가중치 조정 임계값
        prefer_llm_on_large_diff: 점수 차이가 큰 경우 LLM 점수 우선 (복원 기반 모드용)
        metric_key: 측정항목 키 (advanced 모드에서 필요)
        config: LLM 설정 dict (advanced 모드에서 필요)
    
    Returns:
        보정된 점수
    """
    if mode == "advanced":
        if metric_key is None or config is None:
            log.warning("[점수 보정] advanced 모드지만 metric_key 또는 config 없음, hybrid 모드로 대체")
            mode = "hybrid"
        else:
            return _apply_advanced_score_correction(analyzer_score, llm_score, metric_key, config)
    
    if mode == "analyzer":
        log.debug(f"[점수 보정] 자체 분석기 점수 사용: {analyzer_score}")
        return analyzer_score
    elif mode == "llm":
        log.debug(f"[점수 보정] LLM 점수 사용: {llm_score}")
        return llm_score
    elif mode == "hybrid":
        # 동적 가중치 조정
        if dynamic_weighting:
            score_diff = abs(analyzer_score - llm_score)
            if score_diff >= score_difference_threshold:
                if prefer_llm_on_large_diff:
                    log.info(
                        f"[점수 보정] 점수 차이 {score_diff:.1f} >= 임계값 {score_difference_threshold}, LLM 점수 우선 (복원 기반 모드)"
                    )
                    return llm_score
                else:
                    log.info(
                        f"[점수 보정] 점수 차이 {score_diff:.1f} >= 임계값 {score_difference_threshold}, 자체 분석기 점수 사용"
                    )
                    return analyzer_score
            else:
                log.debug(
                    f"[점수 보정] 기존 가중치 사용: 점수 차이 {score_diff:.1f} < 임계값 {score_difference_threshold}"
                )
        
        # 가중치 합계 검증
        total_weight = analyzer_weight + llm_weight
        if abs(total_weight - 1.0) > 0.01:
            log.warning(f"[점수 보정] 가중치 합계가 1.0이 아님: {total_weight}, 정규화 수행")
            analyzer_weight /= total_weight
            llm_weight /= total_weight
        
        corrected_score = analyzer_score * analyzer_weight + llm_score * llm_weight
        log.debug(f"[점수 보정] 하이브리드: 자체={analyzer_score}({analyzer_weight}) + LLM={llm_score}({llm_weight}) = {corrected_score}")
        return corrected_score
    else:
        log.warning(f"[점수 보정] 알 수 없는 모드: {mode}, 자체 분석기 점수 사용")
        return analyzer_score


def _monitor_score_difference(
    analyzer_score: float,
    llm_score: float,
    metric_name: str = "종합 점수",
    warning_threshold: float = 20.0,
    critical_threshold: float = 40.0,
) -> None:
    """점수 차이 모니터링 및 로깅
    
    Args:
        analyzer_score: 자체 분석기 점수
        llm_score: LLM이 측정한 점수
        metric_name: 측정항목 이름
        warning_threshold: 경고 임계값 (기본 20점)
        critical_threshold: 심각 임계값 (기본 40점)
    """
    # config에서 임계값 로드 시도
    try:
        from src.skin.core.config_parser import get_llm_api_config
        api_config = get_llm_api_config()
        score_correction_config = api_config.get("score_correction", {})
        monitoring_config = score_correction_config.get("monitoring", {})
        warning_threshold = monitoring_config.get("warning_threshold", 20.0)
        critical_threshold = monitoring_config.get("critical_threshold", 40.0)
    except Exception:
        pass  # 기본값 사용
    
    score_diff = abs(analyzer_score - llm_score)
    
    if score_diff >= critical_threshold:
        log.error(
            f"[점수 차이] {metric_name}: 심각한 차이 발생 "
            f"(자체={analyzer_score:.1f}, LLM={llm_score:.1f}, 차이={score_diff:.1f})"
        )
    elif score_diff >= warning_threshold:
        # [FIX P2] warning 구간 로깅 추가
        log.warning(
            f"[점수 차이] {metric_name}: 경고 수준 차이 발생 "
            f"(자체={analyzer_score:.1f}, LLM={llm_score:.1f}, 차이={score_diff:.1f})"
        )


def _is_response_truncated(response_text: str) -> bool:
    """응답이 짤렸는지 확인
    
    Args:
        response_text: LLM 응답 텍스트
    
    Returns:
        bool: 응답이 짤렸으면 True
    """
    if not response_text:
        return True
    
    # 마크다운 코드 블록 제거
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        response_text = "\n".join(lines).strip()
    
    # JSON이 중괄호로 닫히지 않은 경우
    if not response_text.strip().endswith("}"):
        return True
    
    # 따옴표 균형이 맞지 않는 경우
    quote_count = response_text.count('"')
    if quote_count % 2 != 0:
        return True
    
    return False


def _identify_missing_fields(response_text: str, expected_fields: list[str]) -> list[str]:
    """응답에서 누락된 필드 식별
    
    Args:
        response_text: LLM 응답 텍스트
        expected_fields: 기대하는 필드 목록
    
    Returns:
        list[str]: 누락된 필드 목록
    """
    missing_fields = []
    
    # 마크다운 코드 블록 제거
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        response_text = "\n".join(lines).strip()
    
    for field in expected_fields:
        if f'"{field}"' not in response_text:
            missing_fields.append(field)
    
    return missing_fields


def _build_field_completion_prompt(missing_fields: list[str], original_response: str) -> str:
    """누락된 필드만 요청하는 프롬프트 생성
    
    Args:
        missing_fields: 누락된 필드 목록
        original_response: 기존 응답 (컨텍스트 제공용)
    
    Returns:
        str: 누락된 필드만 요청하는 프롬프트
    """
    prompt = f"""다음 JSON 응답에서 누락된 필드만 채워주세요.

**기존 응답**:
```json
{original_response}
```

**누락된 필드**: {', '.join(missing_fields)}

**요청사항**:
1. 누락된 필드만 JSON 형식으로 출력하세요.
2. 기존 응답의 구조와 스타일을 유지하세요.
3. 필드값은 적절한 값으로 채워주세요.
4. 출력은 JSON 형식만 출력하세요 (마크다운 코드 블록 없이).

출력 예시:
{{
  "missing_field_1": "value1",
  "missing_field_2": "value2"
}}
"""
    return prompt


def _merge_json_responses(original: dict, completion: dict) -> dict:
    """기존 응답과 완료 응답 병합
    
    Args:
        original: 기존 응답 (누락된 필드가 있는 응답)
        completion: 완료 응답 (누락된 필드만 포함)
    
    Returns:
        dict: 병합된 응답
    """
    merged = original.copy()
    merged.update(completion)
    return merged

