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


def _build_reference_guided_prompt(
    orig_measurements_report: Dict[str, Any],
    orig_overall_score: float,
    orig_perceived_age: float,
    ideal_measurements_report: Dict[str, Any],
    provide_scores: bool = True,
    product_info: Optional[str] = None,
    prescription_info: Optional[str] = None,
) -> str:
    """복원 이미지를 레퍼런스(기준선)로 활용하여 원본 점수 정확도를 높이는 프롬프트.

    기존 듀얼 프롬프트와의 핵심 차이:
      - 기존: "두 이미지를 각각 독립적으로 분석하시오"
      - 신규: "복원본을 먼저 파악하고, 그 기준선으로 원본을 역산하시오"

    3단계 순차 지시로 Gemini의 분석 순서를 강제한다:
      Step 1. 복원본 기준선 파악  (이미지 순서상 2번째 이미지)
      Step 2. 원본 오탐 요인 역산 (이미지 순서상 1번째 이미지)
      Step 3. 최종 원본 점수 산출

    Args:
        orig_measurements_report:  원본 CV 분석기 측정값 (참고용)
        orig_overall_score:        원본 CV 종합 점수
        orig_perceived_age:        원본 CV 인지 나이
        ideal_measurements_report: 복원 CV 측정값 (복원본 분석 품질 참고용)
        provide_scores:            CV 점수를 프롬프트에 포함할지 여부
        product_info:              매칭된 제품 정보 JSON 문자열
        prescription_info:         처방전 정보 JSON 문자열

    Returns:
        Gemini user_prompt 문자열
    """
    # ── 1. 템플릿 파일에서 REFERENCE_GUIDED 섹션 로드 ─────────────
    try:
        template = load_prompt_template()
    except Exception:
        template = ""

    ref_template = ""
    if template:
        ref_template = extract_section(
            template,
            "<!-- REFERENCE_GUIDED_PROMPT_START -->",
            "<!-- REFERENCE_GUIDED_PROMPT_END -->",
        )

    # ── 2. 템플릿 없으면 하드코딩 폴백 사용 ──────────────────────
    if not ref_template:
        ref_template = _REFERENCE_GUIDED_PROMPT_FALLBACK

    # ── 3. 점수 섹션 조립 ─────────────────────────────────────────
    if provide_scores:
        scores_section = _build_cv_scores_section(
            orig_measurements_report, orig_overall_score, orig_perceived_age,
            ideal_measurements_report,
        )
    else:
        scores_section = "(CV 점수 미제공 모드 — 이미지만으로 판단하십시오.)"

    # ── 4. 포맷팅 ─────────────────────────────────────────────────
    format_dict = {
        "orig_overall_score":  f"{orig_overall_score:.1f}",
        "orig_perceived_age":  f"{orig_perceived_age:.1f}",
        "cv_scores_section":   scores_section,
        "product_info":        product_info or "제공된 맞춤형 화장품 정보가 없습니다.",
        "prescription_info":   prescription_info or "{}",
    }

    log.info(
        "[RGP] reference_guided 프롬프트 구성: provide_scores=%s, orig=%.1f점",
        provide_scores, orig_overall_score,
    )

    return _safe_format(ref_template, format_dict)


def _build_cv_scores_section(
    orig_report: Dict[str, Any],
    orig_overall: float,
    orig_age: float,
    ideal_report: Dict[str, Any],
) -> str:
    """CV 분석기 측정 점수를 프롬프트 섹션 문자열로 변환."""
    lines = [
        "### CV 분석기 점수 (참고용 — 이미지 직접 관찰 우선)",
        "",
        f"원본 종합: {orig_overall:.1f}점 / 인지 나이: {orig_age:.1f}세",
        "",
        "| 항목 | 원본 CV점수 | 복원 CV점수 |",
        "|------|------------|------------|",
    ]
    for key, display, _, _ in _METRIC_META:
        o = orig_report.get(key)
        i = ideal_report.get(key)
        o_str = f"{float(o):.1f}" if o is not None else "N/A"
        i_str = f"{float(i):.1f}" if i is not None else "N/A"
        lines.append(f"| {display} ({key}) | {o_str} | {i_str} |")
    lines.append("")
    lines.append(
        "**주의**: 위 점수는 CV 분석기 측정값입니다. "
        "이미지 관찰 결과와 불일치하면 이미지 판단을 우선하십시오."
    )
    return "\n".join(lines)


