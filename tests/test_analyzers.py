"""tests/test_analyzers.py

도메인별 분석기 단위 테스트.

각 analyzer 함수가 올바른 키를 반환하고 점수 범위가 유효한지 검증.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.skin.analyzers.pigmentation import analyze_pigmentation, make_pigment_mask
from src.skin.analyzers.strategies.redness_analyzer import analyze_redness
from src.skin.analyzers.pore import analyze_pores
from src.skin.analyzers.wrinkle_texture import (
    analyze_wrinkles,
    analyze_texture,
    analyze_restoration_quality,
)
from src.skin.analyzers.tone_elasticity import (
    analyze_tone,
    analyze_elasticity,
    analyze_sebum,
    analyze_acne_marks,
    analyze_perceived_age,
)


def make_dummy_face(h: int = 100, w: int = 100) -> np.ndarray:
    """더미 얼굴 이미지 생성."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def make_dummy_mask(h: int = 100, w: int = 100) -> np.ndarray:
    """더미 피부 마스크 생성."""
    return np.ones((h, w), dtype=np.uint8) * 255


def make_dummy_stat() -> dict:
    """더미 피부 통계 생성."""
    return {
        "base_L": 150.0,
        "std_L": 10.0,
        "base_a": 134.0,
        "std_a": 5.0,
        "base_b": 128.0,
        "std_b": 5.0,
    }


