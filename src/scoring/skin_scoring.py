"""COTELEAF 피부 분석 시스템 v3.4 — 퍼사드 (Facade)

[REFACTOR v3.3 → v3.4] God Module 분해 완료.
  이 파일은 공개 API를 단일 진입점으로 re-export하는 퍼사드만 담당한다.
  실제 구현은 아래 내부 모듈에 있다:

  src/scoring/
    _config.py       — 설정 로드 (_load_scoring_config, get_* 접근자)
    _logging.py      — 로깅 설정
    _score_utils.py  — 점수 스케일 변환 (_map_score_*, _score_from_*, _apply_*)
    _breakpoints.py  — 브레이크포인트 / 이미지 처리 파라미터
    _core.py         — _SkinAnalyzerCore 오케스트레이터
    _multi_view.py   — LateralFaceAnalyzer, MultiViewMerger, analyze_all_multi
    _report.py       — ReportLayer, measurement_report_string

  src/skin/
    core/image_utils.py — _imread_bgr, _skin_mask, _skin_stat
    analyzers/          — 도메인별 분석 순수 함수
    compose/            — v3 직교 점수 조합

공개 API (Public API) — 변경 없음:
  SkinAnalyzer
  analyze_all_multi_v3, analyze_all_multi
  get_measurement_categories, get_measurement_weights
  get_report_keys, get_report_categories
  reload_scoring_config, get_restoration_config
  REPORT_DISPLAY_NAMES, measurement_report_string

내부 API (Internal API — 하위 호환용 re-export):
  _load_scoring_config, _imread_bgr
  _map_score_display_10_90, _score_from_display_10_90
  _compute_overall_score_report

사용법:
  from src.scoring.skin_scoring import SkinAnalyzer
  result = SkinAnalyzer().analyze_all("face.jpg")
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

import numpy as np

# ── 외부 의존 (하위 호환 re-export 용) ────────────────────────────
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None

try:
    from skimage.feature import blob_log, graycomatrix, graycoprops, local_binary_pattern
    from skimage.filters import gabor
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    blob_log = graycomatrix = graycoprops = local_binary_pattern = gabor = None

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  내부 모듈 import (구현 위임)
# ══════════════════════════════════════════════════════════════════

# 로깅
from src.scoring._logging import (
    configure_analyzer_logging as _configure_analyzer_logging,
    prepare_analyzer_logging_for_gui,
    restore_analyzer_logging_after_gui,
)

# 설정
from src.scoring.config._config import (
    _load_scoring_config,
    reload_scoring_config,
    get_measurement_weights,
    get_display_names,
    get_categories,
    get_actual_ranges,
    get_display_range,
    get_score_safety_net_config,
    get_restoration_config,
)

# 점수 변환 유틸
from src.scoring._score_utils import (
    _map_score_display_10_90,
    _map_score_display_10_90_adjusted,
    _score_from_display_10_90,
    _score_from_display_10_90_adjusted,
    _apply_measurements_display_10_90,
    _snap_score,
    _quantize_score_to_20,
    _adaptive_threshold,
)

# 브레이크포인트
from src.scoring._breakpoints import (
    _get_metric_bp,
    _get_metric_bp_count,
    _get_clahe_params,
    _get_blob_detection_params,
    _get_freckle_detection_params,
    _get_image_processing_params,
)

# 이미지 유틸
from src.skin.core.image_utils import (
    imread_bgr as _imread_bgr,
    skin_mask as _skin_mask,
    skin_stat as _skin_stat,
)

# 분석 코어
from src.scoring._core import (
    _SkinAnalyzerCore,
    _compute_overall_score_legacy,
    _LEGACY_MEASUREMENT_CATEGORIES,
    _measurement_report_string_legacy,
)

# 멀티뷰
from src.scoring._multi_view import (
    LateralFaceAnalyzer,
    MultiViewMerger,
    analyze_all_multi,
)

# 피부 타입 감지
from src.scoring.skin_type_detector import (
    SkinTypeFeatures,
    SkinTypeDetection,
    SkinTypeClassifier,
    extract_skin_type_features,
    detect_skin_type,
    get_skin_type_name,
)

# 보고서
from src.scoring._report import (
    ReportLayer,
    _compute_overall_score_report,
    measurement_report_string as measurement_report_string_legacy,
    get_report_weights,
    get_report_keys,
    get_report_categories,
    get_report_display_names,
)

# 직교 분해
from src.skin.compose.score_composition import (
    WEIGHTS, OUTPUT_KEYS,
    _compose_pigmentation_scores, _compose_redness_lesion_scores,
    _compose_pore_score, _compose_wrinkle_score, _compose_tone_score,
    _compose_elasticity_score, _compose_hydration_score, _compose_skin_type_score,
    _compose_roughness_score,
    _compute_overall_score, measurement_report_string,
)

# config_parser re-export (하위 호환)
from src.skin.core.config_parser import (
    load_prompt_template        as _load_prompt_template,
    extract_section             as _extract_section,
    parse_score_criteria        as _parse_score_criteria,
    get_display_names           as _get_display_names_from_template,
    parse_categories            as _parse_categories,
    get_categories              as _get_categories_from_template,
    parse_measurement_weights   as _parse_measurement_weights,
    get_measurement_weights     as _get_measurement_weights_from_template,
    parse_actual_ranges         as _parse_actual_ranges,
    get_actual_ranges           as _get_actual_ranges_from_template,
    parse_score_mapping         as _parse_score_mapping,
    get_score_mapping           as _get_score_mapping_from_template,
    get_improvement_threshold,
    get_min_score,
    get_category_count,
    get_measurement_count,
    get_orthogonal_count,
    get_composition_function_registry,
)
from src.skin.core.face_roi import FaceROI
from src.skin.core.face_detector import (
    _try_import_mediapipe,
    _MediaPipeFaceDetector,
    _HaarFaceDetector,
    FaceDetector,
)
from src.skin.analyzers.pigmentation import make_pigment_mask

# ── 하위 호환: 모듈 레벨 상수 (lazy getter로 노출) ─────────────────

def _get_report_weights() -> Dict[str, float]:
    return get_report_weights()

def _get_report_keys() -> List[str]:
    return get_report_keys()

def _get_report_categories() -> List[Tuple[str, List[str]]]:
    return get_report_categories()

def _get_report_display_names() -> Dict[str, str]:
    return get_report_display_names()

# 이전 코드가 모듈 레벨 상수로 참조하는 경우를 위한 lazy proxy
class _LazyDict(dict):
    """첫 접근 시 getter를 실행해 채우는 lazy dict.

    주의: 멀티스레드 환경에서 _ensure()는 경쟁 조건 가능성이 있습니다.
    그러나 getter 함수들은 config에서 값을 읽어오는 멱등(idempotent) 연산이므로,
    중복 호출되더라도 데이터 손상은 없으며 결과만 동일하게 반환됩니다.
    """
    def __init__(self, getter):
        super().__init__()
        self._getter = getter
        self._loaded = False

    def _ensure(self):
        if not self._loaded:
            self.update(self._getter())
            self._loaded = True

    def __getitem__(self, k):
        self._ensure(); return super().__getitem__(k)

    def __contains__(self, key):
        self._ensure()
        return super().__contains__(key)

    def __len__(self):
        self._ensure()
        return super().__len__()

    def __iter__(self):
        self._ensure(); return super().__iter__()

    def items(self):
        self._ensure(); return super().items()

    def keys(self):
        self._ensure(); return super().keys()

    def values(self):
        self._ensure(); return super().values()

    def get(self, k, default=None):
        self._ensure(); return super().get(k, default)


REPORT_WEIGHTS      = _LazyDict(get_report_weights)
REPORT_DISPLAY_NAMES = _LazyDict(get_report_display_names)

# REPORT_KEYS 및 _REPORT_CATEGORIES는 get_report_keys(), get_report_categories() 함수를 사용하세요


# ── TypedDicts ────────────────────────────────────────────────────

class AnalyzeAllResultDict(TypedDict):
    overall_score: float
    perceived_age: float
    measurements: Dict[str, Any]
    measurements_report: Dict[str, Any]
    overall_score_report: float


class AnalyzeAllMultiResultDict(TypedDict):
    overall_score: float
    perceived_age: float
    measurements: Dict[str, Any]
    measurements_report: Dict[str, Any]
    overall_score_report: float
    multi_view_detail: Dict[str, Dict[str, Any]]


# ── 하위 호환 alias ───────────────────────────────────────────────
# 주의: 이 alias들은 하위 호환성을 위해 유지되며, 향후 버전에서 제거될 수 있습니다.
# 새로운 코드에서는 직접 대상을 참조하세요.
_MEASUREMENT_CATEGORIES = _LEGACY_MEASUREMENT_CATEGORIES  # @deprecated: _LEGACY_MEASUREMENT_CATEGORIES 사용 (v2.0 제거 예정)


# ══════════════════════════════════════════════════════════════════
#  SkinAnalyzer — 공개 메인 클래스
# ══════════════════════════════════════════════════════════════════

class SkinAnalyzer:
    """직교 신호 분해 기반 피부 분석기.

    내부 CV 파이프라인은 _SkinAnalyzerCore에 위임.
    _compose_* 레이어(레이어 A): 18개 서브점수 → 10개 직교 출력.
    ReportLayer(레이어 B): 18개 보고서 항목 병렬 생성.
    """

    OUTPUT_KEYS: List[str] = OUTPUT_KEYS  # _OutputKeysProxy 인스턴스 (reload 지원)

    @property
    def report_keys(self) -> List[str]:
        return get_report_keys()

    @classmethod
    def get_report_keys(cls) -> List[str]:
        """보고서 키 목록 반환 (클래스 메서드)."""
        return get_report_keys()

    def __init__(self, face_detector: Optional[FaceDetector] = None) -> None:
        _configure_analyzer_logging()
        self._core      = _SkinAnalyzerCore(face_detector=face_detector)
        self._layer_b = ReportLayer()

    def _legacy_to_current(self, legacy_result: Dict[str, Any], debug: bool = False) -> Dict[str, Any]:
        m2 = legacy_result.get("measurements", {})
        m2_raw: Dict[str, float] = {
            k: (_score_from_display_10_90_adjusted(k, float(v))
                if isinstance(v, (int, float)) else 50.0)
            for k, v in m2.items()
        }
        if debug:
            log.debug("[legacy] core 서브점수 역변환 완료 (%d개)", len(m2_raw))

        pig  = {k: m2_raw.get(k, 50.0) for k in ("melasma_score", "freckle_score")}
        red  = {k: m2_raw.get(k, 50.0) for k in ("redness_score",)}
        acne = {k: m2_raw.get(k, 50.0) for k in ("acne_score", "post_acne_pigment_score")}
        pore = {k: m2_raw.get(k, 50.0) for k in ("pore_size_score", "pore_sagging_score")}
        wri  = {k: m2_raw.get(k, 50.0) for k in ("eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score")}
        tone = {k: m2_raw.get(k, 50.0) for k in ("skin_tone_score", "dullness_score", "uneven_tone_score")}
        ela  = {k: m2_raw.get(k, 50.0) for k in ("jawline_blur_score", "cheek_sagging_score")}
        # skin_type_score: _core.analyze_all()에서 직접 측정된 값을 사용
        # [FIX P0-3] dry_score, oily_score 키가 없으면 역산 오류 발생 → 직접 사용
        seb = {"skin_type_score": m2_raw.get("skin_type_score", 50.0)}

        m3: Dict[str, float] = {}
        m3.update(_compose_pigmentation_scores(pig))
        m3.update(_compose_redness_lesion_scores(red, acne))
        m3.update(_compose_pore_score(pore))
        m3.update(_compose_wrinkle_score(wri))
        m3.update(_compose_roughness_score(m2_raw))
        m3.update(_compose_tone_score(tone))
        m3.update(_compose_elasticity_score(ela))
        m3.update(_compose_hydration_score(seb))

        if debug:
            for k, v in m3.items():
                log.debug("  [레이어A] %-25s %.1f (내부 0~100)", k, v)

        m3_raw_for_b = dict(m3)
        _apply_measurements_display_10_90(m3)
        filtered_a = {k: m3.get(k) for k in OUTPUT_KEYS}
        # skin_type_label 추가 (OUTPUT_KEYS에 없으므로 별도 추가)
        filtered_a["skin_type_label"] = legacy_result.get("measurements", {}).get("skin_type_label", "중성")

        _raw_meas = legacy_result.get("raw_measurements") or {}
        m18_display, overall_v18 = self._layer_b.build(
            m2_raw, m3_raw_for_b, raw_measurements=_raw_meas, debug=debug
        )
        if debug:
            log.debug("[레이어B → overall] %.1f", overall_v18)

        return {
            "overall_score":        overall_v18,
            "overall_score_report": overall_v18,
            "perceived_age":        legacy_result.get("perceived_age", 0.0),
            "measurements":         filtered_a,
            "measurements_report":  m18_display,
            "skin_stat":            legacy_result.get("skin_stat"),
            "skin_type_label":      legacy_result.get("measurements", {}).get("skin_type_label", "중성"),
        }

    def analyze_all(
        self,
        image_path: str,
        debug: bool = False,
        clahe_preprocessed: bool = False,
        ref_stat: Optional[Dict[str, float]] = None,
        origin_image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        effective_ref_stat = ref_stat
        if effective_ref_stat is None and origin_image_path is not None:
            try:
                if Path(origin_image_path).exists():
                    _img_orig = _imread_bgr(origin_image_path)
                    if _img_orig is not None:
                        _face_o, _ = self._core._extract_face(_img_orig)
                        _smask_o   = _skin_mask(_face_o)
                        _lab_o     = cv2.cvtColor(_face_o, cv2.COLOR_BGR2LAB)
                        _stat_o    = _skin_stat(_lab_o, _smask_o)
                        _fh, _fw   = _face_o.shape[:2]
                        _pig_sm    = make_pigment_mask(_smask_o, _fh, _fw)
                        _pig_st    = _skin_stat(_lab_o, _pig_sm)
                        effective_ref_stat = {
                            **_stat_o,
                            "pig_base_L": _pig_st["base_L"], "pig_std_L": _pig_st["std_L"],
                            "pig_base_b": _pig_st["base_b"], "pig_std_b": _pig_st["std_b"],
                            "pig_base_a": _pig_st["base_a"], "pig_std_a": _pig_st["std_a"],
                        }
                        if debug:
                            log.debug("[v3.6] ref_stat 자동 추출: base_L=%.1f", _stat_o["base_L"])
            except Exception as _e:
                log.warning("[v3.6] origin ref_stat 추출 실패: %s", _e)

        legacy_result = self._core.analyze_all(
            image_path, debug=debug,
            clahe_preprocessed=clahe_preprocessed,
            ref_stat=effective_ref_stat,
        )
        return self._legacy_to_current(legacy_result, debug=debug)

    def print_results(self, results: Dict[str, Any]) -> None:
        print(measurement_report_string(results), end="")

    def print_results_report(self, results: Dict[str, Any]) -> None:
        print(measurement_report_string_legacy(results), end="")


# ══════════════════════════════════════════════════════════════════
#  MultiViewMergerV3
# ══════════════════════════════════════════════════════════════════

class MultiViewMergerV3(MultiViewMerger):
    """v2 MultiViewMerger 상속 + v3 직교 변환 후처리."""

    def __init__(self, face_detector=None) -> None:
        super().__init__()
        self._v3_layer = SkinAnalyzer(face_detector=face_detector)

    def merge_v3(
        self,
        front_result: Dict[str, Any],
        left_lateral: Dict[str, Optional[float]],
        right_lateral: Dict[str, Optional[float]],
        debug: bool = False,
    ) -> Dict[str, Any]:
        merged_legacy = self.merge(front_result, left_lateral, right_lateral, debug=debug)
        return self._v3_layer._legacy_to_current(merged_legacy, debug=debug)


# ── 싱글턴 ────────────────────────────────────────────────────────

_DEFAULT_ANALYZER: Optional[SkinAnalyzer] = None


def _get_default_analyzer() -> SkinAnalyzer:
    global _DEFAULT_ANALYZER
    if _DEFAULT_ANALYZER is None:
        _DEFAULT_ANALYZER = SkinAnalyzer()
    return _DEFAULT_ANALYZER


# ── 공개 진입점 ───────────────────────────────────────────────────

def analyze_all_multi_v3(
    front_path: str,
    left45_path: Optional[str] = None,
    right45_path: Optional[str] = None,
    debug: bool = False,
    clahe_preprocessed: bool = False,
    use_full_analysis: bool = True,
) -> Dict[str, Any]:
    """
    3장 멀티뷰 진입점 v3.0.
    
    Args:
        front_path: 정면 이미지 경로
        left45_path: 좌측 45° 이미지 경로 (선택)
        right45_path: 우측 45° 이미지 경로 (선택)
        debug: 디버그 모드
        clahe_preprocessed: CLAHE 전처리 여부
        use_full_analysis: 측면 이미지 전체 분석 여부 (기본 True)
    
    Returns:
        통합된 분석 결과
    """
    legacy_result = analyze_all_multi(
        front_path, left45_path, right45_path,
        debug=debug, clahe_preprocessed=clahe_preprocessed,
        use_full_analysis=use_full_analysis,
    )
    return _get_default_analyzer()._legacy_to_current(legacy_result, debug=debug)


def get_measurement_categories() -> List[Tuple[str, List[str]]]:
    """측정항목 카테고리 반환 (public API)."""
    return _MEASUREMENT_CATEGORIES


# ── 하위 호환 alias ───────────────────────────────────────────────
# 주의: 이 alias들은 하위 호환성을 위해 유지되며, 향후 버전에서 제거될 수 있습니다.
# 새로운 코드에서는 SkinAnalyzer를 직접 사용하세요.
SkinAnalyzerV3 = SkinAnalyzer  # @deprecated: SkinAnalyzer 사용 (v2.0 제거 예정)
# 변환 메서드 하위 호환용 alias
SkinAnalyzer._core_to_v3 = SkinAnalyzer._legacy_to_current  # @deprecated: _legacy_to_current 사용 (v2.0 제거 예정)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="COTELEAF 측정항목 단독 실행")
    ap.add_argument("image")
    ap.add_argument("--clahe", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ns = ap.parse_args()
    an = SkinAnalyzer()
    res = an.analyze_all(ns.image, debug=ns.debug, clahe_preprocessed=ns.clahe)
    an.print_results(res)
    an.print_results_report(res)
