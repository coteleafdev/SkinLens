"""src.scoring._breakpoints — 점수 브레이크포인트 및 이미지 처리 파라미터.

[REFACTOR] skin_scoring.py에서 분리.
  - _get_default_breakpoints / _get_metric_bp / _get_metric_bp_count
  - _get_image_processing_params
  - _get_clahe_params / _get_blob_detection_params / _get_freckle_detection_params

브레이크포인트는 최초 호출 시 config.json에서 로드 후 모듈 캐시에 보관.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

log = logging.getLogger(__name__)

# ── 브레이크포인트 ──────────────────────────────────────────────────

def _get_default_breakpoints() -> Dict[str, List[List[float]]]:
    from src.scoring.config._config import _load_scoring_config
    config = _load_scoring_config()
    bp_config = config.get("breakpoints", {})
    area_default = (bp_config.get("area_default")
                    or [[0.0, 100.0], [0.01, 80.0], [0.03, 60.0],
                        [0.07, 40.0], [0.15, 20.0], [0.20, 0.0]])
    count_default = (bp_config.get("count_default")
                     or [[0, 100.0], [5, 80.0], [15, 60.0],
                         [30, 40.0], [60, 20.0], [100, 0.0]])
    bps: Dict[str, List] = {
        "area_default": area_default,
        "count_default": count_default,
    }
    for name in [
        "melasma_score", "freckle_score", "freckle_score_count",
        "redness_score", "post_inflammatory_erythema_score",
        "acne_score", "post_acne_pigment_score",
        "pore_size_score", "pore_sagging_score",
        "eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score",
        "roughness_score", "skin_type_score", "jawline_blur_score",
    ]:
        bp = bp_config.get(name)
        if bp:
            bps[name] = bp
    return bps


# 모듈 레벨 캐시 — 첫 호출 시 초기화
_DEFAULT_BREAKPOINTS: Dict[str, List] = {}


def _ensure_breakpoints() -> Dict[str, List]:
    global _DEFAULT_BREAKPOINTS
    if not _DEFAULT_BREAKPOINTS:
        _DEFAULT_BREAKPOINTS = _get_default_breakpoints()
    return _DEFAULT_BREAKPOINTS


def _get_metric_bp(metric_name: str) -> List[Tuple[float, float]]:
    bps = _ensure_breakpoints()
    bp = bps.get(metric_name) or bps["area_default"]
    return [(float(bp[i][0]), float(bp[i][1])) for i in range(len(bp))]


def _get_metric_bp_count(metric_name: str) -> List[Tuple[int, float]]:
    bps = _ensure_breakpoints()
    bp = bps.get(metric_name) or bps["count_default"]
    return [(int(bp[i][0]), float(bp[i][1])) for i in range(len(bp))]


# ── 이미지 처리 파라미터 ────────────────────────────────────────────

def _get_image_processing_params() -> Dict[str, Any]:
    from src.scoring.config._config import _load_scoring_config
    config = _load_scoring_config()
    img_proc = config.get("image_processing", {})
    clahe    = img_proc.get("clahe", {})
    blob     = img_proc.get("blob_detection", {})
    freckle  = img_proc.get("freckle_detection", {})
    return {
        "clahe": {
            "clip_limit":      clahe.get("clip_limit", 2.0),
            "clip_limit_pore": clahe.get("clip_limit_pore", 2.2),
            "tile_grid_size":  tuple(clahe.get("tile_grid_size", [8, 8])),
        },
        "blob_detection": {
            "thresholds": blob.get("thresholds", [0.055, 0.042, 0.030, 0.022]),
            "min_sigma":  blob.get("min_sigma", 1.12),
            "max_sigma":  blob.get("max_sigma", 6.5),
            "overlap":    blob.get("overlap", 0.35),
            "num_sigma":  blob.get("num_sigma", 6),
        },
        "freckle_detection": {
            "threshold": freckle.get("threshold", 0.08),
            "min_sigma": freckle.get("min_sigma", 1.0),
            "max_sigma": freckle.get("max_sigma", 5.0),
            "overlap":   freckle.get("overlap", 0.4),
        },
    }


_IMAGE_PROC_PARAMS: Dict[str, Any] = {}


def _ensure_image_proc_params() -> Dict[str, Any]:
    global _IMAGE_PROC_PARAMS
    if not _IMAGE_PROC_PARAMS:
        _IMAGE_PROC_PARAMS = _get_image_processing_params()
    return _IMAGE_PROC_PARAMS


def _get_clahe_params(use_pore: bool = False) -> Tuple[float, Tuple[int, int]]:
    clahe = _ensure_image_proc_params()["clahe"]
    clip_limit = clahe["clip_limit_pore"] if use_pore else clahe["clip_limit"]
    return clip_limit, clahe["tile_grid_size"]


def _get_blob_detection_params() -> Dict[str, Any]:
    return _ensure_image_proc_params()["blob_detection"]


def _get_freckle_detection_params() -> Dict[str, Any]:
    return _ensure_image_proc_params()["freckle_detection"]
