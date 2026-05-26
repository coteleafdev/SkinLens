"""
llm_prompt_builder.py — LLM 프롬프트 빌더 모듈

LLM에 전달할 프롬프트를 생성하는 기능을 제공합니다.
단일 이미지/듀얼 이미지 모드를 지원하며, 템플릿 파일에서 로드하거나
폴백용 하드코딩된 프롬프트를 사용합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.skin.core.config_parser import (
    load_prompt_template,
    extract_section,
    get_measurement_count,
)

from src.llm.llm_metadata import _get_metric_meta
from src.llm.llm_formatters import _safe_format, _grade_label
from src.llm.llm_fallback_prompts import (
    get_fallback_system_prompt,
    build_fallback_user_prompt,
    build_fallback_dual_image_prompt,
)

log = logging.getLogger(__name__)

# 측정항목 메타데이터 (동적 로드)
_METRIC_META: List[tuple[str, str, str, bool]] = _get_metric_meta()


def _build_system_prompt() -> str:
    """마크다운 파일에서 System Prompt를 읽어옵니다."""
    template = load_prompt_template()
    if not template:
        # 파일이 없는 경우 폴백 모듈 사용
        return get_fallback_system_prompt()
    return extract_section(template, "<!-- SYSTEM_PROMPT_START -->", "<!-- SYSTEM_PROMPT_END -->")


def _build_user_prompt(
    measurements_report: Dict[str, Any],
    overall_score: float,
    perceived_age: float,
    provide_scores: bool = True,  # 점수 제공 여부
    product_info: Optional[str] = None,  # 맞춤형 화장품 성분 정보
) -> str:
    """측정 점수표를 포함한 분석 요청 프롬프트 (단일 이미지용)"""
    template = load_prompt_template()
    if not template:
        # 파일이 없는 경우 폴백 모듈 사용
        return build_fallback_user_prompt(measurements_report, overall_score, perceived_age, provide_scores)
    
    user_prompt_template = extract_section(template, "<!-- SINGLE_IMAGE_USER_PROMPT_START -->", "<!-- SINGLE_IMAGE_USER_PROMPT_END -->")
    if not user_prompt_template:
        return build_fallback_user_prompt(measurements_report, overall_score, perceived_age, provide_scores)
    
    # 템플릿 포맷팅
    format_dict = {
        "overall_score": f"{overall_score:.1f}",
        "perceived_age": f"{perceived_age:.1f}",
        "product_info": product_info or "제공된 맞춤형 화장품 정보가 없습니다.",
    }
    
    # skin_type_label 추가 (별도 필드)
    skin_type_label = measurements_report.get("skin_type_label", "중성")
    format_dict["skin_type_label"] = skin_type_label

    # 측정항목 점수와 등급 추가
    valid_metrics = 0
    for key, display, category, _ in _METRIC_META:
        score = measurements_report.get(key)
        if score is not None:
            score_val = float(score)
            format_dict[key] = f"{score_val:.1f}"
            format_dict[f"{key}_grade"] = _grade_label(score_val)
            valid_metrics += 1
    
    # 프롬프트 구성 정보 로그 기록
    log.info("[프롬프트 구성] 종합 점수: %.1f, 인지 나이: %.1f세", overall_score, perceived_age)
    log.info("[프롬프트 구성] 개별항목 점수 제공: %s", provide_scores)
    log.info("[프롬프트 구성] 측정 항목 수: %d개", valid_metrics)
    log.debug("[프롬프트 구성] 유효 측정 항목: %s", 
              [k for k, _, _, _ in _METRIC_META if measurements_report.get(k) is not None])
    
    # [FIX] str.format() 대신 _safe_format() 사용:
    # 템플릿 내 JSON 예시 코드의 { } 가 placeholder 로 오해돼 KeyError 가 발생하던 버그 수정.
    return _safe_format(user_prompt_template, format_dict)


def _build_dual_image_prompt(
    orig_measurements_report: Dict[str, Any],
    orig_overall_score: float,
    orig_perceived_age: float,
    ideal_measurements_report: Dict[str, Any],
    ideal_overall_score: float,
    ideal_perceived_age: float,
    provide_scores: bool = True,  # 점수 제공 여부
    product_info: Optional[str] = None,  # 맞춤형 화장품 성분 정보
    prescription_info: Optional[str] = None,  # 처방전 정보 (A01-A14)
) -> str:
    """듀얼 이미지 프롬프트 빌더"""
    from src.skin.core.config_parser import load_prompt_template
    
    try:
        template = load_prompt_template()
        log.debug("[DEBUG] 템플릿 로드 결과: %s chars", len(template))
        if not template:
            log.debug("[DEBUG] 템플릿이 비어있음, 폴백 사용")
    except Exception as e:
        log.debug("[DEBUG] 템플릿 로드 실패: %s, 폴백 사용", e)
        template = ""
    
    if not template:
        # 파일이 없는 경우 폴백 모듈 사용
        return build_fallback_dual_image_prompt(
            orig_measurements_report, orig_overall_score, orig_perceived_age,
            ideal_measurements_report, ideal_overall_score, ideal_perceived_age,
            provide_scores
        )
    
    # 점수 미제공 모드: 별도 템플릿 사용
    if not provide_scores:
        user_prompt_template = extract_section(template, "<!-- DUAL_IMAGE_USER_PROMPT_NO_SCORES_START -->", "<!-- DUAL_IMAGE_USER_PROMPT_NO_SCORES_END -->")
        if user_prompt_template:
            # 점수 미제공 모드는 점수를 전달하지 않음
            log.info("[프롬프트 구성] 듀얼 이미지 모드")
            log.info("[프롬프트 구성] 개별항목 점수 제공: False")
            log.info("[프롬프트 구성] 원본 종합 점수: %.1f, 인지 나이: %.1f세", orig_overall_score, orig_perceived_age)
            log.info("[프롬프트 구성] 복원 종합 점수: %.1f, 인지 나이: %.1f세", ideal_overall_score, ideal_perceived_age)
            return user_prompt_template
        else:
            # 템플릿이 없으면 폴백 모듈 사용
            return build_fallback_dual_image_prompt(
                orig_measurements_report, orig_overall_score, orig_perceived_age,
                ideal_measurements_report, ideal_overall_score, ideal_perceived_age,
                provide_scores
            )
    
    # 점수 제공 모드: 기존 템플릿 사용
    user_prompt_template = extract_section(template, "<!-- DUAL_IMAGE_USER_PROMPT_START -->", "<!-- DUAL_IMAGE_USER_PROMPT_END -->")
    if not user_prompt_template:
        return build_fallback_dual_image_prompt(
            orig_measurements_report, orig_overall_score, orig_perceived_age,
            ideal_measurements_report, ideal_overall_score, ideal_perceived_age,
            provide_scores
        )
    
    # 템플릿 포맷팅
    format_dict = {
        "orig_overall_score": f"{orig_overall_score:.1f}",
        "orig_perceived_age": f"{orig_perceived_age:.1f}",
        "ideal_overall_score": f"{ideal_overall_score:.1f}",
        "ideal_perceived_age": f"{ideal_perceived_age:.1f}",
        "product_info": product_info or "제공된 맞춤형 화장품 정보가 없습니다.",
        "prescription_info": prescription_info or "{}",
    }
    
    # 프롬프트 구성 정보 로그 기록
    log.info("[프롬프트 구성] 듀얼 이미지 모드")
    log.info("[프롬프트 구성] 개별항목 점수 제공: True (시스템 분석기 점수 참고용)")
    log.info("[프롬프트 구성] 원본 종합 점수: %.1f, 인지 나이: %.1f세", 
             orig_overall_score, orig_perceived_age)
    log.info("[프롬프트 구성] 복원 종합 점수: %.1f, 인지 나이: %.1f세", 
             ideal_overall_score, ideal_perceived_age)
    
    # [FIX] str.format() 대신 _safe_format() 사용:
    # 템플릿 내 JSON 예시 코드의 { } 가 placeholder 로 오해돼 KeyError 가 발생하던 버그 수정.
    return _safe_format(user_prompt_template, format_dict)