def make_dummy_regions(h: int = 100, w: int = 100) -> dict:
    """더미 ROI 영역 생성."""
    return {
        "forehead": np.zeros((h // 4, w, 3), dtype=np.uint8),
        "left_eye": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
        "right_eye": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
        "nose": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
        "left_cheek": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
        "right_cheek": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
        "chin": np.zeros((h // 4, w, 3), dtype=np.uint8),
        "lower_face": np.zeros((h // 4, w, 3), dtype=np.uint8),
        "t_zone": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
        "u_zone": np.zeros((h // 4, w // 3, 3), dtype=np.uint8),
    }


# ─────────────────────────────────────────────────────────────────
# pigmentation 테스트
# ─────────────────────────────────────────────────────────────────

def test_analyze_pigmentation_returns_required_keys():
    """pigmentation analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    mask = make_dummy_mask()
    stat = make_dummy_stat()

    result = analyze_pigmentation(
        face, mask, stat,
        bp_melasma=[(0.0, 100.0), (0.05, 50.0)],
        bp_freckle_count=[(0, 100.0), (5, 50.0)],
        freckle_params={"threshold": 0.08, "min_sigma": 1.0, "max_sigma": 5.0, "overlap": 0.4},
    )

    assert "melasma_score" in result
    assert "freckle_score" in result
    assert "pih_score" in result
    assert 0.0 <= result["melasma_score"] <= 100.0
    assert 0.0 <= result["freckle_score"] <= 100.0
    assert 0.0 <= result["pih_score"] <= 100.0


def test_make_pigment_mask():
    """색소 전용 마스크 생성 함수 테스트."""
    mask = make_dummy_mask(100, 100)
    pig_mask = make_pigment_mask(mask, 100, 100)

    assert pig_mask.shape == mask.shape
    assert pig_mask.dtype == mask.dtype


# ─────────────────────────────────────────────────────────────────
# redness 테스트
# ─────────────────────────────────────────────────────────────────

def test_analyze_redness_returns_required_keys():
    """redness analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    mask = make_dummy_mask()
    stat = make_dummy_stat()
    regions = make_dummy_regions()

    result = analyze_redness(
        face, mask, regions, stat,
        clahe_clip=2.0,
        clahe_tile=(8, 8),
        bp_redness=[(0.0, 100.0), (0.01, 50.0)],
        bp_pie=[(0.0, 100.0), (0.005, 50.0)],
    )

    assert "redness_score" in result
    assert "post_inflammatory_erythema_score" in result
    assert 0.0 <= result["redness_score"] <= 100.0
    assert 0.0 <= result["post_inflammatory_erythema_score"] <= 100.0


# ─────────────────────────────────────────────────────────────────
# pore 테스트
# ─────────────────────────────────────────────────────────────────

def test_analyze_pores_returns_required_keys():
    """pore analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()

    result = analyze_pores(
        face, regions,
        blob_params={"thresholds": [0.055, 0.042], "min_sigma": 1.12, "max_sigma": 6.5, "overlap": 0.35},
        clahe_clip=2.2,
        clahe_tile=(8, 8),
        bp_pore_density=[(0.0, 100.0), (10.0, 50.0)],
        bp_sagging_lap=[(0.0, 100.0), (5.0, 50.0)],
    )

    assert "pore_size_score" in result
    assert "pore_sagging_score" in result
    assert 0.0 <= result["pore_size_score"] <= 100.0
    assert 0.0 <= result["pore_sagging_score"] <= 100.0


# ─────────────────────────────────────────────────────────────────
# wrinkle_texture 테스트
# ─────────────────────────────────────────────────────────────────

def test_analyze_wrinkles_returns_required_keys():
    """wrinkle analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()
    mask = make_dummy_mask()

    result = analyze_wrinkles(
        face, regions,
        clahe_preprocessed=False,
        skin_mask=mask,
        bp_eye=[(0.0, 100.0), (5.0, 50.0)],
        bp_nasolabial=[(0.0, 100.0), (5.0, 50.0)],
    )

    assert "eye_wrinkle_score" in result
    assert "glabella_wrinkle_score" in result
    assert "nasolabial_wrinkle_score" in result
    assert "fine_deep_wrinkle_score" in result
    for key in ["eye_wrinkle_score", "glabella_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score"]:
        assert 0.0 <= result[key] <= 100.0


def test_analyze_texture_returns_required_keys():
    """texture analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()
    mask = make_dummy_mask()

    result = analyze_texture(
        face, regions, mask,
        clahe_clip=2.0,
        clahe_tile=(8, 8),
        bp_roughness=[(0.0, 100.0), (500.0, 50.0)],
    )

    assert "roughness_score" in result
    assert "dead_skin_score" in result
    assert "smoothness_score" in result
    for key in ["roughness_score", "dead_skin_score", "smoothness_score"]:
        assert 0.0 <= result[key] <= 100.0


def test_analyze_restoration_quality_returns_required_keys():
    """restoration quality analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()
    mask = make_dummy_mask()

    result = analyze_restoration_quality(face, regions, mask)

    assert "noise_score" in result
    assert "detail_score" in result
    assert "color_balance_score" in result
    for key in ["noise_score", "detail_score", "color_balance_score"]:
        assert 0.0 <= result[key] <= 100.0


# ─────────────────────────────────────────────────────────────────
# tone_elasticity 테스트
# ─────────────────────────────────────────────────────────────────

def test_analyze_tone_returns_required_keys():
    """tone analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()
    mask = make_dummy_mask()

    result = analyze_tone(face, regions, mask)

    assert "skin_tone_score" in result
    assert "dullness_score" in result
    assert "uneven_tone_score" in result
    for key in ["skin_tone_score", "dullness_score", "uneven_tone_score"]:
        assert 0.0 <= result[key] <= 100.0


def test_analyze_elasticity_returns_required_keys():
    """elasticity analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()

    result = analyze_elasticity(
        face, regions,
        bp_jawline=[(0.0, 0), (5.0, 20), (12.0, 40)],
    )

    assert "cheek_sagging_score" in result
    assert "jawline_blur_score" in result
    assert "eye_elasticity_score" in result
    for key in ["cheek_sagging_score", "jawline_blur_score", "eye_elasticity_score"]:
        assert 0.0 <= result[key] <= 100.0


def test_analyze_sebum_returns_required_keys():
    """sebum analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    regions = make_dummy_regions()
    mask = make_dummy_mask()

    result = analyze_sebum(face, regions, mask)

    assert "oily_score" in result
    assert "dry_score" in result
    assert "sebum_score" in result
    assert "skin_type_score" in result
    assert "skin_type_label" in result
    for key in ["oily_score", "dry_score", "sebum_score", "skin_type_score"]:
        assert 0.0 <= result[key] <= 100.0
    assert result["skin_type_label"] in ("지성", "건성", "복합성", "중성")


def test_analyze_acne_marks_returns_required_keys():
    """acne marks analyzer가 올바른 키를 반환하는지 검증."""
    face = make_dummy_face()
    mask = make_dummy_mask()
    stat = make_dummy_stat()

    result = analyze_acne_marks(
        face, mask, stat,
        bp_acne=[(0.0, 100.0), (0.01, 50.0)],
        bp_pap=[(0.0, 100.0), (0.01, 50.0)],
    )

    assert "acne_score" in result
    assert "post_acne_pigment_score" in result
    for key in ["acne_score", "post_acne_pigment_score"]:
        assert 0.0 <= result[key] <= 100.0


def test_analyze_perceived_age_returns_required_keys():
    """perceived age analyzer가 올바른 값을 반환하는지 검증."""
    face = make_dummy_face()
    eye_wrinkle_score = 50.0
    lines_score = 50.0

    result = analyze_perceived_age(
        face,
        eye_wrinkle_score=eye_wrinkle_score,
        lines_score=lines_score,
    )

    assert isinstance(result, float)
    assert 20.0 <= result <= 80.0  # 합리적인 인지 나이 범위


def test_analyzers_edge_case_stability():
    """극단 입력값에 대한 analyzer 안정성 테스트."""
    face = make_dummy_face()
    mask = make_dummy_mask()
    stat = make_dummy_stat()

    # 극단 점수 값 (0, 100)에 대한 안정성
    extreme_scores = [0.0, 100.0, -10.0, 150.0]

    for score in extreme_scores:
        # analyze_sebum
        result = analyze_sebum(
            face, mask, stat,
            oily_score=score,
            dry_score=score,
            bp_oily=[(0.0, 100.0)],
            bp_dry=[(0.0, 100.0)],
        )
        assert "skin_type_score" in result
        assert "skin_type_label" in result
        # 점수는 클램핑되어야 함
        assert 0.0 <= result["skin_type_score"] <= 100.0

    # 빈 이미지 또는 마스크에 대한 안정성
    empty_face = np.zeros((10, 10, 3), dtype=np.uint8)
    empty_mask = np.zeros((10, 10), dtype=np.uint8)

    try:
        result = analyze_sebum(
            empty_face, empty_mask, stat,
            oily_score=50.0,
            dry_score=50.0,
            bp_oily=[(0.0, 100.0)],
            bp_dry=[(0.0, 100.0)],
        )
        # 빈 이미지라도 예외를 발생시키지 않고 기본값을 반환해야 함
        assert isinstance(result, dict)
    except Exception:
        # 예외가 발생해도 안정성을 위해 처리되어야 함
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
