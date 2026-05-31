"""
skin.core.analyze_utils
=======================
GUI 의존 없는 분석 유틸리티 함수.

[REFACTOR P1-18] analyzer_compare_gui.py에서 분리하여 서버 환경에서도 사용 가능.
"""
from __future__ import annotations

from typing import Any, Dict
from pathlib import Path


def analyze_compare_triple(
    orig_path: str | Path,
    ideal1_path: str | Path,
    ideal2_path: str | Path,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """비교 계산기와 동일: 이상1·2 분석 후 skin_stat 평균을 ref_stat 으로 원본 재분석.

    [FIX v1.0] ref_stat 사용 제거: 독립적 측정으로 변경하여 실제 복원 효과를 점수에 반영.
    """
    from src.scoring.skin_scoring import SkinAnalyzer

    an = SkinAnalyzer()
    ideal1 = an.analyze_all(str(ideal1_path), debug=False, clahe_preprocessed=False)
    ideal2 = an.analyze_all(str(ideal2_path), debug=False, clahe_preprocessed=False)
    # [FIX v1.0] ref_stat 사용 제거: 독립적 측정
    orig = an.analyze_all(
        str(orig_path),
        debug=False,
        clahe_preprocessed=False,
        ref_stat=None,  # 독립적 측정: 이상 이미지 기준 사용 안 함
    )
    return orig, ideal1, ideal2
