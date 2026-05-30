"""
Scoring Multi-View 테스트 - 멀티뷰 분석 및 병합
"""
import pytest
import numpy as np
from src.scoring._multi_view import LateralFaceAnalyzer


class TestLateralFaceAnalyzer:
    """LateralFaceAnalyzer 테스트"""

    @pytest.fixture
    def analyzer(self):
        """LateralFaceAnalyzer 인스턴스 생성"""
        return LateralFaceAnalyzer()

    @pytest.fixture
    def dummy_face(self):
        """더미 얼굴 이미지 생성"""
        return np.ones((200, 200, 3), dtype=np.uint8) * 128

    def test_lateral_regions_structure(self, analyzer):
        """측면 영역 구조 검증"""
        regions = analyzer._LATERAL_REGIONS
        assert isinstance(regions, dict)
        assert "eye_outer_v" in regions
        assert "eye_outer_h" in regions
        assert "nasolabial_v" in regions
        assert "nasolabial_h" in regions
        assert "cheek_v" in regions
        assert "cheek_h" in regions
        assert "chin_v" in regions
        assert "chin_h" in regions

    def test_lateral_regions_ranges(self, analyzer):
        """측면 영역 범위 검증"""
        regions = analyzer._LATERAL_REGIONS
        for key, (v_range, h_range) in regions.items():
            assert 0 <= v_range[0] < v_range[1] <= 1
            assert 0 <= h_range[0] < h_range[1] <= 1

    def test_get_roi(self, analyzer, dummy_face):
        """ROI 추출 테스트"""
        roi = analyzer._get_roi(dummy_face, (0.2, 0.5), (0.3, 0.7))
        assert isinstance(roi, np.ndarray)
        assert roi.shape[0] < dummy_face.shape[0]
        assert roi.shape[1] < dummy_face.shape[1]

    def test_sobel_components(self, analyzer, dummy_face):
        """Sobel 컴포넌트 계산 테스트"""
        gray = np.mean(dummy_face, axis=2).astype(np.uint8)
        mag, sx_mean, sy_mean = analyzer._sobel_components(gray)
        assert isinstance(mag, float)
        assert isinstance(sx_mean, float)
        assert isinstance(sy_mean, float)
        assert mag >= 0
        assert sx_mean >= 0
        assert sy_mean >= 0

    def test_measure_eye_wrinkle_small_roi(self, analyzer, dummy_face):
        """작은 ROI에서 눈가 주름 측정"""
        # 작은 ROI로 인해 None 반환
        result = analyzer._measure_eye_wrinkle(dummy_face)
        # 얼굴 검출 실패 가능성으로 None일 수 있음
        assert result is None or isinstance(result, float)

    def test_measure_nasolabial_small_roi(self, analyzer, dummy_face):
        """작은 ROI에서 비강 주름 측정"""
        result = analyzer._measure_nasolabial(dummy_face)
        # 얼굴 검출 실패 가능성으로 None일 수 있음
        assert result is None or isinstance(result, float)

    def test_extract_lateral_face_no_detection(self, analyzer, dummy_face):
        """얼굴 검출 실패 시 측면 얼굴 추출"""
        # 더미 이미지로 얼굴 검출 실패 가능성
        result = analyzer._extract_lateral_face(dummy_face)
        assert result is None or isinstance(result, np.ndarray)

    def test_lateral_face_analyzer_initialization(self):
        """LateralFaceAnalyzer 초기화 테스트"""
        analyzer = LateralFaceAnalyzer()
        assert analyzer.face_detector is not None

    def test_lateral_face_analyzer_with_custom_detector(self):
        """커스텀 얼굴 검출기로 초기화"""
        from src.skin.core.face_detector import FaceDetector
        custom_detector = FaceDetector()
        analyzer = LateralFaceAnalyzer(face_detector=custom_detector)
        assert analyzer.face_detector is custom_detector

    def test_roi_extraction_boundary(self, analyzer, dummy_face):
        """ROI 추출 경계 테스트"""
        # 경계 조건 테스트
        roi = analyzer._get_roi(dummy_face, (0.0, 1.0), (0.0, 1.0))
        assert roi.shape == dummy_face.shape

    def test_sobel_components_edge_case(self, analyzer):
        """Sobel 컴포넌트 엣지 케이스 테스트"""
        # 균일한 이미지
        uniform = np.ones((100, 100), dtype=np.uint8) * 128
        mag, sx_mean, sy_mean = analyzer._sobel_components(uniform)
        # 균일한 이미지에서는 그라디언트가 0에 가까워야 함
        assert mag < 1.0
        assert sx_mean < 1.0
        assert sy_mean < 1.0

    def test_lateral_regions_completeness(self, analyzer):
        """측면 영역 완전성 검증"""
        required_regions = [
            "eye_outer_v", "eye_outer_h",
            "nasolabial_v", "nasolabial_h",
            "cheek_v", "cheek_h",
            "chin_v", "chin_h"
        ]
        for region in required_regions:
            assert region in analyzer._LATERAL_REGIONS

    def test_measure_eye_wrinkle_clahe_preprocessed(self, analyzer, dummy_face):
        """CLAHE 전처리된 눈가 주름 측정"""
        result = analyzer._measure_eye_wrinkle(dummy_face, clahe_preprocessed=True)
        assert result is None or isinstance(result, float)

    def test_measure_nasolabial_clahe_preprocessed(self, analyzer, dummy_face):
        """CLAHE 전처리된 비강 주름 측정"""
        result = analyzer._measure_nasolabial(dummy_face, clahe_preprocessed=True)
        assert result is None or isinstance(result, float)


class TestMultiViewIntegration:
    """멀티뷰 통합 테스트"""

    def test_multi_view_import(self):
        """멀티뷰 모듈 임포트 테스트"""
        from src.scoring._multi_view import LateralFaceAnalyzer
        assert LateralFaceAnalyzer is not None

    def test_lateral_analyzer_class_methods(self):
        """LateralFaceAnalyzer 클래스 메서드 검증"""
        from src.scoring._multi_view import LateralFaceAnalyzer
        analyzer = LateralFaceAnalyzer()
        
        # 필수 메서드 존재 확인
        assert hasattr(analyzer, '_extract_lateral_face')
        assert hasattr(analyzer, '_sobel_components')
        assert hasattr(analyzer, '_get_roi')
        assert hasattr(analyzer, '_measure_eye_wrinkle')
        assert hasattr(analyzer, '_measure_nasolabial')

    def test_lateral_regions_constancy(self):
        """측면 영역 상수성 검증"""
        from src.scoring._multi_view import LateralFaceAnalyzer
        analyzer1 = LateralFaceAnalyzer()
        analyzer2 = LateralFaceAnalyzer()
        
        # 두 인스턴스의 영역이 같아야 함
        assert analyzer1._LATERAL_REGIONS == analyzer2._LATERAL_REGIONS