# ── 하드코딩 폴백 프롬프트 ────────────────────────────────────────────
_REFERENCE_GUIDED_PROMPT_FALLBACK = """\
## CÔTELEAF 피부 분석 요청 — 복원 기반 원본 점수 정확도 향상 모드

첨부 이미지:
- **이미지 1**: 원본 얼굴 사진 (분석 대상)
- **이미지 2**: GAN 복원 얼굴 사진 (레퍼런스 — 조명·노이즈·압축 아티팩트 제거 상태)

---

## 분석 절차 (반드시 아래 순서대로 수행하십시오)

### Step 1. 복원본 기준선 파악 (이미지 2 먼저 분석)

복원 이미지에서 각 카테고리의 실제 피부 구조를 파악하고
`reference_baseline` 필드에 서술하십시오.

- **주름**: 눈가·팔자·이마 주름의 위치, 방향, 깊이
- **모공**: 코·볼 영역의 분포, 크기 범위
- **색소**: 기미·주근깨의 위치, 농도, 범위
- **탄력**: 턱선 명확도, 볼 처짐 정도, 피부 탄력선
- **홍조**: 홍조·발적 분포 부위와 강도

### Step 2. 원본 오탐 요인 역산 (이미지 1 분석)

원본 이미지에서 Step 1의 구조가 아래 요인에 의해
가려지거나 과장된 정도를 판단하십시오.
보정이 적용된 항목과 이유를 `correction_reasons` 필드에 기재하십시오.

| 오탐 요인 | 설명 |
|---|---|
| 조명 불균일 | 그림자가 주름·음영처럼 보이는 영역 |
| 광택·반사 | 피부 유분이 홍조·발적처럼 보이는 영역 |
| 초점 흐림 | 모공 경계가 불명확한 영역 |
| 색온도 편차 | 전반적 피부 톤 왜곡 (기미·톤 항목 영향) |
| 압축 아티팩트 | 색소 경계 번짐 (주근깨·기미 항목 영향) |

### Step 3. 최종 원본 점수 산출

Step 1(기준선)과 Step 2(보정)를 통합하여
원본 이미지의 18개 항목 점수(10~90 스케일)를 산출하십시오.

---

## CV 분석기 측정값 (참고)

{cv_scores_section}

---

## 처방전 정보

{prescription_info}

---

## 맞춤형 제품 정보

{product_info}

---

## 응답 형식 (순수 JSON, ```json 없이)

{{
  "reference_baseline": {{
    "주름": "복원본에서 관찰된 주름 기준선 서술",
    "모공": "복원본에서 관찰된 모공 기준선 서술",
    "색소": "복원본에서 관찰된 색소 기준선 서술",
    "탄력": "복원본에서 관찰된 탄력 기준선 서술",
    "홍조": "복원본에서 관찰된 홍조 기준선 서술"
  }},
  "correction_reasons": {{
    "melasma_score":                       "보정 이유 (없으면 빈 문자열)",
    "freckle_score":                       "",
    "redness_score":                       "",
    "post_inflammatory_erythema_score":    "",
    "acne_score":                          "",
    "post_acne_pigment_score":             "",
    "pore_size_score":                     "",
    "pore_sagging_score":                  "",
    "eye_wrinkle_score":                   "",
    "nasolabial_wrinkle_score":            "",
    "fine_deep_wrinkle_score":             "",
    "roughness_score":                     "",
    "skin_tone_score":                     "",
    "dullness_score":                      "",
    "uneven_tone_score":                   "",
    "jawline_blur_score":                  "",
    "cheek_sagging_score":                 "",
    "skin_type_score":                     ""
  }},
  "orig_metric_scores": {{
    "melasma_score": 70.0,
    "freckle_score": 65.0,
    "redness_score": 68.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 85.0,
    "post_acne_pigment_score": 75.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 64.0,
    "eye_wrinkle_score": 72.0,
    "nasolabial_wrinkle_score": 70.0,
    "fine_deep_wrinkle_score": 74.0,
    "roughness_score": 71.0,
    "skin_tone_score": 68.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 67.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 75.0,
    "skin_type_score": 78.0
  }},
  "orig_metric_opinions": {{
    "melasma_score": "원본 소견 (Step 2 보정 내용 반영, 2~3문장)",
    "freckle_score": "",
    "redness_score": "",
    "post_inflammatory_erythema_score": "",
    "acne_score": "",
    "post_acne_pigment_score": "",
    "pore_size_score": "",
    "pore_sagging_score": "",
    "eye_wrinkle_score": "",
    "nasolabial_wrinkle_score": "",
    "fine_deep_wrinkle_score": "",
    "roughness_score": "",
    "skin_tone_score": "",
    "dullness_score": "",
    "uneven_tone_score": "",
    "jawline_blur_score": "",
    "cheek_sagging_score": "",
    "skin_type_score": ""
  }},
  "orig_overall_score": 74.5,
  "orig_perceived_age": 38.0,
  "orig_overall_opinion": "종합 소견 5~8문장 (복원 기준선과 비교하여 원본 상태를 서술)",
  "recommendation": "관리 권고사항 (번호 목록)"
}}
"""


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
