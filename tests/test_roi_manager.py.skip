"""
ROIManager 단위 테스트 - ROI 추출, 유효성 검증
"""
import numpy as np
import pytest


class TestROIManager:
    """ROIManager 테스트"""

    def test_singleton_pattern(self):
        """싱글톤 패턴 확인"""
        from src.config.roi_manager import ROIManager
        
        instance1 = ROIManager.get_instance()
        instance2 = ROIManager.get_instance()
        assert instance1 is instance2

    def test_get_forehead_roi(self):
        """이마 ROI 추출 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        # 테스트용 얼굴 이미지 생성 (100x100x3)
        face = np.zeros((100, 100, 3), dtype=np.uint8)
        forehead = roi_manager.get_forehead_roi(face)
        
        # 이마 ROI는 상단 30%여야 함
        assert forehead.shape[0] == 30  # 100 * 0.30
        assert forehead.shape[1] == 100
        assert forehead.shape[2] == 3

    def test_get_glabella_roi(self):
        """미간 ROI 추출 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        regions = {
            "glabella": np.zeros((20, 20, 3), dtype=np.uint8)
        }
        glabella = roi_manager.get_glabella_roi(np.zeros((100, 100, 3), dtype=np.uint8), regions)
        
        assert glabella.shape == (20, 20, 3)

    def test_get_eye_roi(self):
        """눈 영역 ROI 추출 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        regions = {
            "left_canthus": np.zeros((15, 15, 3), dtype=np.uint8),
            "right_canthus": np.zeros((15, 15, 3), dtype=np.uint8),
        }
        eye_rois = roi_manager.get_eye_roi(np.zeros((100, 100, 3), dtype=np.uint8), regions)
        
        assert "left_canthus" in eye_rois
        assert "right_canthus" in eye_rois
        assert eye_rois["left_canthus"].shape == (15, 15, 3)
        assert eye_rois["right_canthus"].shape == (15, 15, 3)

    def test_get_nasolabial_roi(self):
        """팔자 주름 ROI 추출 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        regions = {
            "nasolabial_l": np.zeros((20, 20, 3), dtype=np.uint8),
            "nasolabial_r": np.zeros((20, 20, 3), dtype=np.uint8),
        }
        nl_rois = roi_manager.get_nasolabial_roi(np.zeros((100, 100, 3), dtype=np.uint8), regions)
        
        assert "nasolabial_l" in nl_rois
        assert "nasolabial_r" in nl_rois
        assert nl_rois["nasolabial_l"].shape == (20, 20, 3)
        assert nl_rois["nasolabial_r"].shape == (20, 20, 3)

    def test_get_cheek_roi(self):
        """볼 영역 ROI 추출 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        regions = {
            "left_cheek": np.zeros((30, 30, 3), dtype=np.uint8),
            "right_cheek": np.zeros((30, 30, 3), dtype=np.uint8),
        }
        cheek_rois = roi_manager.get_cheek_roi(np.zeros((100, 100, 3), dtype=np.uint8), regions)
        
        assert "left_cheek" in cheek_rois
        assert "right_cheek" in cheek_rois
        assert cheek_rois["left_cheek"].shape == (30, 30, 3)
        assert cheek_rois["right_cheek"].shape == (30, 30, 3)

    def test_get_pore_roi(self):
        """모공 분석용 ROI 추출 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        regions = {
            "forehead": np.zeros((30, 30, 3), dtype=np.uint8),
            "left_cheek": np.zeros((30, 30, 3), dtype=np.uint8),
            "right_cheek": np.zeros((30, 30, 3), dtype=np.uint8),
            "nose": np.zeros((20, 20, 3), dtype=np.uint8),
        }
        pore_rois = roi_manager.get_pore_roi(np.zeros((100, 100, 3), dtype=np.uint8), regions)
        
        assert "forehead" in pore_rois
        assert "left_cheek" in pore_rois
        assert "right_cheek" in pore_rois
        assert "nose" in pore_rois

    def test_validate_roi_valid(self):
        """유효한 ROI 검증 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        valid_roi = np.zeros((20, 20, 3), dtype=np.uint8)
        assert roi_manager.validate_roi(valid_roi) == True

    def test_validate_roi_too_small(self):
        """너무 작은 ROI 검증 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        small_roi = np.zeros((5, 5, 3), dtype=np.uint8)
        assert roi_manager.validate_roi(small_roi, min_size=8) == False

    def test_validate_roi_none(self):
        """None ROI 검증 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        assert roi_manager.validate_roi(None) == False

    def test_validate_roi_empty(self):
        """빈 ROI 검증 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        empty_roi = np.array([])
        assert roi_manager.validate_roi(empty_roi) == False

    def test_get_face_roi_constants(self):
        """FaceROI 상수 접근 테스트"""
        from src.config.roi_manager import ROIManager
        from src.skin.core.face_roi import FaceROI
        
        roi_manager = ROIManager.get_instance()
        face_roi = roi_manager.get_face_roi_constants()
        
        assert face_roi is FaceROI
        assert hasattr(face_roi, 'FOREHEAD_TOP')
        assert hasattr(face_roi, 'FOREHEAD_BOTTOM')

    def test_missing_region_fallback(self):
        """누락된 ROI 폴백 테스트"""
        from src.config.roi_manager import ROIManager
        
        roi_manager = ROIManager.get_instance()
        
        # 빈 regions 딕셔너리
        regions = {}
        
        # 폴백으로 빈 ROI 반환
        glabella = roi_manager.get_glabella_roi(np.zeros((100, 100, 3), dtype=np.uint8), regions)
        assert glabella.shape == (10, 10, 3)  # 기본 폴백 크기
