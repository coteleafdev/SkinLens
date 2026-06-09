"""
GUI 표시측 점수 후처리 모듈

이 모듈은 GUI 전용 점수 후처리 로직을 포함합니다:
- offset 보정 적용
- raw 점수 필터링
- 최대 점수 제한

이 로직은 CLI/Engine/Server 표준 파이프라인과 독립적으로 작동하며,
GUI 표시 목적으로만 사용됩니다.
"""

import copy
from typing import Dict, Any


def filter_measurements(measurements: Dict[str, Any]) -> Dict[str, Any]:
    """
    raw 점수 필터링
    
    Args:
        measurements: 측정 점수 딕셔너리
        
    Returns:
        _raw로 끝나는 키를 제외한 딕셔너리
    """
    return {k: v for k, v in measurements.items() if not k.endswith("_raw")}


def extract_raw_measurements(measurements: Dict[str, Any]) -> Dict[str, Any]:
    """
    raw 점수 추출
    
    Args:
        measurements: 측정 점수 딕셔너리
        
    Returns:
        _raw로 끝나는 키만 포함하는 딕셔너리
    """
    return {k: v for k, v in measurements.items() if k.endswith("_raw")}


def apply_score_offset(
    score_data: Dict[str, Any],
    offset_config: Dict[str, Any],
    weights: Dict[str, float],
    max_score_limit: float = 90.0
) -> Dict[str, Any]:
    """
    점수 offset 보정 적용
    
    Args:
        score_data: {"overall": float, "measurements": dict} 형태의 점수 데이터
        offset_config: offset 설정 {"enabled": bool, "offset": float}
        weights: 측정항목별 가중치
        max_score_limit: 최대 점수 제한 (기본 90.0)
        
    Returns:
        offset 보정이 적용된 점수 데이터
    """
    if not offset_config.get("enabled", False):
        return score_data

    offset = offset_config.get("offset", 0.0)
    if offset == 0.0:
        return score_data

    # 세부항목에 가중치 비례로 offset 배분
    measurements = score_data.get("measurements", {})
    total_weight = sum(weights.get(k, 0.0) for k in measurements.keys())
    adjusted_measurements = {}

    for key, value in measurements.items():
        weight = weights.get(key, 0.0)
        if total_weight > 0 and weight > 0:
            item_offset = offset * (weight / total_weight)
            adjusted_measurements[key] = min(max_score_limit, value + item_offset)
        else:
            adjusted_measurements[key] = value

    # 피부건강지수에 offset 적용
    overall = score_data.get("overall", 0.0)
    adjusted_overall = min(max_score_limit, overall + offset)

    return {
        "overall": adjusted_overall,
        "measurements": adjusted_measurements
    }


def apply_score_offset_v2(
    score_data: Dict[str, Any],
    offset_config: Dict[str, Any],
    weights: Dict[str, float],
    max_score_limit: float = 90.0
) -> Dict[str, Any]:
    """
    점수 offset 보정 적용 (v2 - apply_score_offset와 동일, 호환성 유지)
    
    Args:
        score_data: {"overall": float, "measurements": dict} 형태의 점수 데이터
        offset_config: offset 설정 {"enabled": bool, "offset": float}
        weights: 측정항목별 가중치
        max_score_limit: 최대 점수 제한 (기본 90.0)
        
    Returns:
        offset 보정이 적용된 점수 데이터
    """
    return apply_score_offset(score_data, offset_config, weights, max_score_limit)


def postprocess_gui_display_scores(
    analysis_result: Dict[str, Any],
    offset_config: Dict[str, Any],
    weights: Dict[str, float],
    max_score_limit: float = 90.0
) -> Dict[str, Any]:
    """
    GUI 표시용 점수 후처리
    
    이 함수는 AnalysisService.run()의 결과를 받아 GUI 표시용으로 후처리합니다:
    1. raw 점수 필터링
    2. offset 보정 적용
    
    Args:
        analysis_result: AnalysisService.run()의 결과
        offset_config: offset 설정
        weights: 측정항목별 가중치
        max_score_limit: 최대 점수 제한
        
    Returns:
        후처리된 점수 데이터 {"overall": float, "measurements": dict}
    """
    # measurements_report 또는 measurements 키에서 점수 추출
    measurements = analysis_result.get("measurements_report") or analysis_result.get("measurements", {})
    overall = float(analysis_result.get("overall_score_report", analysis_result.get("overall_score", 0)))
    
    # raw 점수 필터링
    filtered_measurements = filter_measurements(measurements)
    
    # offset 보정 적용
    score_data = {
        "overall": overall,
        "measurements": filtered_measurements
    }
    adjusted_score = apply_score_offset(score_data, offset_config, weights, max_score_limit)
    
    return adjusted_score


def load_scoring_config() -> tuple:
    """
    점수 설정 로드
    
    Returns:
        (offset_config, weights, max_score_limit) 튜플
    """
    try:
        from src.scoring.skin_scoring import _load_scoring_config
        scoring_config = _load_scoring_config()
        offset_config = scoring_config.get("score_offset", {})
        weights = scoring_config.get("measurement_weights", {})
        safety_net_config = scoring_config.get("score_safety_net", {})
        max_score_limit = float(safety_net_config.get("max_score_limit", 90.0))
        return offset_config, weights, max_score_limit
    except Exception:
        return {}, {}, 90.0
