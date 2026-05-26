"""
skin.compose.score_composition
=================================
직교 신호 분해 함수 및 관련 상수.

[REFACTOR P3] skin_scoring.py 에서 분리.
  WEIGHTS, OUTPUT_KEYS, get_measurement_categories()
  _compose_pigmentation_scores, _compose_redness_lesion_scores
  _compose_pore_score, _compose_wrinkle_score, _compose_tone_score
  _compose_elasticity_score, _compose_hydration_score, _compose_skin_type_score
  _compute_overall_score, measurement_report_string

하위 호환: skin_scoring 가 from skin.compose.score_composition import * 로 재노출.

[REFACTOR MAGIC] WEIGHTS 하드코딩 제거 — config.json에서 로드
[REFACTOR P1-11] 순환 import 제거 — _load_scoring_config lazy import
[REFACTOR P2] _clamp() 중복 정의 제거 — scoring_utils에서 import
[REFACTOR 2026-05-22] _MEASUREMENT_CATEGORIES 하드코딩 제거 — llm_prompt_template.md에서 로드
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── 공통 유틸리티 ──────────────────────────────────────────────
from src.skin.core.scoring_utils import clamp as _clamp
from src.skin.core.config_parser import get_v3_categories

def _get_weights() -> Dict[str, float]:
    """config.json에서 weights를 로드합니다.

    [REFACTOR 2026-05-24] prescription.orthogonal_categories에서 가중치 로드.

    Returns:
        weights 딕셔너리. 로드 실패 시 빈 딕셔너리 반환.
    """
    from src.prescription.prescription_calculator import _load_prescription_config
    try:
        config = _load_prescription_config()
        orthogonal_categories = config.get("orthogonal_categories", {})

        # 직교 항목에서 가중치 추출
        weights = {}
        for category_key, metadata in orthogonal_categories.items():
            if category_key.startswith("_"):
                continue  # _note 등 주석 필드 건너뜀
            weights[category_key] = metadata.get("weight", 0.0)
    except Exception:
        log.warning("config.json에서 orthogonal_categories를 로드하지 못했습니다. 기본값 사용.")
        weights = {}

    if not weights:
        # 폴백 기본값
        return {
            "pigmentation_cov": 0.120,
            "spot_density": 0.100,
            "diffuse_redness": 0.120,
            "focal_lesion": 0.140,
            "pore_score": 0.120,
            "wrinkle_score": 0.130,
            "roughness_score": 0.080,
            "tone_score": 0.100,
            "elasticity_score": 0.050,
            "skin_type_score": 0.040,
        }

    return weights


def get_orthogonal_category_metadata(category_key: str) -> Optional[Dict[str, Any]]:
    """config.json에서 직교 항목 메타데이터를 로드합니다.

    [REFACTOR 2026-05-24] 직교 항목 메타데이터를 동적으로 로드.
    향후 직교 항목 추가/변경/삭제 시 config.json의 orthogonal_categories 섹션만 수정.

    Args:
        category_key: 직교 항목 키 (예: pigmentation_cov, wrinkle_score)

    Returns:
        {name_ko, name_en, weight, source_measurements, composition_function} 또는 None
    """
    from src.prescription.prescription_calculator import _load_prescription_config
    try:
        config = _load_prescription_config()
        orthogonal_categories = config.get("orthogonal_categories", {})
        return orthogonal_categories.get(category_key)
    except Exception:
        log.warning(f"직교 항목 '{category_key}' 메타데이터 로드 실패.")
        return None


def get_all_orthogonal_categories() -> Dict[str, Dict[str, Any]]:
    """config.json에서 모든 직교 항목 메타데이터를 로드합니다.

    [REFACTOR 2026-05-24] 직교 항목 메타데이터를 동적으로 로드.
    향후 직교 항목 추가/변경/삭제 시 config.json의 orthogonal_categories 섹션만 수정.

    Returns:
        {category_key: {name_ko, name_en, weight, source_measurements, composition_function}}
    """
    from src.prescription.prescription_calculator import _load_prescription_config
    try:
        config = _load_prescription_config()
        return config.get("orthogonal_categories", {})
    except Exception:
        log.warning("직교 항목 메타데이터 로드 실패.")
        return {}

# ── 가중치 / 카테고리 ──────────────────────────────────────

# [REFACTOR P1-13] 모듈 수준 I/O 제거 - lazy 초기화로 변경
_WEIGHTS_CACHE: Optional[Dict[str, float]] = None

def _get_weights_cached() -> Dict[str, float]:
    """캐싱된 weights를 반환합니다."""
    global _WEIGHTS_CACHE
    if _WEIGHTS_CACHE is None:
        _WEIGHTS_CACHE = _get_weights()
    return _WEIGHTS_CACHE


# 하위 호환을 위해 WEIGHTS 이름 노출 (lazy getter 사용)
_WEIGHTS_LOCK = threading.Lock()

class _WeightsProxy(dict):
    """WEIGHTS lazy 초기화 프록시 (dict 상속)."""
    def __init__(self):
        super().__init__()
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            with _WEIGHTS_LOCK:
                if not self._loaded:  # double-check
                    self.update(_get_weights_cached())
                    self._loaded = True

    def __getitem__(self, key):
        self._ensure_loaded()
        return super().__getitem__(key)

    def keys(self):
        self._ensure_loaded()
        return super().keys()

    def values(self):
        self._ensure_loaded()
        return super().values()

    def items(self):
        self._ensure_loaded()
        return super().items()

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self):
        self._ensure_loaded()
        return super().__len__()

    def __contains__(self, item):
        """in 연산자 오버라이드 - _ensure_loaded() 호출 보장."""
        self._ensure_loaded()
        return super().__contains__(item)

    def reload(self):
        """config reload 시 호출하여 캐시를 초기화합니다."""
        self._loaded = False


WEIGHTS = _WeightsProxy()  # dict 상속 프록시


def get_output_keys() -> List[str]:
    """출력 키 목록을 반환합니다 (config reload 반영)."""
    return list(_get_weights_cached().keys())


def reload_weights_cache() -> None:
    """가중치 캐시를 초기화합니다 (config reload 시 호출)."""
    global _WEIGHTS_CACHE
    _WEIGHTS_CACHE = None


class _OutputKeysProxy(list):
    """OUTPUT_KEYS를 위한 lazy proxy - config reload 지원."""
    def __init__(self):
        super().__init__()
        self._loaded = False

    def _ensure(self):
        if not self._loaded:
            self.extend(get_output_keys())
            self._loaded = True

    def __iter__(self):
        self._ensure()
        return super().__iter__()

    def __len__(self):
        self._ensure()
        return super().__len__()

    def __getitem__(self, i):
        self._ensure()
        return super().__getitem__(i)

    def __contains__(self, item):
        """in 연산자 오버라이드 - _ensure() 호출 보장."""
        self._ensure()
        return super().__contains__(item)

    def reload(self):
        """config reload 시 호출하여 캐시를 초기화합니다."""
        self.clear()
        self._loaded = False


OUTPUT_KEYS: List[str] = _OutputKeysProxy()  # 하위 호환


def get_measurement_categories() -> List[Tuple[str, List[str]]]:
    """직교 키 카테고리를 반환합니다 (llm_prompt_template.md에서 로드).
    
    [REFACTOR 2026-05-22] 하드코딩된 _MEASUREMENT_CATEGORIES를 동적 로드로 변경.
    llm_prompt_template.md의 SCORE_MAPPING 섹션을 기반으로 카테고리를 생성합니다.
    
    Returns:
        List[(카테고리명, [source_key 목록])]
    """
    cats = get_v3_categories()
    if cats:
        return cats
    # 템플릿 로드 실패 시 기본값 반환 (하위 호환)
    log.warning("카테고리 로드 실패, 기본값 사용")
    return [
        ("색소 (Pigmentation)",       ["pigmentation_cov", "spot_density"]),
        ("홍조·병변 (Redness/Lesion)", ["diffuse_redness",  "focal_lesion"]),
        ("모공 (Pore)",                ["pore_score"]),
        ("주름 (Wrinkle)",             ["wrinkle_score"]),
        ("텍스처 (Texture)",           ["roughness_score"]),
        ("톤·밝기 (Tone)",             ["tone_score"]),
        ("탄력 (Elasticity)",          ["elasticity_score"]),
        ("피부 타입 (Skin Type)",      ["skin_type_score"]),
    ]


# 하위 호환을 위한 별칭 (이름 변경 권장)
_MEASUREMENT_CATEGORIES = get_measurement_categories


# ── 직교 분해 함수 ────────────────────────────────────────────

def _compose_pigmentation_scores(pig: Dict[str, float]) -> Dict[str, float]:
    """색소 직교 분해.

    pigmentation_cov  ←  L* 잔차 면적 기반 (melasma 면적)
    spot_density      ←  blob NMS 개수 기반 (freckle 개수)

    [v3.2] lentigo / pigment_mark 삭제 → melasma(기미·잡티) + freckle(주근깨)
    직교 보장:
      L*_area_ratio (연속 면적)  vs  blob_count (이산 개체 수)
      Corr(넓은 면적, 점 개수) ≈ 0  — 물리적 독립
    """
    mel     = float(pig.get("melasma_score", 0) or 0)
    freckle = float(pig.get("freckle_score", 0) or 0)
    return {
        "pigmentation_cov": round(_clamp(mel), 1),
        "spot_density":     round(_clamp(freckle), 1),
    }


def _compose_redness_lesion_scores(
    red: Dict[str, float],
    acne: Dict[str, float],
) -> Dict[str, float]:
    """홍조·병변 직교 분해 (핵심 재설계).

    [FIX ORTHOGONAL-A] PIE(post_inflammatory_erythema_score) 완전 제거
    diffuse_redness  ←  a* 전역 z-score + local 임계 + telangiectasia 3-way 합성
                        = redness_score (내부에서 이미 3-way 합성 완료)
                        PIE 제거: redness_score 단독 사용
    focal_lesion     ←  a* 국소 잔차 + blob 기반 (개별 병변)
                        = acne * 0.65 + post_acne_pigment * 0.35
                        PIE 제거 후 가중치 재조정

    [FIX REVIEW-①] telangiectasia_score 는 _analyze_redness 내부에서
    redness_score 합성(local*0.40 + global*0.40 + tela*0.20)에 흡수됨.
    이 함수에서는 별도 처리 불필요.

    직교 보장:
      diffuse ← E[a*(skin)] 분포 중심 이동 측정 (전역 홍조 체질)
      focal   ← a*_local 국소 극값 잔차 측정 (개별 병변)
    """
    redness = float(red.get("redness_score",              0) or 0)
    acne_s  = float(acne.get("acne_score",                0) or 0)
    red_m   = float(acne.get("post_acne_pigment_score",            0) or 0)
    return {
        "diffuse_redness": round(_clamp(redness), 1),
        "focal_lesion":    round(_clamp(acne_s  * 0.65 + red_m  * 0.35), 1),
    }


def _compose_pore_score(pores: Dict[str, float]) -> Dict[str, float]:
    """모공 통합.

    pore_size_score    ←  LoG sigma 크기·밀도 (독립 신호)
    pore_sagging_score ←  타원 장단축비 (독립 신호)
    두 신호 이미 직교 → 가중 합산.  size 55% > sagging 45%
    """
    sz  = float(pores.get("pore_size_score",    0) or 0)
    sag = float(pores.get("pore_sagging_score", 0) or 0)
    return {"pore_score": round(_clamp(sz * 0.55 + sag * 0.45), 1)}


def _compose_wrinkle_score(wrinkles: Dict[str, float]) -> Dict[str, float]:
    """주름 통합.

    eye_wrinkle      ←  외측 canthus Sobel_Y (정면+측면)
    nasolabial       ←  팔자 ROI Sobel mag   (정면+측면)
    fine_deep        ←  이마 CLAHE Sobel     (정면 전용)
    세 ROI 해부학적으로 분리 → 이미 공간 독립.
    가중치: eye 0.40 / nasolabial 0.35 / fine_deep 0.25
    """
    eye  = float(wrinkles.get("eye_wrinkle_score",       0) or 0)
    naso = float(wrinkles.get("nasolabial_wrinkle_score", 0) or 0)
    fine = float(wrinkles.get("fine_deep_wrinkle_score",  0) or 0)
    return {"wrinkle_score": round(_clamp(eye * 0.40 + naso * 0.35 + fine * 0.25), 1)}


def _compose_tone_score(tone: Dict[str, float]) -> Dict[str, float]:
    """톤 직교 통합.

    skin_tone_score   ←  ITA = arctan2(L*-50, b*)  절대 밝기
    uneven_tone_score ←  std(strip_norm(L))          조명 독립 불균일
    dullness_score    ←  L_mean + S 기반 (skin_tone과 r≈0.85 → 제거)

    tone_score = ITA_norm * 0.60 + uniformity * 0.40
    직교 보장: strip_norm이 L_mean 성분 제거 → Cov(ITA, L_std_strip) ≈ 0
    """
    ita        = float(tone.get("skin_tone_score",   0) or 0)
    uniformity = float(tone.get("uneven_tone_score", 0) or 0)
    return {"tone_score": round(_clamp(ita * 0.60 + uniformity * 0.40), 1)}


def _compose_elasticity_score(elasticity: Dict[str, float]) -> Dict[str, float]:
    """탄력 독립화.

    v2.6: jawline_blur가 eye_wrinkle_score를 입력으로 받는 구조
          eye_elasticity = eye_wrinkle * 0.65 + dark_circle * 0.35
    v3.0: jawline_blur = chin Sobel_Y 단독 신호 (eye_wrinkle 의존 제거)
          cheek_sagging = 너비비 + 밝기차 형태 신호

    elasticity_score = jawline_blur * 0.60 + cheek_sagging * 0.40
    """
    jaw = float(elasticity.get("jawline_blur_score",  0) or 0)
    sag = float(elasticity.get("cheek_sagging_score", 0) or 0)
    return {"elasticity_score": round(_clamp(jaw * 0.60 + sag * 0.40), 1)}


def _compose_skin_type_score(sebum: Dict[str, float]) -> Dict[str, float]:
    """피부 타입 균형 점수.

    skin_type_score: analyze_sebum()이 산출한 balance_score를 그대로 전달.
      - 높을수록 지성↔건성 균형 → 중성에 가까움
      - 낮을수록 한쪽으로 치우침 (지성/건성/복합성)

    설계 의도:
      - v3 종합 점수에 skin_type_score 키로 독립적으로 기여 (가중치 0.04, config.json).
      - elasticity_score(jawline_blur_score, cheek_sagging_score)와 별개의 항목으로 유지.
      - 피부 타입(지성/건성/중성)은 탄력(처짐)과 물리적으로 다른 차원이므로
        직교 신호로 분리하여 각각 독립적으로 종합 점수에 기여하도록 설계됨.
    """
    val = float(sebum.get("skin_type_score", 0) or 0)
    return {"skin_type_score": round(_clamp(val), 1)}


def _compose_roughness_score(texture: Dict[str, float]) -> Dict[str, float]:
    """거칠기 점수.

    roughness_score: 텍스처 분석기가 산출한 거칠기 점수를 그대로 전달.
      - 높을수록 피부 표면이 거칠음
      - 낮을수록 피부 표면이 매끄러움

    설계 의도:
      - v3 종합 점수에 roughness_score 키로 독립적으로 기여 (가중치 0.08, config.json).
      - wrinkle_score와 별개의 항목으로 유지하여 텍스처 차원을 분리.
      - 거칠기는 주름과 물리적으로 다른 차원(미세 텍스처 vs 선형 주름)이므로
        직교 신호로 분리하여 각각 독립적으로 종합 점수에 기여하도록 설계됨.
    """
    val = float(texture.get("roughness_score", 0) or 0)
    return {"roughness_score": round(_clamp(val), 1)}


def _compose_hydration_score(sebum: Dict[str, float]) -> Dict[str, float]:
    """[하위 호환 래퍼] _compose_skin_type_score 로 위임."""
    return _compose_skin_type_score(sebum)


# ── 종합 점수 ────────────────────────────────────────────

def _compute_overall_score(
    measurements: Dict[str, object],
    *,
    debug: bool = False,
) -> float:
    """10개 직교 항목 가중치 기반 종합 점수 (내부 0~100)."""
    weighted_sum = 0.0
    total_w = sum(WEIGHTS.values())
    for key, w in WEIGHTS.items():
        v = measurements.get(key)
        if v is None:
            continue
        try:
            weighted_sum += float(v) * w
        except (TypeError, ValueError):
            if debug:
                log.debug("종합 점수 키 %r 값 %r 스킵", key, v)
    return round(weighted_sum / total_w, 1) if total_w > 0 else 0.0


# ── 보고서 ──────────────────────────────────────────────

def measurement_report_string(results: Dict[str, Any]) -> str:
    """10개 직교 항목 리포트 문자열."""
    meas = results.get("measurements", {})
    ov   = results.get("overall_score", "N/A")
    age  = results.get("perceived_age",  "N/A")
    lines_out: List[str] = [
        "",
        "=" * 65,
        f"  SkinLens v1.0 피부 분석  |  종합 점수: {ov}점  |  인지 나이: {age}세",
        "=" * 65,
    ]
    for cat_name, keys in _MEASUREMENT_CATEGORIES():
        lines_out.append("")
        lines_out.append(f"  ■ {cat_name}")
        for k in keys:
            v = meas.get(k, "N/A")
            lines_out.append(f"    {k:<30} {v} (10~90)")
    lines_out.extend(["", "=" * 65, ""])
    return "\n".join(lines_out)
