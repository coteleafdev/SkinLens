"""
skin.core.face_roi
==================
얼굴 이미지 ROI(Region of Interest) 비율 상수 SSOT.

[REFACTOR P2] _SkinAnalyzerV2 분석 메서드 전반에 리터럴로 산재하던
얼굴 분할 비율(fh * 0.18 등)을 이 모듈로 집중합니다.

모든 비율은 정규화된 얼굴 이미지 기준 (0.0 ~ 1.0):
  - fh: 얼굴 높이 (face height)
  - fw: 얼굴 너비 (face width)

사용:
    from skin.core.face_roi import FaceROI

    pigment_sk[int(fh * FaceROI.EYE_TOP) : int(fh * FaceROI.EYE_BOTTOM), :] = 0
"""
from __future__ import annotations


class FaceROI:
    """얼굴 영역 분할 비율 상수.

    ┌──────────────────────────────────────────┐  fh * 0.00
    │               헤어라인                   │
    ├──────────────────────────────────────────┤  fh * 0.08  (HAIRLINE_BOTTOM)
    │               이마 (forehead)            │
    ├──────────────────────────────────────────┤  fh * 0.18  (EYE_TOP / GLABELLA_TOP)
    │  눈·눈썹 (eye / brow)                   │
    ├──────────────────────────────────────────┤  fh * 0.48  (EYE_BOTTOM / NOSE_TOP)
    │         코 끝 (nose tip)                 │
    ├──────────────────────────────────────────┤  fh * 0.60  (NOSE_BOTTOM / PHILTRUM_TOP)
    │         인중 (philtrum)                  │
    ├──────────────────────────────────────────┤  fh * 0.62  (PHILTRUM_BOTTOM / MOUTH_TOP)
    │  입·턱 중앙 (mouth / chin)               │
    ├──────────────────────────────────────────┤  fh * 0.90  (MOUTH_BOTTOM)
    │               목 하단                   │
    └──────────────────────────────────────────┘  fh * 1.00
                                                  (NECK_BOTTOM = 0.95)
    """

    # ── 수직 경계 (높이 비율) ──────────────────────────────────────
    HAIRLINE_TOP: float    = 0.00  # 이미지 최상단
    HAIRLINE_BOTTOM: float = 0.08  # 헤어라인 끝 (색소 분석 시 제외 상단)

    FOREHEAD_TOP: float    = 0.00
    FOREHEAD_BOTTOM: float = 0.30  # 이마 끝 / T존 상단

    GLABELLA_TOP: float    = 0.18  # 미간 상단
    GLABELLA_BOTTOM: float = 0.40  # 미간 하단

    EYE_TOP: float         = 0.18  # 눈·눈썹 영역 상단 (색소 마스크 제외)
    EYE_BOTTOM: float      = 0.48  # 눈·눈썹 영역 하단

    NOSE_TOP: float        = 0.48  # 코 시작 (= 눈 영역 끝)
    NOSE_BOTTOM: float     = 0.60  # 코 끝

    # 인중 (philtrum) 영역: 코 끝과 입 사이
    PHILTRUM_TOP: float    = 0.60  # 인중 상단 (= 코 끝)
    PHILTRUM_BOTTOM: float = 0.62  # 인중 하단

    MOUTH_TOP: float       = 0.62  # 입 시작 (인중 하단 = 입 시작)
    MOUTH_BOTTOM: float    = 0.90  # 입·턱 끝

    CHEEK_TOP: float       = 0.40  # 볼 시작
    CHEEK_BOTTOM: float    = 0.75  # 볼 끝

    LOWER_CHEEK_TOP: float    = 0.58
    LOWER_CHEEK_BOTTOM: float = 0.78

    CHIN_TOP: float        = 0.75  # 턱 시작
    CHIN_BOTTOM: float     = 1.00  # 이미지 최하단

    LOWER_FACE_TOP: float  = 0.55  # 하안면 시작

    NECK_BOTTOM: float     = 0.95  # 목 하단 (색소 마스크 제외)

    # ── 수평 경계 (너비 비율) ──────────────────────────────────────
    LEFT_HALF: float       = 0.50
    RIGHT_HALF: float      = 0.50

    NOSE_LEFT: float       = 0.35  # 코 좌측 경계
    NOSE_RIGHT: float      = 0.65  # 코 우측 경계

    MOUTH_LEFT: float      = 0.25  # 입·턱 좌측 경계
    MOUTH_RIGHT: float     = 0.75  # 입·턱 우측 경계

    CHEEK_LEFT_INNER: float  = 0.35   # 좌측 볼 안쪽
    CHEEK_LEFT_OUTER: float  = 0.00
    CHEEK_RIGHT_INNER: float = 0.65   # 우측 볼 안쪽
    CHEEK_RIGHT_OUTER: float = 1.00

    EYE_LEFT_INNER: float  = 0.40
    EYE_RIGHT_INNER: float = 0.60

    GLABELLA_LEFT: float   = 0.38
    GLABELLA_RIGHT: float  = 0.62

    NASOLABIAL_LEFT: float   = 0.38
    NASOLABIAL_RIGHT: float  = 0.62

    LOWER_CHEEK_LEFT: float  = 0.38
    LOWER_CHEEK_RIGHT: float = 0.62

    LEFT_CANTHUS_RIGHT: float  = 0.28
    RIGHT_CANTHUS_LEFT: float  = 0.72

    # ── 색소 전용 마스크 제외 영역 (복합 사용 편의) ──────────────
    # _analyze_pigmentation 에서 pigment_sk 마스크 구성에 사용
    PIGMENT_EXCLUDE_EYE_TOP: float     = EYE_TOP        # 0.18
    PIGMENT_EXCLUDE_EYE_BOTTOM: float  = EYE_BOTTOM     # 0.48
    PIGMENT_EXCLUDE_MOUTH_TOP: float   = MOUTH_TOP      # 0.60
    PIGMENT_EXCLUDE_MOUTH_BOTTOM: float= MOUTH_BOTTOM   # 0.90
    PIGMENT_EXCLUDE_MOUTH_LEFT: float  = MOUTH_LEFT     # 0.25
    PIGMENT_EXCLUDE_MOUTH_RIGHT: float = MOUTH_RIGHT    # 0.75
    PIGMENT_EXCLUDE_NOSE_TOP: float    = NOSE_TOP       # 0.48
    PIGMENT_EXCLUDE_NOSE_BOTTOM: float = NOSE_BOTTOM    # 0.62
    PIGMENT_EXCLUDE_NOSE_LEFT: float   = NOSE_LEFT      # 0.35
    PIGMENT_EXCLUDE_NOSE_RIGHT: float  = NOSE_RIGHT     # 0.65
    PIGMENT_EXCLUDE_HAIR_BOTTOM: float = HAIRLINE_BOTTOM # 0.08
    PIGMENT_EXCLUDE_NECK_BOTTOM: float = NECK_BOTTOM    # 0.95
