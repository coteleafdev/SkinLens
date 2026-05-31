"""src.scoring._multi_view — 멀티뷰(측면) 분석 및 병합.

[REFACTOR] skin_scoring.py에서 분리.
  - LateralFaceAnalyzer (45도 측면 분석)
  - MultiViewMerger (정면 + 좌/우 45° 병합)
  - analyze_all_multi (공개 진입점)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

from src.skin.core.face_detector import FaceDetector
from src.skin.core.face_roi import FaceROI
from src.skin.core.scoring_utils import clamp as _clamp, area_to_score as _area_to_score, safe_region as _safe_region
from src.skin.core.image_utils import imread_bgr as _imread_bgr, skin_mask as _skin_mask
from src.scoring._breakpoints import _get_clahe_params
from src.scoring._score_utils import (
    _map_score_display_10_90,
    _score_from_display_10_90,
    _score_from_display_10_90_adjusted,
    _apply_measurements_display_10_90,
)
from src.scoring._core import _SkinAnalyzerCore, _compute_overall_score_legacy

log = logging.getLogger(__name__)


class LateralFaceAnalyzer:
    """45도 측면 이미지 전용 형태 분석기 (v2.5)."""

    _LATERAL_REGIONS = {
        "eye_outer_v":   (0.20, 0.45), "eye_outer_h":   (0.30, 0.70),
        "nasolabial_v":  (0.45, 0.75), "nasolabial_h":  (0.05, 0.50),
        "cheek_v":       (0.35, 0.75), "cheek_h":       (0.40, 0.80),
        "chin_v":        (0.72, 1.00), "chin_h":        (0.00, 0.70),
    }

    def __init__(self, face_detector: Optional[FaceDetector] = None) -> None:
        self.face_detector = face_detector if face_detector is not None else FaceDetector()

    def _extract_lateral_face(
        self, image: np.ndarray, debug: bool = False
    ) -> Optional[np.ndarray]:
        bbox = self.face_detector.detect_face(image, debug=debug)
        if bbox is None:
            return None
        x, y, w, h = bbox
        ih, iw = image.shape[:2]
        mx, my = int(w * 0.20), int(h * 0.15)
        face = image[max(0, y - my):min(ih, y + h + my), max(0, x - mx):min(iw, x + w + mx)]
        return face if face.size > 0 and min(face.shape[:2]) >= 30 else None

    def _sobel_components(self, gray: np.ndarray) -> Tuple[float, float, float]:
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        sx = cv2.Sobel(blurred.astype(float), cv2.CV_64F, 1, 0, ksize=3)
        sy = cv2.Sobel(blurred.astype(float), cv2.CV_64F, 0, 1, ksize=3)
        return (float(np.mean(np.sqrt(sx ** 2 + sy ** 2))),
                float(np.mean(np.abs(sx))),
                float(np.mean(np.abs(sy))))

    def _get_roi(
        self, face: np.ndarray, v_range: tuple, h_range: tuple
    ) -> np.ndarray:
        fh, fw = face.shape[:2]
        r = face[int(fh * v_range[0]):int(fh * v_range[1]),
                 int(fw * h_range[0]):int(fw * h_range[1])]
        return _safe_region(r)

    def _measure_eye_wrinkle(
        self, face: np.ndarray, clahe_preprocessed: bool = False
    ) -> Optional[float]:
        roi = self._get_roi(face, self._LATERAL_REGIONS["eye_outer_v"],
                            self._LATERAL_REGIONS["eye_outer_h"])
        if min(roi.shape[:2]) < 8:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        cl, tg = _get_clahe_params()
        gray = cv2.createCLAHE(clipLimit=cl, tileGridSize=tg).apply(gray)
        mag, _, sy_m = self._sobel_components(gray)
        _BP = ([(0, 100), (32, 90), (80, 75), (160, 55), (280, 30), (480, 0)]
               if clahe_preprocessed
               else [(0, 100), (8, 90), (20, 75), (40, 55), (70, 30), (120, 0)])
        return _area_to_score(sy_m * 0.65 + mag * 0.35, _BP)

    def _measure_nasolabial(
        self, face: np.ndarray, clahe_preprocessed: bool = False
    ) -> Optional[float]:
        roi = self._get_roi(face, self._LATERAL_REGIONS["nasolabial_v"],
                            self._LATERAL_REGIONS["nasolabial_h"])
        if min(roi.shape[:2]) < 8:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        cl, tg = _get_clahe_params()
        gray = cv2.createCLAHE(clipLimit=cl, tileGridSize=tg).apply(gray)
        mag, _, _ = self._sobel_components(gray)
        _BP = ([(0, 100), (32, 90), (80, 75), (160, 55), (280, 30), (480, 0)]
               if clahe_preprocessed
               else [(0, 100), (8, 90), (20, 75), (40, 55), (70, 30), (120, 0)])
        return _area_to_score(mag, _BP)

    def _measure_cheek_sagging(self, face: np.ndarray) -> Optional[float]:
        fh, fw = face.shape[:2]
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        v0, v1 = int(fh * 0.35), int(fh * 0.75)
        skin_mask_roi = _skin_mask(face[v0:v1, :])
        profile: List[int] = []
        for row_i in range(v1 - v0):
            sk_row = skin_mask_roi[row_i]
            nonzero = np.where(sk_row > 0)[0]
            profile.append(int(nonzero.max()) if len(nonzero) > 0 else 0)
        profile_arr = np.array(profile, dtype=float)
        if profile_arr.max() == 0:
            return None
        peak_row = int(np.argmax(profile_arr))
        peak_ratio = peak_row / max(len(profile_arr) - 1, 1)
        return _area_to_score(peak_ratio,
                              [(0.00, 100), (0.20, 90), (0.35, 80), (0.50, 60),
                               (0.65, 35), (0.80, 15), (1.00, 0)])

    def _measure_jawline(self, face: np.ndarray) -> Optional[float]:
        roi = self._get_roi(face, self._LATERAL_REGIONS["chin_v"],
                            self._LATERAL_REGIONS["chin_h"])
        if min(roi.shape[:2]) < 8:
            return None
        gray   = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        sobelY = cv2.Sobel(cv2.GaussianBlur(gray, (3, 3), 0).astype(float),
                           cv2.CV_64F, 0, 1, ksize=5)
        return _area_to_score(float(np.mean(np.abs(sobelY))),
                              [(0.0, 0), (5.0, 20), (12.0, 40), (20.0, 60),
                               (30.0, 80), (40.0, 90), (55.0, 100)])

    def analyze_lateral(
        self,
        image_path: str,
        side: str,
        debug: bool = False,
        clahe_preprocessed: bool = False,
    ) -> Dict[str, Optional[float]]:
        image = _imread_bgr(image_path)
        if image is None:
            raise ValueError(f"이미지를 불러올 수 없습니다: {image_path}")
        if debug:
            log.debug("측면 분석 side=%s  %s", side, image_path)
        face = self._extract_lateral_face(image, debug=debug)
        if face is None:
            return {k: None for k in ("eye_wrinkle_lateral", "nasolabial_lateral",
                                      "cheek_sagging_lateral", "jawline_lateral")}
        eye_lat   = self._measure_eye_wrinkle(face, clahe_preprocessed)
        nl_lat    = self._measure_nasolabial(face, clahe_preprocessed)
        cheek_lat = self._measure_cheek_sagging(face)
        jaw_lat   = self._measure_jawline(face)
        result = {
            "eye_wrinkle_lateral":   round(_map_score_display_10_90(_clamp(eye_lat)),   1) if eye_lat   is not None else None,
            "nasolabial_lateral":    round(_map_score_display_10_90(_clamp(nl_lat)),    1) if nl_lat    is not None else None,
            "cheek_sagging_lateral": round(_map_score_display_10_90(_clamp(cheek_lat)), 1) if cheek_lat is not None else None,
            "jawline_lateral":       round(_map_score_display_10_90(_clamp(jaw_lat)),   1) if jaw_lat   is not None else None,
        }
        if debug:
            for k, v in result.items():
                log.debug("   %-30s %s", k, v)
        return result


class MultiViewMerger:
    """정면 + 좌45° + 우45° 결과 병합기 (v1.0)."""

    # 각도별 특화 항목 가중치 (front, left, right)
    ANGLE_WEIGHTS: Dict[str, Dict[str, float]] = {
        # 측면 특화 항목 (측면 80%, 정면 20%)
        "pore_sagging_score": {"front": 0.2, "left": 0.4, "right": 0.4},
        "eye_wrinkle_score": {"front": 0.2, "left": 0.4, "right": 0.4},
        "jawline_blur_score": {"front": 0.2, "left": 0.4, "right": 0.4},
        "cheek_sagging_score": {"front": 0.2, "left": 0.4, "right": 0.4},
        
        # 정면 특화 항목 (정면 70%, 측면 30%)
        "melasma_score": {"front": 0.7, "left": 0.15, "right": 0.15},
        "redness_score": {"front": 0.7, "left": 0.15, "right": 0.15},
        "skin_tone_score": {"front": 0.7, "left": 0.15, "right": 0.15},
        "dullness_score": {"front": 0.7, "left": 0.15, "right": 0.15},
        "uneven_tone_score": {"front": 0.7, "left": 0.15, "right": 0.15},
        "nasolabial_wrinkle_score": {"front": 0.7, "left": 0.15, "right": 0.15},
        
        # 최대값 기반 통합 (여드름 등)
        "acne_score": {"method": "max"},
        "post_acne_pigment_score": {"method": "max"},
        
        # 기본값: 평균 (균등 가중치)
    }
    
    # 기본 가중치 (균등)
    DEFAULT_WEIGHTS = {"front": 0.33, "left": 0.33, "right": 0.33}
    
    # 레거시 호환용 (이전 버전과 호환)
    LATERAL_WEIGHTS: Dict[str, Tuple[float, float]] = {
        "eye_wrinkle_score": (0.4, 0.6),
        "nasolabial_wrinkle_score": (0.4, 0.6),
        "cheek_sagging_score": (0.3, 0.7),
        "jawline_blur_score": (0.3, 0.7),
    }
    LATERAL_KEY_MAP: Dict[str, str] = {
        "eye_wrinkle_score": "eye_wrinkle_lateral",
        "nasolabial_wrinkle_score": "nasolabial_lateral",
        "cheek_sagging_score": "cheek_sagging_lateral",
        "jawline_blur_score": "jawline_lateral",
    }

    def merge(
        self,
        front_result: Dict[str, Any],
        left_result: Optional[Dict[str, Any]] = None,
        right_result: Optional[Dict[str, Any]] = None,
        left_lateral: Optional[Dict[str, Optional[float]]] = None,
        right_lateral: Optional[Dict[str, Optional[float]]] = None,
        debug: bool = False,
    ) -> Dict[str, Any]:
        """
        정면 + 좌45° + 우45° 결과 병합 (v1.0).
        
        Args:
            front_result: 정면 이미지 분석 결과
            left_result: 좌측 45° 이미지 전체 분석 결과 (v1.0)
            right_result: 우측 45° 이미지 전체 분석 결과 (v1.0)
            left_lateral: 좌측 45° 측면 분석 결과 (레거시 호환용)
            right_lateral: 우측 45° 측면 분석 결과 (레거시 호환용)
            debug: 디버그 모드
        
        Returns:
            병합된 분석 결과
        """
        import copy
        merged = copy.deepcopy(front_result)
        meas = merged["measurements"]

        # 디스플레이 점수 → 내부 점수 변환
        for k, v in list(meas.items()):
            if not k.endswith("_score") or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                meas[k] = _score_from_display_10_90_adjusted(k, float(v))

        ov0 = merged.get("overall_score")
        if isinstance(ov0, (int, float)) and not isinstance(ov0, bool):
            merged["overall_score"] = _score_from_display_10_90(float(ov0))

        detail: Dict[str, Dict] = {}
        
        # v1.0: 전체 분석 결과가 있는 경우 모든 항목 통합
        if left_result is not None and right_result is not None:
            left_meas = left_result.get("measurements", {})
            right_meas = right_result.get("measurements", {})
            
            for metric in meas.keys():
                if not metric.endswith("_score") or isinstance(meas[metric], bool):
                    continue
                
                front_val = meas.get(metric)
                left_val = left_meas.get(metric)
                right_val = right_meas.get(metric)
                
                if front_val is None:
                    continue
                
                # 최대값 기반 통합 (여드름 등)
                if metric in self.ANGLE_WEIGHTS and self.ANGLE_WEIGHTS[metric].get("method") == "max":
                    vals = [v for v in [front_val, left_val, right_val] if v is not None]
                    if vals:
                        merged_val = max(vals)
                        meas[metric] = merged_val
                        detail[metric] = {
                            "method": "max",
                            "front": front_val,
                            "left": left_val,
                            "right": right_val,
                            "merged": merged_val,
                        }
                        if debug:
                            log.debug("  [Merge] %-35s  max(%s) → %.1f", metric, vals, merged_val)
                    continue
                
                # 가중치 기반 통합
                weights = self.ANGLE_WEIGHTS.get(metric, self.DEFAULT_WEIGHTS)
                if isinstance(weights, dict) and "method" in weights:
                    weights = self.DEFAULT_WEIGHTS
                
                vals = []
                w_sum = 0.0
                for val, weight in [(front_val, weights["front"]), 
                                    (left_val, weights["left"]), 
                                    (right_val, weights["right"])]:
                    if val is not None:
                        vals.append(val * weight)
                        w_sum += weight
                
                if vals:
                    merged_val = round(_clamp(sum(vals) / w_sum), 1)
                    meas[metric] = merged_val
                    detail[metric] = {
                        "method": "weighted_average",
                        "front": front_val,
                        "left": left_val,
                        "right": right_val,
                        "weights": weights,
                        "merged": merged_val,
                    }
                    if debug:
                        log.debug("  [Merge] %-35s  정면=%.1f  좌=%.1f  우=%.1f  → %.1f",
                                  metric, front_val, left_val, right_val, merged_val)
                else:
                    detail[metric] = {"method": "front_only", "front": front_val}
        
        # 레거시: 측면 분석 결과만 있는 경우 (하위 호환)
        else:
            # lat_dict가 None인 경우 빈 딕셔너리로 초기화
            left_lateral = left_lateral or {}
            right_lateral = right_lateral or {}
            
            for front_key, lat_key in self.LATERAL_KEY_MAP.items():
                front_val = meas.get(front_key)
                if front_val is None:
                    continue
                lat_vals: List[float] = []
                for lat_dict in (left_lateral, right_lateral):
                    if lat_dict is None:
                        continue
                    v = lat_dict.get(lat_key)
                    if v is not None:
                        lat_vals.append(_score_from_display_10_90_adjusted(front_key, float(v)))

                if front_key == "cheek_sagging_score":
                    if not lat_vals:
                        meas[front_key] = None
                        detail[front_key] = {"method": "lateral_only_required",
                                             "front": front_val, "status": "no_lateral_images"}
                        if debug:
                            log.debug("  [Merge] %-35s  측면 이미지 없음 → None", front_key)
                    else:
                        lat_mean = float(np.mean(lat_vals))
                        merged_val = round(_clamp(lat_mean), 1)
                        meas[front_key] = merged_val
                        detail[front_key] = {"method": "lateral_only", "lateral_avg": round(lat_mean, 1),
                                             "merged": merged_val, "n_lateral": len(lat_vals)}
                        if debug:
                            log.debug("  [Merge] %-35s  측면=%.1f → %.1f", front_key, lat_mean, merged_val)
                    continue

                if not lat_vals:
                    detail[front_key] = {"method": "front_only", "front": front_val}
                    continue

                lat_mean = float(np.mean(lat_vals))
                w_front, w_lat = self.LATERAL_WEIGHTS[front_key]
                merged_val = round(_clamp(w_front * float(front_val) + w_lat * lat_mean), 1)
                meas[front_key] = merged_val
                detail[front_key] = {
                    "method": "multi_view", "front": front_val,
                    "lateral_avg": round(lat_mean, 1), "merged": merged_val,
                    "w_front": w_front, "w_lateral": w_lat, "n_lateral": len(lat_vals),
                }
                if debug:
                    log.debug("  [Merge] %-35s  정면=%.1f  측면=%.1f  → %.1f",
                              front_key, front_val, lat_mean, merged_val)

        merged["overall_score"] = _compute_overall_score_legacy(meas, debug=debug)
        merged["overall_score_raw"] = merged["overall_score"]
        _apply_measurements_display_10_90(meas)
        merged["overall_score"] = _map_score_display_10_90(merged["overall_score"])
        
        # skin_type_label 보존
        _front_meas = front_result.get("measurements", {})
        _stl = _front_meas.get("skin_type_label")
        if _stl is not None:
            merged["measurements"]["skin_type_label"] = _stl
        
        # 각도별 개별 결과 포함 (v1.0)
        angle_results = {}
        if left_result is not None:
            angle_results["left"] = left_result.get("measurements", {})
        if right_result is not None:
            angle_results["right"] = right_result.get("measurements", {})
        if angle_results:
            merged["angle_results"] = angle_results
        
        for fk, d in detail.items():
            if fk in meas and "merged" in d:
                d["merged"] = meas[fk]
        merged["multi_view_detail"] = detail
        return merged


def analyze_all_multi(
    front_path: str,
    left45_path: Optional[str] = None,
    right45_path: Optional[str] = None,
    debug: bool = False,
    clahe_preprocessed: bool = False,
    use_full_analysis: bool = True,
) -> Dict[str, Any]:
    """
    정면 + 좌45° + 우45° 3장 통합 분석 진입점 (v1.0).
    
    Args:
        front_path: 정면 이미지 경로
        left45_path: 좌측 45° 이미지 경로 (선택)
        right45_path: 우측 45° 이미지 경로 (선택)
        debug: 디버그 모드
        clahe_preprocessed: CLAHE 전처리 여부
        use_full_analysis: 측면 이미지 전체 분석 여부 (v1.0)
    
    Returns:
        통합된 분석 결과
    """
    def _vop(p, name):
        if p is None:
            return None
        pp = Path(p)
        if not pp.exists():
            log.warning("측면 이미지 없음 (%s): %s", name, p)
            return None
        return str(pp)

    left45_path  = _vop(left45_path,  "left45")
    right45_path = _vop(right45_path, "right45")

    shared_detector = FaceDetector()
    analyzer        = _SkinAnalyzerCore(face_detector=shared_detector)
    front_result    = analyzer.analyze_all(front_path, debug=debug,
                                           clahe_preprocessed=clahe_preprocessed)

    if left45_path is None and right45_path is None:
        return {**front_result, "multi_view_detail": {}}

    # v1.0: 측면 이미지 전체 분석
    if use_full_analysis:
        left_result = None
        right_result = None
        
        if left45_path is not None:
            try:
                left_result = analyzer.analyze_all(left45_path, debug=debug,
                                                   clahe_preprocessed=clahe_preprocessed)
            except Exception as e:
                log.warning("좌45° 전체 분석 실패: %s", e)
        
        if right45_path is not None:
            try:
                right_result = analyzer.analyze_all(right45_path, debug=debug,
                                                    clahe_preprocessed=clahe_preprocessed)
            except Exception as e:
                log.warning("우45° 전체 분석 실패: %s", e)
        
        if debug:
            log.debug("[다중 시점 병합 v1.0]")
        
        return MultiViewMerger().merge(
            front_result,
            left_result=left_result,
            right_result=right_result,
            debug=debug
        )
    
    # 레거시: 측면 분석만 수행
    lat_analyzer = LateralFaceAnalyzer(face_detector=shared_detector)
    empty_lat: Dict[str, Optional[float]] = {
        "eye_wrinkle_lateral": None, "nasolabial_lateral": None,
        "cheek_sagging_lateral": None, "jawline_lateral": None,
    }

    def _analyze_side(path, side, name):
        if path is None:
            return empty_lat.copy()
        try:
            return lat_analyzer.analyze_lateral(path, side=side, debug=debug,
                                                clahe_preprocessed=clahe_preprocessed)
        except Exception as e:
            log.warning("%s 분석 실패: %s", name, e)
            return empty_lat.copy()

    left_lat  = _analyze_side(left45_path,  "left",  "좌45°")
    right_lat = _analyze_side(right45_path, "right", "우45°")

    if debug:
        log.debug("[다중 시점 병합 레거시]")

    return MultiViewMerger().merge(front_result, left_lateral=left_lat, right_lateral=right_lat, debug=debug)
