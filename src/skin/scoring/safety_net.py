"""
skin.scoring.safety_net
=======================
복원 이미지 점수 안전장치(Score Safety Net) 로직.

[REFACTOR P2] utils.apply_score_safety_net 에서 분리.

변경 사항:
  - GUI 의존(analyzer_compare_gui / PySide6)을 ``analyze_fn`` 파라미터 주입으로 교체.
    → CLI / 서버 환경에서 PySide6 없이 안전하게 호출 가능.
  - random.uniform 제거 → 결정적 중간값 사용 (동일 이미지 = 동일 결과).
  - 하위 호환 래퍼 apply_score_safety_net() 는 utils.py 에 유지.

사용:
    # 직접 호출 (GUI 환경):
    from skin.scoring.safety_net import apply_safety_net_logic
    from analyzer_compare_gui import analyze_compare_triple

    orig, adjusted, actual = apply_safety_net_logic(
        orig_path, final_path,
        analyze_fn=analyze_compare_triple,
    )

    # 기존 호환 경로 (utils.apply_score_safety_net) 는 변경 없음.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


from src.utils.config import load_config as _load_config


def _get_safety_net_details() -> dict:
    """safety_net_details 설정을 반환합니다."""
    config = _load_config()
    return config.get("safety_net_details", {})


def _get_score_safety_net_config() -> dict:
    """score_safety_net 설정을 반환합니다."""
    config = _load_config()
    return config.get("score_safety_net", {})


# AnalyzeFn: (orig, restored, restored) → (orig_result, restored_result, _)
AnalyzeFn = Callable[
    [Path, Path, Path],
    Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]],
]


def _ov(r: Dict[str, Any]) -> float:
    """결과 dict에서 종합 점수 추출."""
    if r is None:
        return 0.0
    v = r.get("overall_score_report") or r.get("overall_score")
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _recompute_overall(
    meas: Dict[str, Any],
    score_from_display_fn: Callable[[float], float],
    compute_overall_fn: Callable[[Dict[str, float]], float],
    map_display_fn: Callable[[float], float],
) -> Tuple[float, float]:
    """measurements_report 기준 피부건강지수 재계산.

    Returns:
        (raw_score, display_score)
    """
    internal: Dict[str, float] = {}
    for k, v in meas.items():
        if k.endswith("_raw"):
            continue
        try:
            internal[k] = score_from_display_fn(float(v))
        except (TypeError, ValueError):
            continue
    raw = compute_overall_fn(internal)
    return raw, map_display_fn(raw)


def apply_safety_net_logic(
    orig_path: Path,
    final_path: Path,
    *,
    analyze_fn: AnalyzeFn,
    score_fns: Optional[Dict[str, Any]] = None,
    pre_analyzed_original: Optional[Dict[str, Any]] = None,
    pre_analyzed_restored: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """점수 안전장치 핵심 로직.

    GUI 의존를 제거하고 analyze_fn 주입 방식으로 교체.
    기존 utils.apply_score_safety_net 과 동일한 반환 구조를 유지.

    Args:
        orig_path:   원본 이미지 경로.
        final_path:  복원 이미지 경로.
        analyze_fn:  (orig, restored, restored) → (orig_r, restored_r, _) 분석 함수.
                     기본값: None → lazy import로 analyzer_compare_gui 사용 (하위 호환).
        score_fns:   점수 변환 함수 주입용 dict. None 이면 skin_scoring 에서 로드.
                     키: score_from_display, compute_overall, map_display,
                         get_weights, get_config
        pre_analyzed_original: 이미 분석된 원본 결과 (재분석 방지용).
        pre_analyzed_restored: 이미 분석된 복원 결과 (재분석 방지용).

    Returns:
        (orig_result, adjusted_result, actual_result)
    """
    # ── 점수 변환 함수 로드 ───────────────────────────────────────────────
    if score_fns is None:
        try:
            from src.scoring.skin_scoring import (                       # noqa: PLC0415
                _map_score_display_10_90,
                _score_from_display_10_90,
                get_score_safety_net_config,
            )
            # [FIX 2026-05-24] v3 직교 체계 종합 점수 및 가중치 사용 (10개 항목)
            from src.skin.compose.score_composition import (          # noqa: PLC0415
                _compute_overall_score,
                _get_weights_cached,
            )
        except ImportError as e:
            raise ImportError(f"skin_scoring 필수 심볼 누락: {e}") from e
        score_fns = {
            "score_from_display": _score_from_display_10_90,
            "compute_overall":    _compute_overall_score,  # v3 직교 체계
            "map_display":        _map_score_display_10_90,
            "get_weights":        _get_weights_cached,  # v3 직교 가중치
            "get_config":         get_score_safety_net_config,
        }

    score_from_display_fn = score_fns["score_from_display"]
    compute_overall_fn    = score_fns["compute_overall"]
    map_display_fn        = score_fns["map_display"]
    weights: Dict[str, float] = score_fns["get_weights"]()
    safety_net_config: Dict[str, Any] = score_fns["get_config"]()

    # ── 분석 실행 ────────────────────────────────────────────────────────
    # [FIX BUG-3] pre_analyzed 파라미터가 있으면 재분석 방지
    # OR 조건으로 변경: 둘 중 하나만 있어도 해당 분석 사용, 없는 쪽은 직접 분석
    if pre_analyzed_original is not None or pre_analyzed_restored is not None:
        if pre_analyzed_original is not None:
            o = pre_analyzed_original
        else:
            o, _, _ = analyze_fn(orig_path, orig_path, orig_path)

        if pre_analyzed_restored is not None:
            i1_raw = pre_analyzed_restored
        else:
            from src.scoring.skin_scoring import SkinAnalyzer
            i1_raw = SkinAnalyzer().analyze_all(str(final_path))
    else:
        o, i1_raw, _ = analyze_fn(orig_path, final_path, final_path)

    i1        = copy.deepcopy(i1_raw)
    i1_actual = copy.deepcopy(i1_raw)

    orig_score    = _ov(o)
    restore_score = _ov(i1)
    score_diff    = restore_score - orig_score

    mo               = o.get("measurements_report") or o.get("measurements", {})
    measurements_report = i1.get("measurements_report") or i1.get("measurements", {})

    max_score_limit = float(safety_net_config.get("max_score_limit", 90.0))

    # [FIX] 안전장치를 패스스루로 변경: 점수가 합리적이면 수정하지 않음
    # 복원 점수가 원본과 비슷하거나 높으면 안전장치 적용하지 않음
    if restore_score >= orig_score - 5.0:
        log.info("[안전장치] 복원 점수(%.1f)가 원본(%.1f)과 비슷하거나 높아 안전장치 적용하지 않음", restore_score, orig_score)
        i1["overall_score_before_safety_net"] = restore_score
        i1["overall_score_report_before_safety_net"] = restore_score
        i1["overall_score_report"] = restore_score
        i1["safety_net_adjusted"] = False
        return o, i1, i1_actual

    # 투명성 메타데이터 초기화
    i1["overall_score_before_safety_net"]        = restore_score
    i1["overall_score_report_before_safety_net"] = restore_score
    i1["overall_score_report"]                   = restore_score
    i1["safety_net_adjusted"]                    = False
    i1["safety_net_adjusted_keys"]               = []

    clamp_keys: List[str] = []
    boost_keys: List[str] = []

    log.info(
        "[안전장치] 원본: %.1f  복원(실측): %.1f  차이: %+.1f",
        orig_score, restore_score, score_diff,
    )
    log.debug(
        "[안전장치] 원본: %.1f  복원(실측): %.1f  차이: %+.1f",
        orig_score, restore_score, score_diff,
    )

    def _recompute() -> Tuple[float, float]:
        return _recompute_overall(
            measurements_report, score_from_display_fn, compute_overall_fn, map_display_fn
        )

    # ── Step 1: 원본보다 낮은 항목 클램프 ────────────────────────────────
    # [FIX] 개별 항목 클램프 비활성화 - 종합 점수만 유지
    # 개별 항목 클램프는 점수를 과도하게 낮추는 문제가 있음
    overall_raw, overall_display = _recompute()

    # ── Step 2: 목표 점수 미달 시 추가 상향 조정 ─────────────────────────
    # [FIX] 상향 조정 비활성화하여 문제 격리
    pass

    # ── Step 3: 결과 반영 ────────────────────────────────────────────────
    all_adjusted = list(dict.fromkeys(clamp_keys + boost_keys))
    if all_adjusted:
        i1["safety_net_adjusted"]      = True
        i1["safety_net_clamp_keys"]    = list(dict.fromkeys(clamp_keys))
        i1["safety_net_boost_keys"]    = list(dict.fromkeys(boost_keys))
        i1["safety_net_adjusted_keys"] = all_adjusted
        for field in ("overall_score_report", "overall_score"):
            i1[field] = overall_display
        for field in ("overall_score_report_raw", "overall_score_raw"):
            if field in i1:
                i1[field] = overall_raw
    else:
        i1["overall_score_report"] = overall_display

    log.debug(
        "[안전장치] 실측: %.1f → 최종: %.1f (클램프: %d개, 상향: %d개)",
        restore_score, overall_display,
        len(dict.fromkeys(clamp_keys)), len(dict.fromkeys(boost_keys)),
    )
    return o, i1, i1_actual
