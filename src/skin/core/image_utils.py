"""src.skin.core.image_utils — 이미지 입출력 및 피부 마스크 유틸리티.

[REFACTOR] skin_scoring.py에서 분리.
  - _imread_bgr
  - _skin_mask
  - _skin_stat
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np

log = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None  # type: ignore


def imread_bgr(path: str | Path) -> Optional[np.ndarray]:
    """유니코드 경로 안전 이미지 로드 (BGR)."""
    try:
        data = Path(path).expanduser().read_bytes()
    except OSError:
        return None
    if not data:
        return None
    buf = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


# 하위 호환 alias
_imread_bgr = imread_bgr


def skin_mask(face_region: np.ndarray) -> np.ndarray:
    """적응형 피부 마스크 (Fitzpatrick I~VI 대응)."""
    h, w = face_region.shape[:2]
    cy, cx = h // 2, w // 2
    ph, pw = max(h // 6, 10), max(w // 6, 10)
    patch = face_region[cy - ph: cy + ph, cx - pw: cx + pw]
    if patch.size == 0:
        patch = face_region

    ycrcb_patch = cv2.cvtColor(patch, cv2.COLOR_BGR2YCrCb)
    hsv_patch   = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)

    cr_med = float(np.median(ycrcb_patch[:, :, 1]))
    cb_med = float(np.median(ycrcb_patch[:, :, 2]))
    v_med  = float(np.median(hsv_patch[:, :, 2]))

    cr_lo = max(125, int(cr_med - 22)); cr_hi = min(185, int(cr_med + 22))
    cb_lo = max(75,  int(cb_med - 22)); cb_hi = min(135, int(cb_med + 22))

    ycrcb = cv2.cvtColor(face_region, cv2.COLOR_BGR2YCrCb)
    mask_ycrcb = cv2.inRange(
        ycrcb,
        np.array([0, cr_lo, cb_lo], np.uint8),
        np.array([255, cr_hi, cb_hi], np.uint8),
    )

    v_lo = max(22, int(v_med * 0.35))
    hsv  = cv2.cvtColor(face_region, cv2.COLOR_BGR2HSV)
    mask_hsv = cv2.inRange(
        hsv,
        np.array([0, 10, v_lo], np.uint8),
        np.array([28, 185, 255], np.uint8),
    )

    mask = cv2.bitwise_and(mask_hsv, mask_ycrcb)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))

    if np.count_nonzero(mask) / (h * w) < 0.10:
        mask = cv2.morphologyEx(
            mask_ycrcb, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        )
    if np.count_nonzero(mask) < h * w * 0.08:
        mask = np.ones((h, w), dtype=np.uint8) * 255
    return mask


# 하위 호환 alias
_skin_mask = skin_mask


def skin_stat(lab: np.ndarray, skin_mask_arr: np.ndarray) -> Dict[str, float]:
    """LAB 이미지에서 피부 영역 통계 추출."""
    L_ch = lab[:, :, 0].astype(float)
    a_ch = lab[:, :, 1].astype(float)
    b_ch = lab[:, :, 2].astype(float)
    sk   = skin_mask_arr > 0
    if sk.any():
        return {
            "base_L": float(np.median(L_ch[sk])), "std_L": float(np.std(L_ch[sk])),
            "base_a": float(np.median(a_ch[sk])), "std_a": float(np.std(a_ch[sk])),
            "base_b": float(np.median(b_ch[sk])), "std_b": float(np.std(b_ch[sk])),
        }
    return {
        "base_L": float(np.mean(L_ch)), "std_L": float(np.std(L_ch)),
        "base_a": float(np.mean(a_ch)), "std_a": float(np.std(a_ch)),
        "base_b": float(np.mean(b_ch)), "std_b": float(np.std(b_ch)),
    }


# 하위 호환 alias
_skin_stat = skin_stat
