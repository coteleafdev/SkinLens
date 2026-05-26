"""
llm_fallback_prompts.py — 폴백용 하드코딩된 LLM 프롬프트

llm_prompt_template.md 를 읽을 수 없는 환경(서버 배포, 단위 테스트)에서도
측정 항목을 전부 포함한 완전한 프롬프트를 생성하는 폴백 프롬프트입니다.
"""

from __future__ import annotations

from typing import Any, Dict

from src.llm.llm_metadata import _get_metric_meta
from src.llm.llm_formatters import _grade_label
from src.skin.core.config_parser import get_measurement_count

# 측정항목 메타데이터 (동적 로드)
_METRIC_META = _get_metric_meta()


def get_fallback_system_prompt() -> str:
    """폴백용 System Prompt.
    
    llm_prompt_template.md 를 읽을 수 없는 환경에서 사용하는
    하드코딩된 기본 System Prompt입니다.
    """
    return (
        "당신은 CÔTELEAF 피부 AI 분석 시스템의 전문 피부과 소견 작성 엔진입니다.\n"
        "다음 규칙을 엄격히 따르십시오:\n"
        "1. 응답은 반드시 JSON 형식만 출력하십시오. Markdown 코드블록(```) 없이 순수 JSON만 출력.\n"
        "2. 각 항목 소견은 2~3문장, 구체적이고 전문적인 한국어로 작성.\n"
        "3. 점수 10~90 기준: 90 이상=매우우수, 80~90=우수, 70~80=양호, 60~70=집중케어추천, 60 미만=개선필요.\n"
        "4. 이미지를 직접 참고하여 점수와 이미지 상태가 일치하는 소견을 작성.\n"
        "5. 종합 소견은 5~8문장, 전반적 피부 상태 평가와 개선 방향 포함.\n"
        "6. 관리 권고사항은 3~5가지 항목으로 구체적 케어 방법 제시.\n"
        "7. 의학적 진단이 아닌 피부 관리 관점의 소견임을 전제로 작성."
    )


def build_fallback_user_prompt(
    measurements_report: Dict[str, Any],
    overall_score: float,
    perceived_age: float,
    provide_scores: bool = True,
) -> str:
    """폴백용 하드코딩된 단일 이미지 프롬프트 빌더.

    llm_prompt_template.md 를 읽을 수 없는 환경(서버 배포, 단위 테스트)에서도
    측정 항목을 전부 포함한 완전한 프롬프트를 생성한다.
    """
    lines = [
        "## CÔTELEAF 피부 분석 결과",
        "",
    ]

    if provide_scores:
        measurement_count = get_measurement_count()
        lines += [
            f"- 종합 점수: {overall_score:.1f}점 (10~90 스케일)",
            f"- 인지 나이: {perceived_age:.1f}세",
            "",
            f"## {measurement_count}개 항목별 측정 점수 (10~90 스케일, 높을수록 양호)",
            "",
        ]
        current_cat = None
        for key, display, category, _ in _METRIC_META:
            score = measurements_report.get(key)
            if score is None:
                continue
            score_val = float(score)
            if category != current_cat:
                lines.append(f"  [{category}]")
                current_cat = category
            lines.append(f"    - {display}: {score_val:.1f}점 → {_grade_label(score_val)}")
        lines.append("")
        lines.append(
            "첨부된 얼굴 원본 사진과 위 측정 점수를 함께 참고하여 "
            "아래 JSON 형식으로 응답하시오."
        )
    else:
        measurement_count = get_measurement_count()
        lines += [
            f"## {measurement_count}개 측정 항목 (점수 평가 기준)",
            "",
            "**점수 스케일:** 10~90점 (높을수록 양호)",
            "- 90 이상: 매우 우수",
            "- 80~90: 우수",
            "- 70~80: 양호",
            "- 60~70: 집중케어 추천",
            "- 60 미만: 개선 필요",
            "",
        ]
        current_cat = None
        for key, display, category, _ in _METRIC_META:
            if category != current_cat:
                lines.append(f"  [{category}]")
                current_cat = category
            lines.append(f"    - {display}")
        lines.append("")
        measurement_count = get_measurement_count()
        lines.append(
            "첨부된 얼굴 원본 사진을 참고하여 "
            f"위 {measurement_count}개 항목에 대한 점수와 소견을 "
            "아래 JSON 형식으로 응답하시오."
        )

    lines.append("")
    lines.append("## 응답 형식 (JSON)")
    lines.append("")
    lines.append("{")
    lines.append('  "overall_opinion": "종합 소견 (5~8문장)",')
    lines.append('  "recommendations": ["관리 권고사항 1", "관리 권고사항 2", ...],')
    
    if provide_scores:
        for key, display, _, _ in _METRIC_META:
            lines.append(f'  "{key}_opinion": "{display} 소견 (2~3문장)",')
    
    lines.append("}")
    
    return "\n".join(lines)


