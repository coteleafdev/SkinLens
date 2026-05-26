"""
llm_metadata.py — LLM 메타데이터 관리 모듈

측정항목 메타데이터 및 점수 기준을 동적으로 로드하는 기능을 제공합니다.
[REFACTOR 2026-05-24] config.json에서 데이터를 로드하며, 실패 시 하드코딩된 폴백값을 사용합니다.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from src.skin.core.config_parser import (
    parse_metric_meta,
    get_metric_meta,
    parse_score_criteria,
    get_min_score,
)

log = logging.getLogger(__name__)

# 메타데이터 캐싱 (중복 로드 방지)
_metric_meta_cache: Optional[List[Tuple[str, str, str, bool]]] = None
_score_criteria_cache: Optional[Dict[str, Tuple[int, int, str]]] = None


def _get_metric_meta_fallback() -> List[Tuple[str, str, str, bool]]:
    """폴백용 하드코딩된 측정항목 메타데이터"""
    return [
        # 색소 (Pigmentation)
        ("melasma_score",              "기미·잡티",           "색소",    True),
        ("freckle_score",              "주근깨",              "색소",    True),
        # 홍조, 홍반 (Redness)
        ("redness_score",              "홍조",         "홍조",    True),
        ("post_inflammatory_erythema_score", "염증후 홍반",         "홍조",    True),
        # 트러블·흔적 (Acne & Marks)
        ("acne_score",                 "여드름",              "트러블",  True),
        ("post_acne_pigment_score",    "여드름 후 색소",      "트러블",  True),
        # 모공 (Pore)
        ("pore_size_score",            "모공 크기",           "모공",    True),
        ("pore_sagging_score",         "모공 처짐",           "모공",    True),
        # 주름 (Wrinkle)
        ("eye_wrinkle_score",          "눈가 주름",           "주름",    True),
        ("nasolabial_wrinkle_score",   "팔자 주름",           "주름",    True),
        ("fine_deep_wrinkle_score",    "잔주름·깊은 주름",   "주름",    True),
        # 텍스처 (Texture)
        ("roughness_score",            "피부결 거칠기",       "텍스처",  True),
        # 톤·밝기 (Tone)
        ("skin_tone_score",            "피부 톤",             "톤",      True),
        ("dullness_score",             "칙칙함",              "톤",      True),
        ("uneven_tone_score",          "톤 불균일",           "톤",      True),
        # 탄력 (Elasticity)
        ("jawline_blur_score",         "턱선 탄력",           "탄력",    True),
        ("cheek_sagging_score",        "볼 처짐",             "탄력",    True),
        # 피부 타입 (Skin Type)
        ("skin_type_score",            "피부 타입",           "피부 타입",    True),
    ]


def _get_metric_meta() -> List[Tuple[str, str, str, bool]]:
    """측정항목 메타데이터를 동적으로 로드합니다.

    [REFACTOR 2026-05-24] config.json의 measurements 섹션에서 로드.
    [OPTIMIZE 2026-05-24] 캐싱으로 중복 로드 방지.
    """
    global _metric_meta_cache
    
    # 캐시된 데이터가 있으면 반환
    if _metric_meta_cache is not None:
        log.debug(f"[LLM Metadata] 캐시된 메타데이터 사용: {len(_metric_meta_cache)}개 항목")
        return _metric_meta_cache
    
    try:
        from src.prescription.prescription_calculator import get_all_measurements

        measurements = get_all_measurements()
        if not measurements:
            raise ValueError("measurements가 비어있습니다.")

        log.debug(f"[LLM Metadata] config.json에서 {len(measurements)}개 측정항목 로드")

        # config.json 메타데이터를 LLM 형식으로 변환
        meta = []
        for key, data in measurements.items():
            if key.startswith("_"):
                continue  # _note 등 주석 필드 건너뜀

            name_ko = data.get("name_ko", key)
            category = data.get("category", "기타")
            higher_is_better = True  # 기본값

            meta.append((key, name_ko, category, higher_is_better))

        log.debug(f"[LLM Metadata] 변환된 메타데이터: {len(meta)}개 항목")
        for key, name_ko, category, _ in meta:
            log.debug(f"  - {key}: {name_ko} ({category})")

        if meta:
            _metric_meta_cache = meta  # 캐시 저장
            return meta
    except Exception as e:
        log.warning(f"config.json 메타데이터 로드 실패, 폴백 사용: {e}", exc_info=True)

    # 폴백: llm_prompt_template.md에서 로드
    try:
        meta = get_metric_meta()
        if meta:
            _metric_meta_cache = meta  # 캐시 저장
            return meta
    except Exception as e:
        log.warning(f"llm_prompt_template.md 로드 실패, 폴백 사용: {e}")

    # 최종 폴백
    meta = _get_metric_meta_fallback()
    _metric_meta_cache = meta  # 캐시 저장
    return meta


def _get_score_criteria_fallback() -> Dict[str, Tuple[int, int, str]]:
    """폴백용 하드코딩된 점수 기준"""
    return {
        "melasma_score": (30, 70, "색소침착"),
        "freckle_score": (30, 70, "색소침착"),
        "redness_score": (30, 70, "홍조"),
        "post_inflammatory_erythema_score": (30, 70, "홍조"),
        "acne_score": (30, 70, "트러블"),
        "post_acne_pigment_score": (30, 70, "색소침착"),
        "pore_size_score": (30, 70, "모공"),
        "pore_sagging_score": (30, 70, "모공"),
        "eye_wrinkle_score": (30, 70, "주름"),
        "nasolabial_wrinkle_score": (30, 70, "주름"),
        "fine_deep_wrinkle_score": (30, 70, "주름"),
        "roughness_score": (30, 70, "텍스처"),
        "skin_tone_score": (30, 70, "톤"),
        "dullness_score": (30, 70, "톤"),
        "uneven_tone_score": (30, 70, "톤"),
        "jawline_blur_score": (30, 70, "탄력"),
        "skin_type_score": (30, 70, "피부 타입"),
    }


def _get_score_criteria() -> Dict[str, Tuple[int, int, str]]:
    """점수 기준을 동적으로 로드합니다.
    
    [OPTIMIZE 2026-05-24] 캐싱으로 중복 로드 방지.
    """
    global _score_criteria_cache
    
    # 캐시된 데이터가 있으면 반환
    if _score_criteria_cache is not None:
        log.debug(f"[LLM Metadata] 캐시된 점수 기준 사용: {len(_score_criteria_cache)}개 항목")
        return _score_criteria_cache
    
    try:
        from src.skin.core.config_parser import load_prompt_template
        markdown = load_prompt_template()
        if markdown:
            criteria = parse_score_criteria(markdown)
            if criteria:
                _score_criteria_cache = criteria  # 캐시 저장
                return criteria
    except Exception as e:
        log.warning(f"점수 기준 로드 실패, 폴백 사용: {e}")
    
    # 폴백
    criteria = _get_score_criteria_fallback()
    _score_criteria_cache = criteria  # 캐시 저장
    return criteria
