"""src.scoring._report — 보고서 항목 레이어 (레이어 B).

[REFACTOR] skin_scoring.py에서 분리.
  - REPORT_WEIGHTS, REPORT_KEYS, _REPORT_CATEGORIES, REPORT_DISPLAY_NAMES (lazy getter)
  - _compute_overall_score_report
  - ReportLayer
  - measurement_report_string

REPORT_* 상수는 모듈 레벨 I/O를 없애기 위해 lazy getter 함수로 제공.
하위 호환을 위해 동일 이름 속성도 노출한다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.skin.core.scoring_utils import clamp as _clamp
from src.skin.core.config_parser import get_measurement_count

log = logging.getLogger(__name__)


# ── Lazy 접근자 ──────────────────────────────────────────────────────

def get_report_weights() -> Dict[str, float]:
    from src.scoring.config._config import get_measurement_weights
    return get_measurement_weights()


def get_report_keys() -> List[str]:
    return list(get_report_weights().keys())


def get_report_categories() -> List[Tuple[str, List[str]]]:
    from src.scoring.config._config import get_categories
    return get_categories()


def get_report_display_names() -> Dict[str, str]:
    from src.scoring.config._config import get_display_names
    return get_display_names()


# ── 하위 호환 모듈-레벨 속성 (lazy 초기화) ───────────────────────────

class _LazyReportAttr:
    """모듈 레벨 REPORT_* 속성을 lazy하게 제공하는 내부 헬퍼."""
    _weights: Optional[Dict[str, float]] = None
    _keys: Optional[List[str]] = None
    _categories: Optional[List] = None
    _display_names: Optional[Dict[str, str]] = None

    @classmethod
    def weights(cls) -> Dict[str, float]:
        if cls._weights is None:
            cls._weights = get_report_weights()
        return cls._weights

    @classmethod
    def keys(cls) -> List[str]:
        if cls._keys is None:
            cls._keys = list(cls.weights().keys())
        return cls._keys

    @classmethod
    def categories(cls) -> List:
        if cls._categories is None:
            cls._categories = get_report_categories()
        return cls._categories

    @classmethod
    def display_names(cls) -> Dict[str, str]:
        if cls._display_names is None:
            cls._display_names = get_report_display_names()
        return cls._display_names


# ── 종합 점수 ────────────────────────────────────────────────────────

def _compute_overall_score_report(
    measurements_report: Dict[str, object], *, debug: bool = False
) -> float:
    weights = _LazyReportAttr.weights()
    weighted_sum = 0.0
    total_w = sum(weights.values())
    for key, w in weights.items():
        v = measurements_report.get(key)
        if v is None:
            continue
        try:
            weighted_sum += float(v) * w
        except (TypeError, ValueError):
            if debug:
                log.debug("[report] 키 %r 값 %r 스킵", key, v)
    return round(weighted_sum / total_w, 1) if total_w > 0 else 0.0


# ── ReportLayer ─────────────────────────────────────────────────────

class ReportLayer:
    """레이어 B — v3 엔진 출력을 보고서 항목으로 역매핑."""

    def build(
        self,
        m2_raw: Dict[str, float],
        m3_raw: Dict[str, float],
        *,
        raw_measurements: Optional[Dict[str, float]] = None,
        debug: bool = False,
    ) -> Tuple[Dict[str, Any], float]:
        from src.scoring._score_utils import _map_score_display_10_90
        from src.skin.core.config_parser import get_improvement_threshold, get_min_score

        report_keys = _LazyReportAttr.keys()
        m18: Dict[str, float] = {}
        _raw = raw_measurements or {}

        for key in report_keys:
            if key in m2_raw and m2_raw[key] is not None:
                # 데이터 타입 검증 및 변환
                try:
                    value = float(m2_raw[key])
                    m18[key] = round(_clamp(value), 1)
                except (TypeError, ValueError):
                    # 타입 변환 실패 시 기본값 사용
                    m18[key] = 0.0
                continue
            if key in _raw and _raw[key] is not None:
                # 데이터 타입 검증 및 변환
                try:
                    value = float(_raw[key])
                    m18[key] = round(_clamp(value), 1)
                    if debug:
                        log.debug("[레이어B] %s: raw_measurements 복원 %.1f", key, m18[key])
                except (TypeError, ValueError):
                    # 타입 변환 실패 시 기본값 사용
                    m18[key] = 0.0
                    if debug:
                        log.debug("[레이어B] %s: raw_measurements 타입 변환 실패, 기본값 사용", key)
                continue
            fallback = self._fallback_from_v3(key, m3_raw)
            m18[key] = round(_clamp(fallback), 1)
            if debug:
                log.debug("[레이어B] %s: v3 역산 %.1f", key, fallback)

        overall_raw = _compute_overall_score_report(m18, debug=debug)
        min_score = get_min_score()
        improvement_threshold = get_improvement_threshold()

        m18_display: Dict[str, Any] = {}
        for k, v in m18.items():
            m18_display[f"{k}_raw"] = v
            # 데이터 타입 검증 및 변환
            try:
                # v가 시퀀스인 경우 첫 번째 요소 사용
                if isinstance(v, (list, tuple)):
                    if len(v) > 0:
                        v = float(v[0])
                    else:
                        v = 0.0
                else:
                    v = float(v)
                transformed = _map_score_display_10_90(v)
                if transformed < improvement_threshold:
                    transformed = min_score
                m18_display[k] = transformed
            except (TypeError, ValueError, IndexError) as e:
                # 타입 변환 실패 시 기본값 사용
                if debug:
                    log.debug("[레이어B] %s: 점수 변환 실패 (%s), 기본값 사용", k, e)
                m18_display[k] = min_score

        m18_display["overall_score_report_raw"] = overall_raw
        # overall_raw도 시퀀스일 수 있음
        try:
            if isinstance(overall_raw, (list, tuple)):
                if len(overall_raw) > 0:
                    overall_raw = float(overall_raw[0])
                else:
                    overall_raw = 0.0
            else:
                overall_raw = float(overall_raw)
            overall_display = _map_score_display_10_90(overall_raw)
            if overall_display < improvement_threshold:
                overall_display = min_score
        except (TypeError, ValueError, IndexError) as e:
            if debug:
                log.debug("[레이어B] overall_score 변환 실패 (%s), 기본값 사용", e)
            overall_display = min_score
        return m18_display, round(overall_display, 1)

    @staticmethod
    def _fallback_from_v3(key: str, m3: Dict[str, float]) -> float:
        from src.skin.core.config_parser import get_score_mapping as _get_score_mapping_from_template
        score_mapping = _get_score_mapping_from_template()
        _F = m3.get
        if score_mapping:
            _MAP: Dict[str, float] = {}
            for k, v in score_mapping.items():
                # 메타데이터 키 필터링
                if k.startswith("_"):
                    continue
                # v가 리스트/튜플인지 확인
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    source_key, coefficient = v[0], v[1]
                else:
                    continue
                # [FIX] acne_score는 focal_lesion 대신 직접 acne_score 사용
                if k == "acne_score" and source_key == "focal_lesion":
                    value = _F("acne_score", 50.0)
                    # 데이터 타입 검증
                    if isinstance(value, (list, tuple)):
                        value = float(value[0]) if len(value) > 0 else 50.0
                    else:
                        value = float(value)
                    # coefficient도 시퀀스일 수 있음
                    if isinstance(coefficient, (list, tuple)):
                        coefficient = float(coefficient[0]) if len(coefficient) > 0 else 1.0
                    else:
                        coefficient = float(coefficient)
                    _MAP[k] = value * coefficient
                else:
                    value = _F(source_key, 50.0)
                    # 데이터 타입 검증
                    if isinstance(value, (list, tuple)):
                        value = float(value[0]) if len(value) > 0 else 50.0
                    else:
                        value = float(value)
                    # coefficient도 시퀀스일 수 있음
                    if isinstance(coefficient, (list, tuple)):
                        coefficient = float(coefficient[0]) if len(coefficient) > 0 else 1.0
                    else:
                        coefficient = float(coefficient)
                    _MAP[k] = value * coefficient
        else:
            # 데이터 타입 검증 추가
            def _safe_get(key, default):
                value = _F(key, default)
                if isinstance(value, (list, tuple)):
                    return float(value[0]) if len(value) > 0 else default
                return float(value)
            
            _MAP = {
                "melasma_score":                    _safe_get("pigmentation_cov", 50.0),
                "freckle_score":                    _safe_get("spot_density",     50.0),
                "redness_score":                    _safe_get("diffuse_redness",  50.0),
                "post_inflammatory_erythema_score": _safe_get("diffuse_redness",  50.0) * 0.85,
                "acne_score":                       _safe_get("acne_score",       50.0),  # [FIX] focal_lesion 대신 acne_score 직접 사용
                "post_acne_pigment_score":          _safe_get("focal_lesion",     50.0) * 0.90,
                "pore_size_score":                  _safe_get("pore_score",       50.0),
                "pore_sagging_score":               _safe_get("pore_score",       50.0) * 0.92,
                "eye_wrinkle_score":                _safe_get("wrinkle_score",    50.0),
                "nasolabial_wrinkle_score":         _safe_get("wrinkle_score",    50.0) * 0.92,
                "fine_deep_wrinkle_score":          _safe_get("wrinkle_score",    50.0) * 0.88,
                "roughness_score":                  _safe_get("roughness_score",  50.0),
                "skin_tone_score":                  _safe_get("tone_score",       50.0),
                "dullness_score":                   _safe_get("tone_score",       50.0) * 0.88,
                "uneven_tone_score":                _safe_get("tone_score",       50.0) * 0.92,
                "jawline_blur_score":               _safe_get("elasticity_score", 50.0),
                "skin_type_score":                  _safe_get("skin_type_score",  50.0),
            }
        return _MAP.get(key, 50.0)


# ── 보고서 문자열 ────────────────────────────────────────────────────

def measurement_report_string(results: Dict[str, Any]) -> str:
    meas    = results.get("measurements_report", {})
    ov_eng  = results.get("overall_score", "N/A")
    ov_rep  = results.get("overall_score_report", "N/A")
    age     = results.get("perceived_age", "N/A")
    weights = _LazyReportAttr.weights()
    cats    = _LazyReportAttr.categories()
    names   = _LazyReportAttr.display_names()
    measurement_count = get_measurement_count()

    lines_out: List[str] = [
        "", "=" * 65,
        f"  COTELEAF 피부 분석 v1.0  |  보고서 ({measurement_count}개 항목)",
        f"  종합 (보고서): {ov_rep}점  |  엔진 (직교): {ov_eng}점  |  인지 나이: {age}세",
        "=" * 65,
    ]
    _v3_approx_keys: set = {"dullness_score"}
    _raw_restored = set(results.get("raw_measurements", {}).keys())

    for cat_name, keys in cats:
        lines_out.append("")
        lines_out.append(f"【{cat_name}】")
        for k in keys:
            v    = meas.get(k, "N/A")
            name = names.get(k, k)
            w    = weights.get(k, 0.0)
            note = (
                ("  *직접" if k in _raw_restored else "  *v3근사")
                if k in _v3_approx_keys else ""
            )
            lines_out.append(f"    {name:<36} {str(v):>6}  (w={w:.3f}){note}")

    lines_out.extend(["", "=" * 65, ""])
    return "\n".join(lines_out)
