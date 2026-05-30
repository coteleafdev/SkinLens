"""
Scoring Score Utils 테스트 - 점수 스케일 변환 유틸리티
"""
import pytest
import numpy as np
from src.scoring._score_utils import (
    _get_measurement_actual_ranges,
    invalidate_actual_ranges_cache,
    _map_score_display_10_90,
    _map_score_display_10_90_adjusted,
    _score_from_display_10_90,
    _score_from_display_10_90_adjusted,
    _apply_measurements_display_10_90,
    _snap_score,
    _quantize_score_to_20,
    _adaptive_threshold,
)


class TestScoreMapping:
    """점수 매핑 테스트"""

    def test_map_score_display_10_90(self):
        """0-100 점수를 10-90 범위로 매핑"""
        # 0 -> 10
        assert _map_score_display_10_90(0.0) == 10.0
        # 50 -> 50
        assert _map_score_display_10_90(50.0) == 50.0
        # 100 -> 90
        assert _map_score_display_10_90(100.0) == 90.0

    def test_map_score_display_10_90_clamping(self):
        """점수 클램핑 검증"""
        # -10 -> 10 (클램핑)
        assert _map_score_display_10_90(-10.0) == 10.0
        # 150 -> 90 (클램핑)
        assert _map_score_display_10_90(150.0) == 90.0

    def test_map_score_display_10_90_adjusted(self):
        """실제 범위 조정된 점수 매핑"""
        # 기본 범위가 없는 경우
        result = _map_score_display_10_90_adjusted("nonexistent_key", 50.0)
        assert 10.0 <= result <= 90.0

    def test_map_score_display_10_90_adjusted_with_ranges(self):
        """실제 범위가 있는 경우 조정된 매핑"""
        # 실제 범위가 설정된 경우 테스트
        result = _map_score_display_10_90_adjusted("melasma_score", 50.0)
        assert 10.0 <= result <= 90.0

    def test_score_from_display_10_90(self):
        """10-90 범위를 0-100으로 역매핑"""
        # 10 -> 0
        assert _score_from_display_10_90(10.0) == 0.0
        # 50 -> 50
        assert _score_from_display_10_90(50.0) == 50.0
        # 90 -> 100
        assert _score_from_display_10_90(90.0) == 100.0

    def test_score_from_display_10_90_clamping(self):
        """역매핑 클램핑 검증"""
        # 5 -> 0 (클램핑)
        assert _score_from_display_10_90(5.0) == 0.0
        # 95 -> 100 (클램핑)
        assert _score_from_display_10_90(95.0) == 100.0

    def test_score_from_display_10_90_adjusted(self):
        """실제 범위 조정된 역매핑"""
        # 기본 범위가 없는 경우
        result = _score_from_display_10_90_adjusted("nonexistent_key", 50.0)
        assert 0.0 <= result <= 100.0

    def test_score_from_display_10_90_adjusted_with_ranges(self):
        """실제 범위가 있는 경우 조정된 역매핑"""
        result = _score_from_display_10_90_adjusted("melasma_score", 50.0)
        assert 0.0 <= result <= 100.0

    def test_mapping_round_trip(self):
        """매핑 역매핑 라운드 트립 테스트"""
        original = 75.0
        mapped = _map_score_display_10_90(original)
        unmapped = _score_from_display_10_90(mapped)
        assert abs(unmapped - original) < 0.1


class TestApplyMeasurementsDisplay:
    """측정값 표시 변환 테스트"""

    def test_apply_measurements_display_10_90(self):
        """측정값 표시 변환 적용"""
        measurements = {
            "melasma_score": 80.0,
            "redness_score": 75.0,
            "other_field": "value"
        }
        
        _apply_measurements_display_10_90(measurements)
        
        # _raw 필드가 추가되어야 함
        assert "melasma_score_raw" in measurements
        assert "redness_score_raw" in measurements
        # 다른 필드는 변경되지 않아야 함
        assert measurements["other_field"] == "value"

    def test_apply_measurements_display_10_90_boolean_skip(self):
        """불리언 값 건너뛰기"""
        measurements = {
            "some_field": True,
            "melasma_score": 80.0
        }
        
        _apply_measurements_display_10_90(measurements)
        
        # 불리언 필드는 건너뛰어야 함
        assert measurements["some_field"] is True
        # 점수 필드는 변환되어야 함
        assert "melasma_score_raw" in measurements

    def test_apply_measurements_display_10_90_clamping(self):
        """점수 클램핑 검증"""
        measurements = {
            "melasma_score": 150.0  # 100 초과
        }
        
        _apply_measurements_display_10_90(measurements)
        
        # 클램핑된 값이어야 함
        assert 10.0 <= measurements["melasma_score"] <= 90.0


