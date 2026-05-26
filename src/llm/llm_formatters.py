"""
llm_formatters.py — LLM 포맷터 모듈

소견 텍스트 포맷팅, 등급 라벨링, 감정 분석, 점수 조정 기능을 제공합니다.
데이터 클래스(MetricOpinion, SkinLLMReport)도 포함합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.llm.llm_metadata import _get_score_criteria


# 점수 기준 (동적 로드)
_SCORE_CRITERIA: Dict[str, tuple[int, int, str]] = _get_score_criteria()


def _safe_format(template: str, mapping: Dict[str, str]) -> str:
    """format_dict 의 키만 선택적으로 치환한다. 나머지 { } 는 건드리지 않는다.

    str.format(**mapping) 은 템플릿 안의 JSON 예시 코드({...})를
    placeholder 로 오해해 KeyError 를 발생시키는 문제를 완전히 회피한다.

    치환 순서: 긴 키 우선 (접두사 충돌 방지).
    예: {orig_melasma_score_grade} 가 {orig_melasma_score} 보다 먼저 치환.
    """
    for key in sorted(mapping.keys(), key=len, reverse=True):
        template = template.replace("{" + key + "}", mapping[key])
    return template


def _grade_label(score: float) -> str:
    """점수에 따른 등급 라벨 반환 (동적 로드된 기준 사용)"""
    for grade_name, (min_score, max_score, label) in _SCORE_CRITERIA.items():
        if min_score <= score <= max_score:
            return label
    return "알 수 없음"


def _analyze_opinion_sentiment(opinion_text: str) -> str:
    """소견 텍스트에서 긍정/부정/중립 판단
    
    Returns:
        "positive" - 우수, 양호, 좋음, 개선됨 등 긍정적 표현
        "negative" - 심함, 나쁨, 개선 필요, 문제 등 부정적 표현
        "neutral" - 그 외 중립적 표현
    """
    # opinion_text가 문자열이 아닌 경우 처리
    if not isinstance(opinion_text, str):
        return "neutral"
    if not opinion_text:
        return "neutral"
    
    opinion_lower = opinion_text.lower()
    
    # 부정적 키워드
    negative_keywords = [
        "심함", "나쁨", "개선 필요", "문제", "부족", "미흡", "낮음", 
        "안좋음", "심각", "심한", "많음", "관리 필요", "치료 필요",
        "염증", "홍조", "여드름", "주름", "거칠", "칙칙", "건조"
    ]
    
    # 긍정적 키워드
    positive_keywords = [
        "우수", "양호", "좋음", "개선됨", "정상", "유지 관리", 
        "건강", "깨끗", "매끄러움", "밝음", "탄력", "촉촉"
    ]
    
    for keyword in negative_keywords:
        if keyword in opinion_text:
            return "negative"
    
    for keyword in positive_keywords:
        if keyword in opinion_text:
            return "positive"
    
    return "neutral"


def _adjust_score_based_on_opinion(original_score: float, opinion_text: str) -> float:
    """소견에 기반하여 점수 조정
    
    Args:
        original_score: 원래 점수 (0-100)
        opinion_text: LLM 소견 텍스트
    
    Returns:
        조정된 점수
    """
    # opinion_text가 문자열이 아닌 경우 처리
    if not isinstance(opinion_text, str):
        return original_score
    if not opinion_text or opinion_text.strip() == "":
        return original_score
    
    sentiment = _analyze_opinion_sentiment(opinion_text)
    
    # 점수 범위에 따른 등급 판정
    if original_score >= 90:
        score_grade = "excellent"
    elif original_score >= 80:
        score_grade = "good"
    elif original_score >= 70:
        score_grade = "fair"
    elif original_score >= 60:
        score_grade = "care"
    else:
        score_grade = "poor"
    
    # 소견과 점수 불일치 시 조정
    if sentiment == "negative" and score_grade in ["excellent", "good"]:
        # 점수는 좋은데 소견이 부정적 → 점수 하향 조정
        if score_grade == "excellent":
            return max(50.0, original_score - 20.0)  # 우수 → 보통 수준으로
        else:  # good
            return max(40.0, original_score - 15.0)  # 양호 → 낮은 수준으로
    
    elif sentiment == "positive" and score_grade in ["poor", "care", "fair"]:
        # 점수는 낮은데 소견이 긍정적 → 점수 상향 조정
        if score_grade == "poor":
            return min(70.0, original_score + 20.0)  # 낮음 → 양호 수준으로
        elif score_grade == "care":
            return min(80.0, original_score + 15.0)  # 관리 필요 → 양호 수준으로
        else:  # fair
            return min(88.0, original_score + 8.0)  # 보통 → 우수 수준으로
    
    # 일치하는 경우 조정 없음
    return original_score


# ──────────────────────────────────────────────────────────────
# 데이터 클래스
# ──────────────────────────────────────────────────────────────

@dataclass
class MetricOpinion:
    """항목 1개의 소견"""
    key: str
    display_name: str
    category: str
    score: float
    grade: str
    opinion: str          # LLM 생성 소견 (2~3문장)


@dataclass
class SkinLLMReport:
    """전체 보고서"""
    overall_score: float
    perceived_age: float
    metric_opinions: List[MetricOpinion] = field(default_factory=list)
    overall_opinion: str = ""          # 종합 소견
    recommendation: str = ""          # 관리 권고사항
    raw_response: str = ""            # LLM 원문 응답 (디버그용)
    scores_adjusted: bool = False     # 점수가 조정되었는지 여부
    model: str = ""                   # 사용된 LLM 모델명
    llm_stats: Dict[str, Any] = field(default_factory=dict)  # LLM API 통계
    product_recommendations: Dict[str, Any] = field(default_factory=dict)  # 맞춤형 화장품 추천 (LLM 생성)
    matched_products: List[Dict[str, Any]] = field(default_factory=list)  # DB 매칭 제품 (시스템 매칭)
