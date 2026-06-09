"""
Scoring Report 테스트 - 보고서 생성 및 점수 계산
"""
import pytest
from src.scoring._report import (
    get_report_weights,
    get_report_keys,
    get_report_categories,
    get_report_display_names,
    _compute_overall_score_report,
    ReportLayer,
    measurement_report_string,
    _LazyReportAttr,
)


class TestReportLazyAccessors:
    """Report Lazy Accessors 테스트"""

    def test_get_report_weights(self):
        """보고서 가중치 로드"""
        weights = get_report_weights()
        assert isinstance(weights, dict)
        assert len(weights) > 0
        # 가중치는 0-1 범위여야 함
        for key, weight in weights.items():
            assert 0 <= weight <= 1

    def test_get_report_keys(self):
        """보고서 키 로드"""
        keys = get_report_keys()
        assert isinstance(keys, list)
        assert len(keys) > 0
        # 모든 키는 문자열이어야 함
        for key in keys:
            assert isinstance(key, str)

    def test_get_report_categories(self):
        """보고서 카테고리 로드"""
        categories = get_report_categories()
        assert isinstance(categories, list)
        assert len(categories) > 0
        # 각 카테고리는 (이름, 키 리스트) 튜플이어야 함
        for category_name, keys in categories:
            assert isinstance(category_name, str)
            assert isinstance(keys, list)

    def test_get_report_display_names(self):
        """보고서 표시 이름 로드"""
        display_names = get_report_display_names()
        assert isinstance(display_names, dict)
        assert len(display_names) > 0
        # 모든 키와 값은 문자열이어야 함
        for key, name in display_names.items():
            assert isinstance(key, str)
            assert isinstance(name, str)


class TestLazyReportAttr:
    """_LazyReportAttr 테스트"""

    def test_lazy_weights_caching(self):
        """가중치 캐싱 검증"""
        weights1 = _LazyReportAttr.weights()
        weights2 = _LazyReportAttr.weights()
        # 같은 객체인지 확인
        assert weights1 is weights2

    def test_lazy_keys_caching(self):
        """키 캐싱 검증"""
        keys1 = _LazyReportAttr.keys()
        keys2 = _LazyReportAttr.keys()
        # 같은 객체인지 확인
        assert keys1 is keys2

    def test_lazy_categories_caching(self):
        """카테고리 캐싱 검증"""
        categories1 = _LazyReportAttr.categories()
        categories2 = _LazyReportAttr.categories()
        # 같은 객체인지 확인
        assert categories1 is categories2

    def test_lazy_display_names_caching(self):
        """표시 이름 캐싱 검증"""
        display_names1 = _LazyReportAttr.display_names()
        display_names2 = _LazyReportAttr.display_names()
        # 같은 객체인지 확인
        assert display_names1 is display_names2

    def test_lazy_weights_consistency(self):
        """가중치 일관성 검증"""
        weights = _LazyReportAttr.weights()
        keys = _LazyReportAttr.keys()
        # 키는 가중치의 키와 일치해야 함
        assert set(keys) == set(weights.keys())


class TestComputeOverallScoreReport:
    """종합 점수 계산 테스트"""

    def test_compute_overall_score_report_basic(self):
        """기본 종합 점수 계산"""
        measurements = {
            "melasma_score": 80.0,
            "redness_score": 75.0,
            "pore_size_score": 70.0
        }
        score = _compute_overall_score_report(measurements)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_compute_overall_score_report_with_none(self):
        """None 값이 있는 경우 종합 점수 계산"""
        measurements = {
            "melasma_score": 80.0,
            "redness_score": None,
            "pore_size_score": 70.0
        }
        score = _compute_overall_score_report(measurements)
        assert isinstance(score, float)
        # None 값은 건너뛰어야 함

    def test_compute_overall_score_report_empty(self):
        """빈 측정값으로 종합 점수 계산"""
        measurements = {}
        score = _compute_overall_score_report(measurements)
        assert score == 0.0

    def test_compute_overall_score_report_invalid_value(self):
        """잘못된 값이 있는 경우 종합 점수 계산"""
        measurements = {
            "melasma_score": 80.0,
            "redness_score": "invalid",
            "pore_size_score": 70.0
        }
        score = _compute_overall_score_report(measurements, debug=True)
        assert isinstance(score, float)
        # 잘못된 값은 건너뛰어야 함

    def test_compute_overall_score_report_clamping(self):
        """점수 클램핑 검증"""
        measurements = {
            "melasma_score": 150.0,  # 100 초과
            "redness_score": -10.0,  # 0 미만
            "pore_size_score": 50.0
        }
        score = _compute_overall_score_report(measurements)
        assert 0 <= score <= 100


