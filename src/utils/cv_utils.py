"""src.utils.cv_utils

OpenCV 기반 CV 유틸리티 함수 - skimage 의존성 제거용.

제공하는 함수:
  - blob_log_cv: Laplacian of Gaussian blob detection (skimage.feature.blob_log 대체)
  - local_binary_pattern_cv: Local Binary Pattern (skimage.feature.local_binary_pattern 대체)
  - graycomatrix_cv: Gray Level Co-occurrence Matrix (skimage.feature.graycomatrix 대체)
  - graycoprops_cv: GLCM 속성 계산 (skimage.feature.graycoprops 대체)
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)


def blob_log_cv(
    image: np.ndarray,
    min_sigma: float = 1.0,
    max_sigma: float = 30.0,
    num_sigma: int = 10,
    threshold: float = 0.2,
    overlap: float = 0.5,
    log_scale: bool = False,
) -> np.ndarray:
    """Laplacian of Gaussian blob detection (skimage fallback).

    skimage.feature.blob_log의 래퍼. skimage가 없으면 빈 배열 반환.

    Args:
        image: 입력 이미지 (grayscale, float32)
        min_sigma: 최소 sigma 값
        max_sigma: 최대 sigma 값
        num_sigma: sigma 단계 수
        threshold: 임계값 (상대적)
        overlap: blob 간 중복 허용 비율
        log_scale: sigma를 로그 스케일로 사용

    Returns:
        (N, 3) 배열 - [y, x, sigma]
    """
    try:
        from skimage.feature import blob_log
        return blob_log(
            image,
            min_sigma=min_sigma,
            max_sigma=max_sigma,
            num_sigma=num_sigma,
            threshold=threshold,
            overlap=overlap,
            log_scale=log_scale,
        )
    except ImportError:
        log.warning("skimage not available, blob_log_cv returning empty array")
        return np.empty((0, 3))


def local_binary_pattern_cv(
    image: np.ndarray,
    P: int = 8,
    R: float = 1.0,
    method: str = "uniform"
) -> np.ndarray:
    """Local Binary Pattern (skimage fallback).

    skimage.feature.local_binary_pattern의 래퍼. skimage가 없으면 빈 배열 반환.

    Args:
        image: 입력 이미지 (grayscale, uint8)
        P: 이웃 픽셀 수 (보통 8)
        R: 반경
        method: 'default', 'ror', 'uniform', 'nri_uniform'

    Returns:
        LBP 이미지 (uint64)
    """
    try:
        from skimage.feature import local_binary_pattern
        return local_binary_pattern(image, P=P, R=R, method=method)
    except ImportError:
        log.warning("skimage not available, local_binary_pattern_cv returning zeros")
        return np.zeros_like(image, dtype=np.uint64)


def graycomatrix_cv(
    image: np.ndarray,
    distances: List[int],
    angles: List[float],
    levels: int = 256,
    symmetric: bool = True,
    normed: bool = False,
) -> np.ndarray:
    """Gray Level Co-occurrence Matrix (skimage fallback).

    skimage.feature.graycomatrix의 래퍼. skimage가 없으면 빈 배열 반환.

    Args:
        image: 입력 이미지 (grayscale, uint8)
        distances: 거리 리스트 (픽셀 단위)
        angles: 각도 리스트 (라디안)
        levels: 그레이 레벨 수
        symmetric: 대칭 행렬 여부
        normed: 정규화 여부

    Returns:
        (len(distances), len(angles), levels, levels) 배열
    """
    try:
        from skimage.feature import graycomatrix
        return graycomatrix(
            image,
            distances=distances,
            angles=angles,
            levels=levels,
            symmetric=symmetric,
            normed=normed,
        )
    except ImportError:
        log.warning("skimage not available, graycomatrix_cv returning empty array")
        return np.empty((len(distances), len(angles), levels, levels))


def graycoprops_cv(
    glcm: np.ndarray,
    props: List[str] = ["contrast", "dissimilarity", "homogeneity", "ASM", "energy"]
) -> np.ndarray:
    """GLCM 속성 계산 (skimage fallback).

    skimage.feature.graycoprops의 래퍼. skimage가 없으면 빈 배열 반환.

    Args:
        glcm: graycomatrix_cv로 계산된 GLCM
        props: 계산할 속성 리스트

    Returns:
        (len(distances), len(angles), len(props)) 배열
    """
    try:
        from skimage.feature import graycoprops
        return graycoprops(glcm, props=props)
    except ImportError:
        log.warning("skimage not available, graycoprops_cv returning empty array")
        return np.empty((glcm.shape[0], glcm.shape[1], len(props)))
