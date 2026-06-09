"""
src.db.result_parser
====================
파이프라인 결과에서 점수 추출 유틸리티.

[REFACTOR P0-8, P0-9] skin_analysis_db.py와 supabase_sync.py의 중복 로직을 통합.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def extract_overall_scores(json_result: Dict[str, Any]) -> Tuple[float, float]:
    """run_analysis_pipeline() 결과에서 원본·복원 종합 점수 추출.

    Args:
        json_result: run_analysis_pipeline()의 반환값 딕셔너리

    Returns:
        (overall_score_original, overall_score_restored) 튜플

    Notes:
        - analysis_result 키에서 overall_score와 overall_score_report를 추출
        - overall_score가 없으면 0.0 반환
        - overall_score_report가 없으면 overall_score와 동일한 값 반환
    """
    if json_result is None:
        return 0.0, 0.0
    ar = json_result.get("analysis_result", {})
    orig = float(ar.get("overall_score", 0))
    rest = float(ar.get("overall_score_report", orig))
    return orig, rest