def build_fallback_dual_image_prompt(
    orig_measurements_report: Dict[str, Any],
    orig_overall_score: float,
    orig_perceived_age: float,
    ideal_measurements_report: Dict[str, Any],
    ideal_overall_score: float,
    ideal_perceived_age: float,
    provide_scores: bool = True,
) -> str:
    """폴백용 하드코딩된 듀얼 이미지 프롬프트 빌더.

    원본 이미지와 복원 이미지를 비교하는 듀얼 이미지 분석용
    하드코딩된 프롬프트입니다.
    """
    lines = [
        "## CÔTELEAF 피부 분석 결과 (원본 vs 복원)",
        "",
    ]

    if provide_scores:
        measurement_count = get_measurement_count()
        lines += [
            "### 원본 이미지",
            f"- 종합 점수: {orig_overall_score:.1f}점 (10~90 스케일, 시스템 분석기 로직)",
            f"- 인지 나이: {orig_perceived_age:.1f}세",
            "",
            "### 복원 이미지",
            f"- 종합 점수: {ideal_overall_score:.1f}점 (10~90 스케일, 시스템 분석기 로직)",
            f"- 인지 나이: {ideal_perceived_age:.1f}세",
            "",
            f"## {measurement_count}개 측정 항목 (점수 평가 기준)",
            "",
            "**점수 스케일:** 10~90점 (높을수록 양호)",
            "- 90 이상: 매우 우수",
            "- 80~90: 우수",
            "- 70~80: 양호",
            "- 60~70: 집중케어 추천",
            "- 60 미만: 개선 필요",
            "",
        ]
        current_cat = None
        for key, display, category, _ in _METRIC_META:
            if category != current_cat:
                lines.append(f"  [{category}]")
                current_cat = category
            lines.append(f"    - {display}")
        lines.append("")
        lines.append(
            "첨부된 얼굴 원본 사진과 복원 사진을 참고하여 "
            f"위 {measurement_count}개 항목에 대한 점수를 직접 산출하고 "
            "아래 JSON 형식으로 응답하시오."
        )
    else:
        measurement_count = get_measurement_count()
        lines += [
            f"## {measurement_count}개 측정 항목 (점수 평가 기준)",
            "",
            "**점수 스케일:** 10~90점 (높을수록 양호)",
            "- 90 이상: 매우 우수",
            "- 80~90: 우수",
            "- 70~80: 양호",
            "- 60~70: 집중케어 추천",
            "- 60 미만: 개선 필요",
            "",
        ]
        current_cat = None
        for key, display, category, _ in _METRIC_META:
            if category != current_cat:
                lines.append(f"  [{category}]")
                current_cat = category
            lines.append(f"    - {display}")
        lines.append("")
        measurement_count = get_measurement_count()
        lines.append(
            "첨부된 얼굴 원본 사진과 복원 사진을 참고하여 "
            f"위 {measurement_count}개 항목에 대한 점수와 소견을 "
            "아래 JSON 형식으로 응답하시오."
        )

    lines.append("")
    lines.append("## 응답 형식 (JSON)")
    lines.append("")
    lines.append("{")
    lines.append('  "original_metric_scores": {')
    for key, display, _, _ in _METRIC_META:
        lines.append(f'    "{key}": 70.0,')
    lines.append('  },')
    lines.append('  "restored_metric_scores": {')
    for key, display, _, _ in _METRIC_META:
        lines.append(f'    "{key}": 75.0,')
    lines.append('  },')
    lines.append('  "original_metric_opinions": {')
    for key, display, _, _ in _METRIC_META:
        lines.append(f'    "{key}": "원본 {display} 소견 (2~3문장)",')
    lines.append('  },')
    lines.append('  "restored_metric_opinions": {')
    for key, display, _, _ in _METRIC_META:
        lines.append(f'    "{key}": "복원 {display} 소견 (2~3문장)",')
    lines.append('  },')
    lines.append('  "original_overall_score": 65.0,')
    lines.append('  "original_perceived_age": 22.0,')
    lines.append('  "restored_overall_score": 70.0,')
    lines.append('  "restored_perceived_age": 21.0,')
    lines.append('  "original_overall_opinion": "원본 종합 소견 (5~8문장)",')
    lines.append('  "restored_overall_opinion": "복원 종합 소견 (5~8문장)",')
    lines.append('  "recommendation": "관리 권고사항 (번호 목록 형식)",')
    lines.append("}")
    
    return "\n".join(lines)
