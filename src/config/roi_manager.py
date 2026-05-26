"""src.config.roi_manager — ROI 관리자.

[REFACTOR P1] ROI 관리 중앙화:
  - ROI 정의 상수화 (FaceROI 래핑)
  - ROI 유효성 검증
  - ROI 캐싱
  - ROI 일관성 확보

사용법:
    from src.config.roi_manager import ROIManager

    roi = ROIManager.get_instance()
    forehead = roi.get_forehead_roi(face)
    glabella = roi.get_glabella_roi(face, regions)
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import numpy as np

from src.skin.core.face_roi import FaceROI

log = logging.getLogger(__name__)


class ROIManager:
    """ROI 관리자 (싱글톤).
    
    얼굴 영역(ROI)을 중앙에서 관리하고 캐싱합니다.
    FaceROI 상수를 래핑하고 ROI 추출 로직을 제공합니다.
    """
    
    _instance: Optional["ROIManager"] = None
    _lock = type(None)  # Placeholder, will be replaced with threading.Lock if needed
    
    def __new__(cls) -> "ROIManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self._roi_cache: Dict[str, np.ndarray] = {}
    
    # ── ROI 추출 ───────────────────────────────────────────────────
    
    def get_forehead_roi(self, face: np.ndarray) -> np.ndarray:
        """이마 ROI를 추출합니다.
        
        Args:
            face: 얼굴 이미지 (BGR, uint8)
        
        Returns:
            이마 영역 이미지
        """
        fh = face.shape[0]
        y0 = int(fh * FaceROI.FOREHEAD_TOP)
        y1 = int(fh * FaceROI.FOREHEAD_BOTTOM)
        return face[y0:y1, :]
    
    def get_glabella_roi(self, face: np.ndarray, regions: Dict[str, np.ndarray]) -> np.ndarray:
        """미간 ROI를 추출합니다.
        
        Args:
            face: 얼굴 이미지
            regions: ROI 딕셔너리
        
        Returns:
            미간 영역 이미지
        """
        return regions.get("glabella", np.zeros((10, 10, 3), dtype=np.uint8))
    
    def get_eye_roi(self, face: np.ndarray, regions: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """눈 영역 ROI를 추출합니다.
        
        Args:
            face: 얼굴 이미지
            regions: ROI 딕셔너리
        
        Returns:
            {left_canthus, right_canthus} 딕셔너리
        """
        return {
            "left_canthus": regions.get("left_canthus", np.zeros((10, 10, 3), dtype=np.uint8)),
            "right_canthus": regions.get("right_canthus", np.zeros((10, 10, 3), dtype=np.uint8)),
        }
    
    def get_nasolabial_roi(self, face: np.ndarray, regions: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """팔자 주름 ROI를 추출합니다.
        
        Args:
            face: 얼굴 이미지
            regions: ROI 딕셔너리
        
        Returns:
            {nasolabial_l, nasolabial_r} 딕셔너리
        """
        return {
            "nasolabial_l": regions.get("nasolabial_l", np.zeros((10, 10, 3), dtype=np.uint8)),
            "nasolabial_r": regions.get("nasolabial_r", np.zeros((10, 10, 3), dtype=np.uint8)),
        }
    
    def get_cheek_roi(self, face: np.ndarray, regions: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """볼 영역 ROI를 추출합니다.
        
        Args:
            face: 얼굴 이미지
            regions: ROI 딕셔너리
        
        Returns:
            {left_cheek, right_cheek} 딕셔너리
        """
        return {
            "left_cheek": regions.get("left_cheek", np.zeros((10, 10, 3), dtype=np.uint8)),
            "right_cheek": regions.get("right_cheek", np.zeros((10, 10, 3), dtype=np.uint8)),
        }
    
    def get_pore_roi(self, face: np.ndarray, regions: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """모공 분석용 ROI를 추출합니다.
        
        Args:
            face: 얼굴 이미지
            regions: ROI 딕셔너리
        
        Returns:
            {forehead, left_cheek, right_cheek, nose} 딕셔너리
        """
        return {
            "forehead": regions.get("forehead", np.zeros((10, 10, 3), dtype=np.uint8)),
            "left_cheek": regions.get("left_cheek", np.zeros((10, 10, 3), dtype=np.uint8)),
            "right_cheek": regions.get("right_cheek", np.zeros((10, 10, 3), dtype=np.uint8)),
            "nose": regions.get("nose", np.zeros((10, 10, 3), dtype=np.uint8)),
        }
    
    # ── ROI 유효성 검증 ─────────────────────────────────────────────
    
    def validate_roi(self, roi: np.ndarray, min_size: int = 8) -> bool:
        """ROI 유효성을 검증합니다.
        
        Args:
            roi: ROI 이미지
            min_size: 최소 크기 (기본값: 8)
        
        Returns:
            유효하면 True, 그렇지 않으면 False
        """
        if roi is None or roi.size == 0:
            return False
        if min(roi.shape[:2]) < min_size:
            return False
        return True
    
    # ── ROI 상수 접근자 ────────────────────────────────────────────
    
    @staticmethod
    def get_face_roi_constants() -> type[FaceROI]:
        """FaceROI 상수 클래스를 반환합니다."""
        return FaceROI
    
    # ── 유틸리티 ───────────────────────────────────────────────────
    
    @staticmethod
    def get_instance() -> "ROIManager":
        """싱글톤 인스턴스를 반환합니다."""
        if ROIManager._instance is None:
            ROIManager._instance = ROIManager()
        return ROIManager._instance


# 편의 함수: 싱글톤 인스턴스 접근
get_roi_manager = ROIManager.get_instance