class TestReportLayer:
    """ReportLayer 테스트"""

    @pytest.fixture
    def report_layer(self):
        """ReportLayer 인스턴스 생성"""
        return ReportLayer()

    def test_report_layer_build_basic(self, report_layer):
        """기본 보고서 레이어 빌드"""
        m2_raw = {
            "melasma_score": 80.0,
            "redness_score": 75.0
        }
        m3_raw = {
            "pigmentation_cov": 0.5,
            "diffuse_redness": 0.3
        }
        
        report, overall = report_layer.build(m2_raw, m3_raw)
        assert isinstance(report, dict)
        assert isinstance(overall, float)
        assert 0 <= overall <= 100

    def test_report_layer_build_with_raw_measurements(self, report_layer):
        """raw_measurements와 함께 보고서 레이어 빌드"""
        m2_raw = {}
        m3_raw = {}
        raw_measurements = {
            "melasma_score": 80.0,
            "redness_score": 75.0
        }
        
        report, overall = report_layer.build(m2_raw, m3_raw, raw_measurements=raw_measurements)
        assert isinstance(report, dict)
        assert isinstance(overall, float)

    def test_report_layer_fallback_from_v3(self, report_layer):
        """v3 데이터에서 폴백"""
        m2_raw = {}
        m3_raw = {
            "pigmentation_cov": 0.5,
            "diffuse_redness": 0.3,
            "pore_score": 0.4
        }
        
        report, overall = report_layer.build(m2_raw, m3_raw)
        assert isinstance(report, dict)
        # m2_raw이 없어도 v3 데이터에서 계산되어야 함

    def test_report_layer_score_transformation(self, report_layer):
        """점수 변환 검증"""
        m2_raw = {
            "melasma_score": 50.0,
            "redness_score": 50.0
        }
        m3_raw = {}
        
        report, overall = report_layer.build(m2_raw, m3_raw)
        # 변환된 점수와 원본 점수가 모두 있어야 함
        assert "melasma_score" in report
        assert "melasma_score_raw" in report
        assert "overall_score_report_raw" in report

    def test_report_layer_clamping(self, report_layer):
        """점수 클램핑 검증"""
        m2_raw = {
            "melasma_score": 150.0,
            "redness_score": -10.0
        }
        m3_raw = {}
        
        report, overall = report_layer.build(m2_raw, m3_raw)
        # 클램핑된 점수 확인
        assert 0 <= report["melasma_score"] <= 100
        assert 0 <= report["redness_score"] <= 100


class TestMeasurementReportString:
    """측정 보고서 문자열 테스트"""

    def test_measurement_report_string_basic(self):
        """기본 측정 보고서 문자열 생성"""
        results = {
            "measurements_report": {
                "melasma_score": 80.0,
                "redness_score": 75.0
            },
            "overall_score": 78.0,
            "overall_score_report": 77.5,
            "perceived_age": 30
        }
        
        report_str = measurement_report_string(results)
        assert isinstance(report_str, str)
        assert len(report_str) > 0
        assert "COTELEAF" in report_str
        assert "종합" in report_str

    def test_measurement_report_string_with_missing_fields(self):
        """누락된 필드가 있는 경우 보고서 문자열 생성"""
        results = {
            "measurements_report": {
                "melasma_score": 80.0
            },
            "overall_score": "N/A",
            "overall_score_report": "N/A",
            "perceived_age": "N/A"
        }
        
        report_str = measurement_report_string(results)
        assert isinstance(report_str, str)
        assert "N/A" in report_str

    def test_measurement_report_string_structure(self):
        """보고서 문자열 구조 검증"""
        results = {
            "measurements_report": {
                "melasma_score": 80.0
            },
            "overall_score": 78.0,
            "overall_score_report": 77.5,
            "perceived_age": 30
        }
        
        report_str = measurement_report_string(results)
        # 구분자 확인
        assert "=" in report_str
        assert "【" in report_str
        assert "】" in report_str

    def test_measurement_report_string_empty(self):
        """빈 결과로 보고서 문자열 생성"""
        results = {
            "measurements_report": {},
            "overall_score": "N/A",
            "overall_score_report": "N/A",
            "perceived_age": "N/A"
        }
        
        report_str = measurement_report_string(results)
        assert isinstance(report_str, str)
        assert len(report_str) > 0


class TestReportIntegration:
    """보고서 통합 테스트"""

    def test_report_integration(self):
        """보고서 모듈 통합 테스트"""
        # 모든 함수가 임포트되고 호출 가능해야 함
        weights = get_report_weights()
        keys = get_report_keys()
        categories = get_report_categories()
        display_names = get_report_display_names()
        
        assert isinstance(weights, dict)
        assert isinstance(keys, list)
        assert isinstance(categories, list)
        assert isinstance(display_names, dict)

    def test_report_data_consistency(self):
        """보고서 데이터 일관성 검증"""
        weights = get_report_weights()
        keys = get_report_keys()
        display_names = get_report_display_names()
        
        # 가중치의 키와 키 리스트가 일치해야 함
        assert set(keys) == set(weights.keys())
        
        # 키 리스트의 모든 항목이 표시 이름에 있어야 함
        for key in keys:
            assert key in display_names