class TestScoreQuantization:
    """점수 양자화 테스트"""

    def test_snap_score(self):
        """점수 스냅 테스트"""
        assert _snap_score(5.0) == 10
        assert _snap_score(25.0) == 30
        assert _snap_score(45.0) == 50
        assert _snap_score(65.0) == 70
        assert _snap_score(85.0) == 90

    def test_snap_score_boundaries(self):
        """점수 스냅 경계 테스트"""
        assert _snap_score(19.9) == 10
        assert _snap_score(20.0) == 30
        assert _snap_score(39.9) == 30
        assert _snap_score(40.0) == 50
        assert _snap_score(59.9) == 50
        assert _snap_score(60.0) == 70
        assert _snap_score(79.9) == 70
        assert _snap_score(80.0) == 90

    def test_quantize_score_to_20(self):
        """점수 20단위 양자화 테스트"""
        assert _quantize_score_to_20(5.0) == 10
        assert _quantize_score_to_20(25.0) == 30
        assert _quantize_score_to_20(45.0) == 50
        assert _quantize_score_to_20(65.0) == 70
        assert _quantize_score_to_20(85.0) == 90

    def test_quantize_score_to_20_boundaries(self):
        """양자화 경계 테스트"""
        assert _quantize_score_to_20(19.9) == 10
        assert _quantize_score_to_20(20.0) == 30
        assert _quantize_score_to_20(39.9) == 30
        assert _quantize_score_to_20(40.0) == 50


class TestAdaptiveThreshold:
    """적응형 임계값 테스트"""

    def test_adaptive_threshold_basic(self):
        """기본 적응형 임계값 계산"""
        channel = np.random.rand(100, 100) * 255
        threshold = _adaptive_threshold(channel, mask=None)
        assert isinstance(threshold, float)
        assert 0 <= threshold <= 255

    def test_adaptive_threshold_with_mask(self):
        """마스크와 함께 적응형 임계값 계산"""
        channel = np.random.rand(100, 100) * 255
        mask = np.ones((100, 100), dtype=np.uint8)
        threshold = _adaptive_threshold(channel, mask=mask)
        assert isinstance(threshold, float)

    def test_adaptive_threshold_empty_mask(self):
        """빈 마스크로 적응형 임계값 계산"""
        channel = np.random.rand(100, 100) * 255
        mask = np.zeros((100, 100), dtype=np.uint8)
        threshold = _adaptive_threshold(channel, mask=mask)
        assert isinstance(threshold, float)

    def test_adaptive_threshold_z_parameter(self):
        """z 파라미터 테스트"""
        channel = np.random.rand(100, 100) * 255
        threshold1 = _adaptive_threshold(channel, mask=None, z=1.0)
        threshold2 = _adaptive_threshold(channel, mask=None, z=2.0)
        # z가 클수록 임계값이 낮아져야 함
        assert threshold2 < threshold1


class TestActualRangesCache:
    """실제 범위 캐시 테스트"""

    def test_get_measurement_actual_ranges(self):
        """실제 범위 로드"""
        ranges = _get_measurement_actual_ranges()
        assert isinstance(ranges, dict)

    def test_invalidate_actual_ranges_cache(self):
        """실제 범위 캐시 초기화"""
        # 캐시 미리 로드
        _get_measurement_actual_ranges()
        
        # 캐시 초기화
        invalidate_actual_ranges_cache()
        
        # 다시 로드 가능해야 함
        ranges = _get_measurement_actual_ranges()
        assert isinstance(ranges, dict)

    def test_actual_ranges_caching(self):
        """실제 범위 캐싱 검증"""
        ranges1 = _get_measurement_actual_ranges()
        ranges2 = _get_measurement_actual_ranges()
        # 같은 객체인지 확인
        assert ranges1 is ranges2


class TestScoreUtilsIntegration:
    """점수 유틸리티 통합 테스트"""

    def test_score_utils_import(self):
        """점수 유틸리티 모듈 임포트 테스트"""
        from src.scoring._score_utils import (
            _map_score_display_10_90,
            _score_from_display_10_90,
            _snap_score,
            _quantize_score_to_20,
        )
        assert callable(_map_score_display_10_90)
        assert callable(_score_from_display_10_90)
        assert callable(_snap_score)
        assert callable(_quantize_score_to_20)

    def test_score_transformation_pipeline(self):
        """점수 변환 파이프라인 테스트"""
        original = 75.0
        
        # 매핑
        mapped = _map_score_display_10_90(original)
        
        # 스냅
        snapped = _snap_score(mapped)
        
        # 역매핑
        unmapped = _score_from_display_10_90(snapped)
        
        # 모든 단계가 유효해야 함
        assert 10.0 <= mapped <= 90.0
        assert snapped in [10, 30, 50, 70, 90]
        assert 0.0 <= unmapped <= 100.0

    def test_measurement_transformation_pipeline(self):
        """측정값 변환 파이프라인 테스트"""
        measurements = {
            "melasma_score": 80.0,
            "redness_score": 75.0,
            "pore_size_score": 70.0
        }
        
        # 변환 적용
        _apply_measurements_display_10_90(measurements)
        
        # 모든 점수에 _raw 필드가 있어야 함
        for key in ["melasma_score", "redness_score", "pore_size_score"]:
            assert f"{key}_raw" in measurements
            assert 10.0 <= measurements[key] <= 90.0
