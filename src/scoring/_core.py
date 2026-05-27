"""src.scoring._core — _SkinAnalyzerCore 오케스트레이터.

[REFACTOR] skin_scoring.py에서 분리.

각 도메인 분석은 src/skin/analyzers/ 패키지의 순수 함수에 위임.
이 클래스는 얼굴 검출 → ROI 분할 → 도메인 분석 호출 → 결과 취합만 담당.
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None  # type: ignore

from src.skin.core.face_roi import FaceROI
from src.skin.core.face_detector import FaceDetector
from src.skin.core.scoring_utils import clamp as _clamp
from src.skin.core.image_utils import imread_bgr as _imread_bgr, skin_mask as _skin_mask, skin_stat as _skin_stat
from src.skin.core.scoring_utils import safe_region as _safe_region
from src.skin.analyzers.pigmentation import analyze_pigmentation, make_pigment_mask
from src.skin.analyzers.redness import analyze_redness
from src.skin.analyzers.pore import analyze_pores
from src.skin.analyzers.wrinkle_texture import (
    analyze_wrinkles,
    analyze_texture,
    analyze_restoration_quality,
)
from src.skin.analyzers.tone_elasticity import (
    analyze_tone,
    analyze_elasticity,
    analyze_dark_circle,
    analyze_sebum,
    analyze_acne_marks,
    analyze_perceived_age,
)
from src.scoring._breakpoints import (
    _get_metric_bp,
    _get_metric_bp_count,
    _get_clahe_params,
    _get_blob_detection_params,
    _get_freckle_detection_params,
)
from src.scoring._score_utils import (
    _map_score_display_10_90,
    _score_from_display_10_90_adjusted,
    _apply_measurements_display_10_90,
)


# ── 배열 스택 헬퍼 ─────────────────────────────────────────────────────

def _safe_vstack(parts: List[np.ndarray]) -> np.ndarray:
    """안전한 수직 스택 - 빈 배열이나 크기 불일치 처리."""
    parts = [p for p in parts if isinstance(p, np.ndarray) and p.size > 0]
    if not parts:
        return np.zeros((10, 10, 3), np.uint8)
    if len(parts) == 1:
        return parts[0]
    w_ = min(p.shape[1] for p in parts)
    if w_ <= 0:
        return parts[0]
    try:
        return np.vstack([p[:, :w_] for p in parts])
    except Exception:
        return parts[0]


def _safe_hstack(parts: List[np.ndarray]) -> np.ndarray:
    """안전한 수평 스택 - 빈 배열이나 크기 불일치 처리."""
    parts = [p for p in parts if isinstance(p, np.ndarray) and p.size > 0]
    if not parts:
        return np.zeros((10, 10, 3), np.uint8)
    if len(parts) == 1:
        return parts[0]
    h_ = min(p.shape[0] for p in parts)
    if h_ <= 0:
        return parts[0]
    try:
        return np.hstack([p[:h_, :] for p in parts])
    except Exception:
        return parts[0]

log = logging.getLogger(__name__)


# ── v2 종합 점수 계산 ────────────────────────────────────────────────

def _compute_overall_score_legacy(
    measurements: Dict[str, object], *, debug: bool = False
) -> float:
    from src.scoring.config._config import get_measurement_weights
    weights = get_measurement_weights()
    total_w = sum(w for w in weights.values() if w > 0)
    weighted_sum = 0.0
    for key, w in weights.items():
        if w == 0.0:
            continue
        v = measurements.get(key)
        if v is None:
            continue
        try:
            weighted_sum += float(v) * w
        except (TypeError, ValueError):
            if debug:
                log.debug("종합 점수 키 %r 값 %r 스킵", key, v)
    return round(weighted_sum / total_w, 1) if total_w > 0 else 0.0


# ── v2 측정 카테고리 (보고서용) ──────────────────────────────────────

_LEGACY_MEASUREMENT_CATEGORIES: List[Tuple[str, List[str]]] = [
    ("색소 (Pigmentation)",       ["melasma_score", "freckle_score"]),
    ("홍조, 홍반 (Redness)",       ["redness_score", "post_inflammatory_erythema_score"]),
    ("트러블·흔적 (Acne & Marks)", ["acne_score", "post_acne_pigment_score"]),
    ("모공 (Pore)",               ["pore_size_score", "pore_sagging_score"]),
    ("주름 (Wrinkle)",            ["eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score"]),
    ("텍스처 (Texture)",          ["roughness_score"]),
    ("톤·밝기 (Tone)",            ["skin_tone_score", "dullness_score", "uneven_tone_score"]),
    ("탄력 (Elasticity)",         ["jawline_blur_score", "cheek_sagging_score"]),
    ("피부 타입 (Skin Type)",      ["skin_type_score"]),
]


def _measurement_report_string_legacy(results: Dict[str, Any]) -> str:
    meas = results.get("measurements", {})
    ov   = results.get("overall_score", "N/A")
    age  = results.get("perceived_age", "N/A")
    lines: List[str] = [
        "", "=" * 65,
        f"  COTELEAF 피부 분석  |  종합: {ov}점  |  인지 나이: {age}세",
        "=" * 65,
    ]
    for cat_name, keys in _LEGACY_MEASUREMENT_CATEGORIES:
        lines.append("")
        lines.append(f"  ■ {cat_name}")
        for k in keys:
            v = meas.get(k, "N/A")
            lines.append(f"    {k:<35} {v} (10~90)")
    lines.extend(["", "=" * 65, ""])
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  _SkinAnalyzerCore
# ══════════════════════════════════════════════════════════════════

class _SkinAnalyzerCore:
    """내부 CV 파이프라인 (직접 사용 금지 — SkinAnalyzer 경유).

    책임: 얼굴 검출 → ROI 분할 → 도메인 분석 위임 → 결과 취합.
    스코어 변환·보고서 생성은 담당하지 않는다.
    """

    OUTPUT_KEYS: List[str] = [
        "melasma_score", "freckle_score", "pih_score",
        "redness_score", "post_inflammatory_erythema_score",
        "acne_score", "post_acne_pigment_score", "focal_lesion",
        "pore_size_score", "pore_sagging_score",
        "eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score",
        "roughness_score",
        "skin_tone_score", "dullness_score", "uneven_tone_score",
        "jawline_blur_score", "cheek_sagging_score",
        "oily_score", "skin_type_score",
        "noise_score", "color_balance_score", "detail_score",
    ]

    def __init__(
        self,
        face_detector: Optional[FaceDetector] = None,
        analyzers: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.face_detector = face_detector if face_detector is not None else FaceDetector()
        self.analyzers = analyzers or self._get_default_analyzers()

    def _get_default_analyzers(self) -> Dict[str, Any]:
        try:
            from src.skin.analyzers import AnalyzerRegistry, register_analyzers_from_config
            from src.scoring.config._config import _load_scoring_config
            
            register_analyzers_from_config()
            
            # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
            config = _load_scoring_config()
            prescription_config = config.get("prescription", {}) if config else {}
            analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
            
            return {
                "pigmentation":    AnalyzerRegistry.get("pigmentation_v1", config=analyzer_config.get("pigmentation_v1", {})),
                "redness":         AnalyzerRegistry.get("redness_v1", config=analyzer_config.get("redness_v1", {})),
                "pore":            AnalyzerRegistry.get("pore_v1", config=analyzer_config.get("pore_v1", {})),
                "wrinkle":         AnalyzerRegistry.get("wrinkle_v1", config=analyzer_config.get("wrinkle_v1", {})),
                "tone_elasticity": AnalyzerRegistry.get("tone_elasticity_v1", config=analyzer_config.get("tone_elasticity_v1", {})),
                "acne":            AnalyzerRegistry.get("acne_v1", config=analyzer_config.get("acne_v1", {})),
            }
        except Exception as e:
            log.warning("분석기 레지스트리 로드 실패: %s. 기본 순수 함수 사용.", e)
            return {}

    @staticmethod
    def load_analyzers_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
        from src.skin.analyzers import AnalyzerRegistry, register_analyzers_from_config
        register_analyzers_from_config()
        analyzer_config = config.get("analyzers", {})
        analyzers: Dict[str, Any] = {}
        for key, analyzer_name in analyzer_config.items():
            if key.startswith("_"):
                continue
            try:
                analyzers[key] = AnalyzerRegistry.get(analyzer_name)
                log.info("분석기 로드: %s -> %s", key, analyzer_name)
            except ValueError as e:
                log.warning("분석기 로드 실패: %s -> %s: %s", key, analyzer_name, e)
        return analyzers

    # ── 내부 헬퍼 ──────────────────────────────────────────────────

    @staticmethod
    def _make_pigment_mask(smask: np.ndarray, fh: int, fw: int) -> np.ndarray:
        return make_pigment_mask(smask, fh, fw)

    def _extract_face(
        self, image: np.ndarray, debug: bool = False
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """얼굴 검출 + ROI 분할."""
        if debug:
            log.debug("얼굴 검출 이미지 크기: %s", image.shape[:2])

        bbox = self.face_detector.detect_face(image, debug=debug)
        if bbox is not None:
            x, y, w, h = bbox
            img_h, img_w = image.shape[:2]
            margin = int(min(w, h) * 0.15)
            x = max(0, x - margin); y = max(0, y - margin)
            w = min(img_w - x, w + 2 * margin); h = min(img_h - y, h + 2 * margin)
            face = image[y:y + h, x:x + w]
        else:
            if debug:
                log.debug("얼굴 검출 실패 → 중앙 영역 폴백")
            ih, iw = image.shape[:2]
            if iw > ih:
                mw, mh = int(iw * 0.25), int(ih * 0.15)
            else:
                mw, mh = int(iw * 0.15), int(ih * 0.20)
            face = image[mh:ih - mh, mw:iw - mw]

        fh, fw = face.shape[:2]
        x1, x2 = int(fw * 0.35), int(fw * 0.65)

        regions: Dict[str, np.ndarray] = {
            "forehead":      face[0:int(fh * FaceROI.FOREHEAD_BOTTOM), :],
            "left_eye":      face[int(fh * FaceROI.EYE_TOP - 0.02):int(fh * FaceROI.EYE_BOTTOM - 0.03), 0:int(fw * FaceROI.EYE_LEFT_INNER)],
            "right_eye":     face[int(fh * FaceROI.EYE_TOP - 0.02):int(fh * FaceROI.EYE_BOTTOM - 0.03), int(fw * FaceROI.EYE_RIGHT_INNER):],
            "nose":          face[int(fh * 0.30):int(fh * 0.65), x1:x2],
            "left_cheek":    face[int(fh * FaceROI.CHEEK_TOP):int(fh * FaceROI.CHEEK_BOTTOM), 0:int(fw * FaceROI.CHEEK_LEFT_INNER)],
            "right_cheek":   face[int(fh * FaceROI.CHEEK_TOP):int(fh * FaceROI.CHEEK_BOTTOM), int(fw * FaceROI.CHEEK_RIGHT_INNER):],
            "chin":          face[int(fh * FaceROI.CHIN_TOP):, :],
            "lower_face":    face[int(fh * FaceROI.LOWER_FACE_TOP):, :],
            "t_zone":        _safe_vstack([face[0:int(fh * 0.30), x1:x2], face[int(fh * 0.30):int(fh * 0.65), x1:x2]]),
            "u_zone":        _safe_hstack([face[int(fh * 0.40):, 0:int(fw * 0.35)], face[int(fh * 0.40):, int(fw * 0.65):]]),
            "left_canthus":  face[int(fh * FaceROI.FOREHEAD_BOTTOM - 0.05):int(fh * FaceROI.NOSE_TOP), 0:int(fw * FaceROI.LEFT_CANTHUS_RIGHT)],
            "right_canthus": face[int(fh * FaceROI.FOREHEAD_BOTTOM - 0.05):int(fh * FaceROI.NOSE_TOP), int(fw * FaceROI.RIGHT_CANTHUS_LEFT):],
            "glabella":      face[int(fh * FaceROI.GLABELLA_TOP):int(fh * FaceROI.GLABELLA_BOTTOM), int(fw * FaceROI.GLABELLA_LEFT):int(fw * FaceROI.GLABELLA_RIGHT)],
            "nasolabial_l":  face[int(fh * FaceROI.NOSE_TOP):int(fh * 0.80), 0:int(fw * FaceROI.NASOLABIAL_LEFT)],
            "nasolabial_r":  face[int(fh * FaceROI.NOSE_TOP):int(fh * 0.80), int(fw * FaceROI.NASOLABIAL_RIGHT):],
            "lower_cheek_l": face[int(fh * FaceROI.LOWER_CHEEK_TOP):int(fh * FaceROI.LOWER_CHEEK_BOTTOM), 0:int(fw * FaceROI.LOWER_CHEEK_LEFT)],
            "lower_cheek_r": face[int(fh * FaceROI.LOWER_CHEEK_TOP):int(fh * FaceROI.LOWER_CHEEK_BOTTOM), int(fw * FaceROI.LOWER_CHEEK_RIGHT):],
        }
        return face, regions

    # ── 퍼블릭 진입점 ──────────────────────────────────────────────

    def analyze_all(
        self,
        image_path: str,
        debug: bool = False,
        clahe_preprocessed: bool = False,
        ref_stat: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """전체 측정항목 분석 실행 (오케스트레이터)."""
        image = _imread_bgr(image_path)
        if image is None:
            raise ValueError(f"이미지를 불러올 수 없습니다: {image_path}")

        if debug:
            log.debug("%s\n COTELEAF Skin Analyzer v3  |  %s\n%s", "=" * 60, image_path, "=" * 60)

        face, regions = self._extract_face(image, debug=debug)
        smask = _skin_mask(face)

        if debug:
            log.debug("피부 마스크 커버리지: %.1f%%", np.count_nonzero(smask) / smask.size * 100)

        lab_face = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
        stat     = _skin_stat(lab_face, smask)

        # pig_stat 주입 (눈·코·입 제외)
        fh_s, fw_s = face.shape[:2]
        pig_smask_pre = make_pigment_mask(smask, fh_s, fw_s)
        pig_stat = _skin_stat(lab_face, pig_smask_pre)
        stat["pig_base_L"] = pig_stat["base_L"]; stat["pig_std_L"]  = pig_stat["std_L"]
        stat["pig_base_b"] = pig_stat["base_b"]; stat["pig_std_b"]  = pig_stat["std_b"]
        stat["pig_base_a"] = pig_stat["base_a"]; stat["pig_std_a"]  = pig_stat["std_a"]

        # red_stat 주입 (cheek 기준)
        red_smask_pre = smask.copy()
        red_smask_pre[:int(fh_s * 0.40), :] = 0
        red_smask_pre[int(fh_s * 0.75):, :] = 0
        red_smask_pre[:, int(fw_s * 0.35):int(fw_s * 0.65)] = 0
        if int(np.count_nonzero(red_smask_pre)) >= 200:
            red_stat = _skin_stat(lab_face, red_smask_pre)
            stat["red_base_a"] = red_stat["base_a"]
            stat["red_std_a"]  = max(red_stat["std_a"], 2.0)
        else:
            stat["red_base_a"] = stat["base_a"]
            stat["red_std_a"]  = max(stat["std_a"], 2.0)

        if ref_stat is not None:
            stat = {**stat, **ref_stat}
            if debug:
                log.debug("[ref_stat 주입] base_L=%.1f std_L=%.1f base_b=%.1f",
                          stat.get("base_L", 0), stat.get("std_L", 0), stat.get("base_b", 0))

        # ── 도메인별 분석 호출 ─────────────────────────────────────
        clip_limit, tile_grid_size = _get_clahe_params()
        freckle_params = _get_freckle_detection_params()
        blob_params    = _get_blob_detection_params()

        if debug: log.debug("[분석] Pigmentation ...")
        if "pigmentation" in self.analyzers:
            pigmentation = self.analyzers["pigmentation"].analyze(
                face, smask, regions, stat=stat,
                bp_melasma=_get_metric_bp("melasma_score"),
                bp_freckle_count=_get_metric_bp_count("freckle_score_count"),
                freckle_params=freckle_params,
            )
        else:
            # [REFACTOR 2026-05-23] 측정항목별 분석기 버전 매핑 사용
            from src.skin.analyzers.registry import AnalyzerRegistry
            from src.scoring.config._config import _load_scoring_config
            try:
                # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
                config = _load_scoring_config()
                prescription_config = config.get("prescription", {}) if config else {}
                analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
                
                # melasma_score에 매핑된 분석기 사용 (pigmentation_v1)
                pig_analyzer = AnalyzerRegistry.get_for_measurement("melasma_score", config=analyzer_config.get("pigmentation_v1", {}))
                pigmentation = pig_analyzer.analyze(
                    face, smask, regions, stat=stat,
                    bp_melasma=_get_metric_bp("melasma_score"),
                    bp_freckle_count=_get_metric_bp_count("freckle_score_count"),
                    freckle_params=freckle_params,
                )
            except Exception as e:
                log.warning(f"측정항목 기반 분석기 로드 실패, 기본 함수 사용: {e}")
                pigmentation = analyze_pigmentation(
                    face, smask, stat,
                    bp_melasma=_get_metric_bp("melasma_score"),
                    bp_freckle_count=_get_metric_bp_count("freckle_score_count"),
                    freckle_params=freckle_params,
                )

        if debug: log.debug("[분석] Redness ...")
        if "redness" in self.analyzers:
            redness = self.analyzers["redness"].analyze(
                face, smask, regions, stat=stat,
                clahe_clip=clip_limit, clahe_tile=tile_grid_size,
                bp_redness=_get_metric_bp("redness_score"),
                bp_pie=_get_metric_bp("post_inflammatory_erythema_score"),
            )
        else:
            # [REFACTOR 2026-05-23] 측정항목별 분석기 버전 매핑 사용
            from src.skin.analyzers.registry import AnalyzerRegistry
            from src.scoring.config._config import _load_scoring_config
            try:
                # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
                config = _load_scoring_config()
                prescription_config = config.get("prescription", {}) if config else {}
                analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
                
                # redness_score에 매핑된 분석기 사용 (redness_v1)
                red_analyzer = AnalyzerRegistry.get_for_measurement("redness_score", config=analyzer_config.get("redness_v1", {}))
                redness = red_analyzer.analyze(
                    face, smask, regions, stat=stat,
                    clahe_clip=clip_limit, clahe_tile=tile_grid_size,
                    bp_redness=_get_metric_bp("redness_score"),
                    bp_pie=_get_metric_bp("post_inflammatory_erythema_score"),
                )
            except Exception as e:
                log.warning(f"측정항목 기반 분석기 로드 실패, 기본 함수 사용: {e}")
                redness = analyze_redness(
                    face, smask, regions, stat,
                    clahe_clip=clip_limit, clahe_tile=tile_grid_size,
                    bp_redness=_get_metric_bp("redness_score"),
                    bp_pie=_get_metric_bp("post_inflammatory_erythema_score"),
                )

        if debug: log.debug("[분석] Pore ...")
        if "pore" in self.analyzers:
            pores = self.analyzers["pore"].analyze(
                face, smask, regions,
                blob_params=blob_params,
                clahe_clip=_get_clahe_params(use_pore=True)[0],
                clahe_tile=_get_clahe_params(use_pore=True)[1],
                bp_pore_density=_get_metric_bp("pore_size_score"),
                bp_sagging_lap=_get_metric_bp("pore_sagging_score"),
            )
        else:
            # [REFACTOR 2026-05-23] 측정항목별 분석기 버전 매핑 사용
            from src.skin.analyzers.registry import AnalyzerRegistry
            from src.scoring.config._config import _load_scoring_config
            try:
                # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
                config = _load_scoring_config()
                prescription_config = config.get("prescription", {}) if config else {}
                analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
                
                # pore_size_score에 매핑된 분석기 사용 (pore_v1)
                pore_analyzer = AnalyzerRegistry.get_for_measurement("pore_size_score", config=analyzer_config.get("pore_v1", {}))
                pores = pore_analyzer.analyze(
                    face, smask, regions,
                    blob_params=blob_params,
                    clahe_clip=_get_clahe_params(use_pore=True)[0],
                    clahe_tile=_get_clahe_params(use_pore=True)[1],
                    bp_pore_density=_get_metric_bp("pore_size_score"),
                    bp_sagging_lap=_get_metric_bp("pore_sagging_score"),
                )
            except Exception as e:
                log.warning(f"측정항목 기반 분석기 로드 실패, 기본 함수 사용: {e}")
                pores = analyze_pores(
                    face, regions,
                    blob_params=blob_params,
                    clahe_clip=_get_clahe_params(use_pore=True)[0],
                    clahe_tile=_get_clahe_params(use_pore=True)[1],
                    bp_pore_density=_get_metric_bp("pore_size_score"),
                    bp_sagging_lap=_get_metric_bp("pore_sagging_score"),
                )

        if debug: log.debug("[분석] Wrinkle ...")
        if "wrinkle" in self.analyzers:
            wrinkles = self.analyzers["wrinkle"].analyze(
                face, smask, regions,
                clahe_preprocessed=clahe_preprocessed,
                bp_eye=_get_metric_bp("eye_wrinkle_score"),
                bp_nasolabial=_get_metric_bp("nasolabial_wrinkle_score"),
            )
        else:
            # [REFACTOR 2026-05-23] 측정항목별 분석기 버전 매핑 사용
            from src.skin.analyzers.registry import AnalyzerRegistry
            from src.scoring.config._config import _load_scoring_config
            try:
                # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
                config = _load_scoring_config()
                prescription_config = config.get("prescription", {}) if config else {}
                analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
                
                # eye_wrinkle_score에 매핑된 분석기 사용 (wrinkle_v1)
                wrinkle_analyzer = AnalyzerRegistry.get_for_measurement("eye_wrinkle_score", config=analyzer_config.get("wrinkle_v1", {}))
                wrinkles = wrinkle_analyzer.analyze(
                    face, smask, regions,
                    clahe_preprocessed=clahe_preprocessed,
                    bp_eye=_get_metric_bp("eye_wrinkle_score"),
                    bp_nasolabial=_get_metric_bp("nasolabial_wrinkle_score"),
                )
            except Exception as e:
                log.warning(f"측정항목 기반 분석기 로드 실패, 기본 함수 사용: {e}")
                wrinkles = analyze_wrinkles(
                    face, regions,
                    clahe_preprocessed=clahe_preprocessed,
                    skin_mask=smask,
                    bp_eye=_get_metric_bp("eye_wrinkle_score"),
                    bp_nasolabial=_get_metric_bp("nasolabial_wrinkle_score"),
                )

        if debug: log.debug("[분석] Texture ...")
        texture = analyze_texture(
            face, regions, smask,
            clahe_clip=clip_limit, clahe_tile=tile_grid_size,
            bp_roughness=_get_metric_bp("roughness_score"),
        )

        if debug: log.debug("[분석] Tone, Elasticity, Sebum ...")
        if "tone_elasticity" in self.analyzers:
            # [REFACTOR 2026-05-23] 완전 독립성 - 외부 wrinkle 의존성 제거
            te = self.analyzers["tone_elasticity"].analyze(
                face, smask, regions, stat=stat,
                clahe_preprocessed=clahe_preprocessed,
            )
            tone      = {k: te.get(k) for k in ("skin_tone_score", "dullness_score", "uneven_tone_score")}
            elasticity = {k: te.get(k) for k in ("jawline_blur_score", "cheek_sagging_score", "elasticity_score")}
            sebum      = {
                "skin_type_score": te.get("skin_type_score"),
                "skin_type_label": te.get("skin_type_label", "중성"),
            }
        else:
            # [REFACTOR 2026-05-23] 측정항목별 분석기 버전 매핑 사용
            from src.skin.analyzers.registry import AnalyzerRegistry
            from src.scoring.config._config import _load_scoring_config
            try:
                # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
                config = _load_scoring_config()
                prescription_config = config.get("prescription", {}) if config else {}
                analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
                
                # skin_tone_score에 매핑된 분석기 사용 (tone_elasticity_v1)
                # [REFACTOR 2026-05-23] 완전 독립성 - 외부 wrinkle 의존성 제거
                te_analyzer = AnalyzerRegistry.get_for_measurement("skin_tone_score", config=analyzer_config.get("tone_elasticity_v1", {}))
                te = te_analyzer.analyze(
                    face, smask, regions, stat=stat,
                    clahe_preprocessed=clahe_preprocessed,
                )
                tone      = {k: te.get(k) for k in ("skin_tone_score", "dullness_score", "uneven_tone_score")}
                elasticity = {k: te.get(k) for k in ("jawline_blur_score", "cheek_sagging_score", "elasticity_score")}
                sebum      = {
                    "skin_type_score": te.get("skin_type_score"),
                    "skin_type_label": te.get("skin_type_label", "중성"),
                }
            except Exception as e:
                log.warning(f"측정항목 기반 분석기 로드 실패, 기본 함수 사용: {e}")
                tone       = analyze_tone(face, regions, smask)
                elasticity = analyze_elasticity(
                    face, regions,
                    eye_wrinkle_score=wrinkles["eye_wrinkle_score"],
                    bp_jawline=_get_metric_bp("jawline_blur_score"),
                )
                sebum = analyze_sebum(face, regions, smask)

        if debug: log.debug("[분석] Acne & Marks ...")
        if "acne" in self.analyzers:
            acne_marks = self.analyzers["acne"].analyze(
                face, smask, regions, stat=stat,
                bp_acne=_get_metric_bp("acne_score"),
                bp_pap=_get_metric_bp("post_acne_pigment_score"),
            )
        else:
            # [REFACTOR 2026-05-23] 측정항목별 분석기 버전 매핑 사용
            from src.skin.analyzers.registry import AnalyzerRegistry
            from src.scoring.config._config import _load_scoring_config
            try:
                # config.json에서 분석기 설정 로드 (prescription.analyzers 섹션)
                config = _load_scoring_config()
                prescription_config = config.get("prescription", {}) if config else {}
                analyzer_config = prescription_config.get("analyzers", {}) if prescription_config else {}
                
                # acne_score에 매핑된 분석기 사용 (acne_v1)
                acne_analyzer = AnalyzerRegistry.get_for_measurement("acne_score", config=analyzer_config.get("acne_v1", {}))
                acne_marks = acne_analyzer.analyze(
                    face, smask, regions, stat=stat,
                    bp_acne=_get_metric_bp("acne_score"),
                    bp_pap=_get_metric_bp("post_acne_pigment_score"),
                )
            except Exception as e:
                log.warning(f"측정항목 기반 분석기 로드 실패, 기본 함수 사용: {e}")
                acne_marks = analyze_acne_marks(
                    face, smask, stat,
                    bp_acne=_get_metric_bp("acne_score"),
                    bp_pap=_get_metric_bp("post_acne_pigment_score"),
                )

        if debug: log.debug("[분석] Restoration Quality ...")
        restoration_quality = analyze_restoration_quality(face, regions, smask)

        # ── 결과 취합 ──────────────────────────────────────────────
        measurements: Dict[str, object] = {
            **pigmentation, **redness, **pores, **wrinkles,
            **texture, **tone, **restoration_quality,
            **elasticity, **sebum, **acne_marks,
        }

        missing = [k for k in self.OUTPUT_KEYS if k not in measurements]
        if missing:
            for k in missing:
                measurements[k] = None
            if debug:
                log.debug("누락 키 보완: %s", missing)

        for k, v in list(measurements.items()):
            if not k.endswith("_score") and k != "focal_lesion":
                continue
            if isinstance(v, (int, float)):
                measurements[k] = round(float(v), 1)

        lines_score = float(np.mean([
            wrinkles["eye_wrinkle_score"],
            wrinkles["glabella_wrinkle_score"],
            wrinkles["nasolabial_wrinkle_score"],
        ]))
        perceived_age_val = analyze_perceived_age(
            face,
            eye_wrinkle_score=wrinkles["eye_wrinkle_score"],
            lines_score=lines_score,
        )
        overall = _compute_overall_score_legacy(measurements, debug=debug)
        measurements["overall_score_raw"] = overall
        _apply_measurements_display_10_90(measurements)
        overall = _map_score_display_10_90(overall)

        if debug:
            log.debug("%s\n 종합: %s  인지나이: %s\n%s",
                      "─" * 60, overall, perceived_age_val, "─" * 60)

        filtered = {k: measurements[k] for k in self.OUTPUT_KEYS if k in measurements}

        # skin_type_label은 _score suffix가 아니므로 OUTPUT_KEYS에 없음 — 별도 보존
        _stl = measurements.get("skin_type_label")
        if _stl is not None:
            filtered["skin_type_label"] = _stl

        # raw 보존 (레이어 B 직접 복원용) - 설정 기반 관리
        raw_measurements: Dict[str, float] = {}
        try:
            from src.scoring.config._config import _load_scoring_config
            config = _load_scoring_config()
            raw_preserve_keys = config.get("raw_preserve_keys", ["dullness_score"])
        except Exception:
            raw_preserve_keys = ["dullness_score"]  # 폴백
        
        for k in raw_preserve_keys:
            v = measurements.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                raw_measurements[k] = _score_from_display_10_90_adjusted(k, float(v))

        return {
            "overall_score":     overall,
            "overall_score_raw": measurements.get("overall_score_raw", 0.0),
            "perceived_age":     perceived_age_val,
            "measurements":      filtered,
            "skin_stat":         stat,
            "raw_measurements":  raw_measurements,
        }

    def print_results(self, results: Dict[str, Any]) -> None:
        print(_measurement_report_string_legacy(results), end="")


# ── 하위 호환 alias ───────────────────────────────────────────────
# [DEPRECATION POLICY 2026-05-24]
# 이 alias들은 v2.0 릴리스 시 제거될 예정입니다.
# 새로운 코드에서는 _legacy_ 접두사 함수를 사용하세요.
# 사용 시 DeprecationWarning이 발생합니다.

def _deprecated_v2_wrapper(func, name):
    """v2 alias에 대한 deprecation warning wrapper."""
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{name}는 v2.0에서 제거될 예정입니다. "
            f"대신 {func.__name__}를 사용하세요.",
            DeprecationWarning,
            stacklevel=2
        )
        return func(*args, **kwargs)
    return wrapper

_compute_overall_score_v2 = _deprecated_v2_wrapper(
    _compute_overall_score_legacy, "_compute_overall_score_v2"
)
_V2_MEASUREMENT_CATEGORIES = _LEGACY_MEASUREMENT_CATEGORIES  # 상수는 warning 불가
_measurement_report_string_v2 = _deprecated_v2_wrapper(
    _measurement_report_string_legacy, "_measurement_report_string_v2"
)
