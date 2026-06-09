"""src.scoring._score_utils — 점수 스케일 변환 유틸리티.

[REFACTOR] skin_scoring.py에서 분리.
  - _map_score_display_10_90 / _adjusted
  - _score_from_display_10_90 / _adjusted
  - _apply_measurements_display_10_90
  - _snap_score, _quantize_score_to_20
  - _adaptive_threshold
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np

from src.skin.core.scoring_utils import clamp as _clamp

log = logging.getLogger(__name__)

_MEASUREMENT_ACTUAL_RANGES: Optional[Dict[str, tuple]] = None


def _get_measurement_actual_ranges() -> Dict[str, tuple]:
    global _MEASUREMENT_ACTUAL_RANGES
    if _MEASUREMENT_ACTUAL_RANGES is None:
        from src.scoring.config._config import get_actual_ranges
        _MEASUREMENT_ACTUAL_RANGES = get_actual_ranges()
    return _MEASUREMENT_ACTUAL_RANGES


def invalidate_actual_ranges_cache() -> None:
    """_MEASUREMENT_ACTUAL_RANGES 캐시를 초기화합니다."""
    global _MEASUREMENT_ACTUAL_RANGES
    _MEASUREMENT_ACTUAL_RANGES = None


def _map_score_display_10_90(v: float) -> float:
    x = _clamp(float(v), 0.0, 100.0)
    return round(10.0 + (x / 100.0) * 80.0, 1)


def _map_score_display_10_90_adjusted(key: str, v: float) -> float:
    x = _clamp(float(v), 0.0, 100.0)
    actual_ranges = _get_measurement_actual_ranges()
    if key not in actual_ranges:
        return _map_score_display_10_90(x)
    min_val, max_val = actual_ranges[key]
    if x <= min_val:
        return 10.0
    if x >= max_val:
        return 90.0
    return round(10.0 + (x - min_val) / (max_val - min_val) * 80.0, 1)


def _score_from_display_10_90(v: float) -> float:
    x = float(np.clip(float(v), 10.0, 90.0))
    return float(np.clip((x - 10.0) / 80.0 * 100.0, 0.0, 100.0))


def _score_from_display_10_90_adjusted(key: str, v: float) -> float:
    x = float(np.clip(float(v), 10.0, 90.0))
    actual_ranges = _get_measurement_actual_ranges()
    if key not in actual_ranges:
        return _score_from_display_10_90(x)
    min_val, max_val = actual_ranges[key]
    normalized = (x - 10.0) / 80.0
    return _clamp(min_val + normalized * (max_val - min_val), 0.0, 100.0)


def _apply_measurements_display_10_90(measurements: Dict[str, object]) -> None:
    from src.skin.core.config_parser import get_improvement_threshold, get_min_score
    min_score = get_min_score()
    improvement_threshold = get_improvement_threshold()
    for k, val in list(measurements.items()):
        if not k.endswith("_score"):
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            raw_key = f"{k}_raw"
            if raw_key not in measurements:
                measurements[raw_key] = float(val)
            transformed = _map_score_display_10_90_adjusted(k, float(val))
            if transformed < improvement_threshold:
                transformed = min_score
            measurements[k] = transformed


def _snap_score(score: float) -> int:
    s = float(np.clip(score, 0.0, 100.0))
    if s < 20:
        return 10
    elif s < 40:
        return 30
    elif s < 60:
        return 50
    elif s < 80:
        return 70
    else:
        return 90


def _quantize_score_to_20(val: float) -> int:
    v = _clamp(float(val))
    if v < 20:
        return 10
    elif v < 40:
        return 30
    elif v < 60:
        return 50
    elif v < 80:
        return 70
    else:
        return 90


def _adaptive_threshold(
    channel: np.ndarray,
    mask: Optional[np.ndarray],
    z: float = 1.5,
) -> float:
    px = (channel[mask > 0].astype(float)
          if mask is not None and mask.any()
          else channel.astype(float).ravel())
    if len(px) == 0:
        return float(np.mean(channel)) - 20.0
    return float(np.median(px)) - z * float(np.std(px))
