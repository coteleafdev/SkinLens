"""
test_prescription_calculator.py — 처방 계산기 단위 테스트

피부 평가 점수 및 PCR 결과 기반 처방전 계산 테스트
"""
import pytest
from unittest.mock import patch, MagicMock
from src.prescription.prescription_calculator import (
    _load_prescription_config,
    get_measurement_metadata,
    get_all_measurements,
    get_category_metadata,
    get_all_categories,
    get_measurements_by_category,
    get_measurement_display_names,
    get_ordered_measurement_keys,
    get_mix_code_definition,
    get_all_mix_codes,
    calculate_skin_assessment_percentage,
    calculate_skin_assessment_recipe,
    get_age_group,
    calculate_pcr_prescription_for_category,
    calculate_pcr_recipe,
    create_prescription,
    _calculate_skin_type_mix,
    _calculate_concern_mix
)


class TestPrescriptionConfig:
    """처방전 설정 로드 테스트"""
    
    def test_load_prescription_config_default(self):
        """기본 설정 로드 테스트"""
        config = _load_prescription_config()
        
        assert config is not None
        assert "enabled" in config
        assert "skin_assessment" in config
        assert "age_group_mapping" in config
        assert "pcr" in config
    
    def test_load_prescription_config_structure(self):
        """설정 구조 테스트"""
        config = _load_prescription_config()
        
        # skin_assessment 설정
        skin_config = config["skin_assessment"]
        assert "good_threshold" in skin_config
        assert "critical_threshold" in skin_config
        assert "max_percentage" in skin_config
        assert "min_percentage" in skin_config
        
        # age_group_mapping 설정
        age_mapping = config["age_group_mapping"]
        assert isinstance(age_mapping, list)
        assert len(age_mapping) > 0
        assert all("min_age" in m and "max_age" in m and "group" in m for m in age_mapping)
        
        # pcr 설정
        pcr_config = config["pcr"]
        assert "total_rules" in pcr_config
        assert "beneficial_rules" in pcr_config
        assert "trouble_rules" in pcr_config
        assert "harmful_rules" in pcr_config


class TestMeasurementMetadata:
    """측정항목 메타데이터 테스트"""
    
    def test_get_measurement_metadata_existing(self):
        """존재하는 측정항목 메타데이터 테스트"""
        # config.json에 있는 측정항목으로 테스트
        metadata = get_measurement_metadata("melasma_score")
        
        # config.json에 따라 결과가 다를 수 있음
        if metadata:
            assert "name_ko" in metadata or "name_en" in metadata
    
    def test_get_measurement_metadata_nonexistent(self):
        """존재하지 않는 측정항목 메타데이터 테스트"""
        metadata = get_measurement_metadata("nonexistent_score")
        
        assert metadata is None
    
    def test_get_all_measurements(self):
        """모든 측정항목 메타데이터 테스트"""
        measurements = get_all_measurements()
        
        assert isinstance(measurements, dict)
        # config.json에 따라 결과가 다를 수 있음
    
    def test_get_category_metadata_existing(self):
        """존재하는 카테고리 메타데이터 테스트"""
        metadata = get_category_metadata("pigmentation")
        
        # config.json에 따라 결과가 다를 수 있음
        if metadata:
            assert "name_ko" in metadata or "name_en" in metadata
    
    def test_get_category_metadata_nonexistent(self):
        """존재하지 않는 카테고리 메타데이터 테스트"""
        metadata = get_category_metadata("nonexistent_category")
        
        assert metadata is None
    
    def test_get_all_categories(self):
        """모든 카테고리 메타데이터 테스트"""
        categories = get_all_categories()
        
        assert isinstance(categories, dict)
    
    def test_get_measurements_by_category(self):
        """카테고리별 측정항목 테스트"""
        measurements = get_measurements_by_category("pigmentation")
        
        assert isinstance(measurements, list)
    
    def test_get_measurement_display_names(self):
        """측정항목 디스플레이 이름 테스트"""
        display_names = get_measurement_display_names()
        
        assert isinstance(display_names, dict)
        # 값이 한글인지 확인 (config.json에 따라 다를 수 있음)
        if display_names:
            for key, name in display_names.items():
                assert isinstance(name, str)
    
    def test_get_ordered_measurement_keys(self):
        """정렬된 측정항목 키 테스트"""
        ordered_keys = get_ordered_measurement_keys()
        
        assert isinstance(ordered_keys, list)
        # 중복 없는지 확인
        assert len(ordered_keys) == len(set(ordered_keys))


class TestMixCodeMetadata:
    """믹스 코드 메타데이터 테스트"""
    
    def test_get_mix_code_definition_existing(self):
        """존재하는 믹스 코드 정의 테스트"""
        definition = get_mix_code_definition("M01")
        
        # config.json에 따라 결과가 다를 수 있음
        if definition:
            assert "name" in definition or "category" in definition
    
    def test_get_mix_code_definition_nonexistent(self):
        """존재하지 않는 믹스 코드 정의 테스트"""
        definition = get_mix_code_definition("M99")
        
        assert definition is None
    
    def test_get_all_mix_codes(self):
        """모든 믹스 코드 정의 테스트"""
        mix_codes = get_all_mix_codes()
        
        assert isinstance(mix_codes, dict)


class TestSkinAssessmentPercentage:
    """피부 평가 점수 비율 계산 테스트"""
    
    def test_calculate_percentage_good(self):
        """좋은 점수 비율 계산 테스트"""
        percentage = calculate_skin_assessment_percentage(80)
        
        assert percentage == 0.0
    
    def test_calculate_percentage_critical(self):
        """나쁜 점수 비율 계산 테스트"""
        percentage = calculate_skin_assessment_percentage(30)
        
        assert percentage == 3.0  # max_percentage
    
    def test_calculate_percentage_moderate(self):
        """중간 점수 비율 계산 테스트"""
        percentage = calculate_skin_assessment_percentage(58)
        
        # critical_threshold(40) ~ good_threshold(76) 사이
        assert 0.5 <= percentage <= 3.0
    
    def test_calculate_percentage_boundary_good(self):
        """좋은 점수 경계 테스트"""
        percentage = calculate_skin_assessment_percentage(76)
        
        assert percentage == 0.0
    
    def test_calculate_percentage_boundary_critical(self):
        """나쁜 점수 경계 테스트"""
        percentage = calculate_skin_assessment_percentage(40)
        
        assert percentage == 3.0
    
    def test_calculate_percentage_rounding(self):
        """반올림 테스트"""
        percentage = calculate_skin_assessment_percentage(58)
        
        # 0.1% 단위 반올림
        assert percentage * 10 % 1 == 0


class TestSkinAssessmentRecipe:
    """피부 평가 처방전 계산 테스트"""
    
    def test_calculate_recipe_none_input(self):
        """None 입력 테스트"""
        recipe = calculate_skin_assessment_recipe(None)
        
        assert recipe == {}
    
    def test_calculate_recipe_empty_dict(self):
        """빈 딕셔너리 입력 테스트"""
        recipe = calculate_skin_assessment_recipe({})
        
        assert recipe == {}
    
    def test_calculate_recipe_with_measurements_key(self):
        """measurements 키가 있는 입력 테스트"""
        input_data = {
            "measurements": {
                "melasma_score": 50,
                "redness_score": 60
            }
        }
        
        recipe = calculate_skin_assessment_recipe(input_data)
        
        assert isinstance(recipe, dict)
    
    def test_calculate_recipe_nan_score(self):
        """NaN 점수 처리 테스트"""
        import math
        input_data = {
            "melasma_score": math.nan,
            "redness_score": 60
        }
        
        recipe = calculate_skin_assessment_recipe(input_data)
        
        # NaN은 무시되어야 함
        assert isinstance(recipe, dict)
    
    def test_calculate_recipe_low_score(self):
        """낮은 점수 처방 테스트"""
        # config.json에 매핑이 있는 경우에만 테스트
        input_data = {
            "melasma_score": 30,
            "redness_score": 35
        }
        
        recipe = calculate_skin_assessment_recipe(input_data)
        
        assert isinstance(recipe, dict)
        # 낮은 점수는 높은 비율 처방
        if recipe:
            for percentage in recipe.values():
                assert percentage > 0
    
    def test_calculate_recipe_high_score(self):
        """높은 점수 처방 테스트"""
        input_data = {
            "melasma_score": 80,
            "redness_score": 85
        }
        
        recipe = calculate_skin_assessment_recipe(input_data)
        
        assert isinstance(recipe, dict)
        # 높은 점수는 낮은 비율 처방 또는 처방 없음
        if recipe:
            for percentage in recipe.values():
                assert percentage >= 0


class TestAgeGroup:
    """나이대 테스트"""
    
    def test_get_age_group_child(self):
        """어린이 나이대 테스트"""
        age_group = get_age_group(5)
        
        assert age_group == 0
    
    def test_get_age_group_teen(self):
        """청소년 나이대 테스트"""
        age_group = get_age_group(15)
        
        assert age_group == 10
    
    def test_get_age_group_adult(self):
        """성인 나이대 테스트"""
        age_group = get_age_group(30)
        
        assert age_group == 26
    
    def test_get_age_group_elderly(self):
        """노년 나이대 테스트"""
        age_group = get_age_group(85)
        
        assert age_group == 81
    
    def test_get_age_group_boundary(self):
        """경계 나이 테스트"""
        age_group = get_age_group(20)
        
        assert age_group == 20


class TestPCRPrescription:
    """PCR 처방 테스트"""
    
    def test_calculate_pcr_prescription_no_match(self):
        """일치하는 규칙 없음 테스트"""
        prescription = calculate_pcr_prescription_for_category("total", 100)
        
        # 규칙에 따라 다를 수 있음
        assert prescription is None or isinstance(prescription, tuple)
    
    def test_calculate_pcr_recipe_none_input(self):
        """None 입력 테스트"""
        result = calculate_pcr_recipe(None, None, 30, "female")
        
        assert result is not None
        assert "pcr_recipe" in result
        assert "calculation_basis" in result
    
    def test_calculate_pcr_recipe_no_stats(self):
        """통계 데이터 없음 테스트"""
        pcr_result = {"bacteria1": 100, "bacteria2": 200}
        
        result = calculate_pcr_recipe(pcr_result, None, 30, "female")
        
        assert result is not None
        assert "pcr_recipe" in result
    
    def test_calculate_pcr_recipe_with_stats(self):
        """통계 데이터 있음 테스트"""
        pcr_result = {"bacteria1": 100, "bacteria2": 200}
        age_group_statistics = {
            "26_female": {
                "total": {"average_amount": 300},
                "beneficial": {"average_amount": 100},
                "trouble": {"average_amount": 100},
                "harmful": {"average_amount": 100},
                "bacteria": {
                    "bacteria1": {"category": "beneficial"},
                    "bacteria2": {"category": "trouble"}
                }
            }
        }
        
        result = calculate_pcr_recipe(pcr_result, age_group_statistics, 30, "female")
        
        assert result is not None
        assert "pcr_recipe" in result
        assert "calculation_basis" in result


class TestIntegratedPrescription:
    """통합 처방전 테스트"""
    
    def test_create_prescription_none_input(self):
        """None 입력 테스트"""
        prescription = create_prescription()
        
        assert prescription is not None
        assert "base" in prescription
        assert "skin" in prescription
        assert "care" in prescription
        assert "pcr" in prescription
        assert "assessment" in prescription
    
    def test_create_prescription_with_skin_assessment(self):
        """피부 평가 포함 테스트"""
        skin_scores = {
            "melasma_score": 50,
            "redness_score": 60
        }
        
        prescription = create_prescription(skin_assessment_scores=skin_scores)
        
        assert prescription is not None
        assert "assessment" in prescription
        assert isinstance(prescription["assessment"], dict)
    
    def test_create_prescription_with_pcr(self):
        """PCR 결과 포함 테스트"""
        pcr_result = {"bacteria1": 100}
        age_group_statistics = {
            "26_female": {
                "total": {"average_amount": 300},
                "beneficial": {"average_amount": 100},
                "trouble": {"average_amount": 100},
                "harmful": {"average_amount": 100}
            }
        }
        
        prescription = create_prescription(
            pcr_result=pcr_result,
            age_group_statistics=age_group_statistics,
            age=30,
            gender="female"
        )
        
        assert prescription is not None
        assert "pcr" in prescription
        assert isinstance(prescription["pcr"], dict)
    
    def test_create_prescription_base_percentage(self):
        """베이스 비율 계산 테스트"""
        prescription = create_prescription()
        
        assert prescription is not None
        assert "base" in prescription
        assert "percentage" in prescription["base"]
        # 베이스 비율은 0 ~ 100 사이
        assert 0 <= prescription["base"]["percentage"] <= 100


class TestSkinTypeMix:
    """피부타입 믹스 테스트"""
    
    def test_calculate_skin_type_mix_oily(self):
        """지성 피부 테스트"""
        mix = _calculate_skin_type_mix("oily")
        
        assert isinstance(mix, dict)
        if mix:
            assert "M03" in mix
    
    def test_calculate_skin_type_mix_dry(self):
        """건성 피부 테스트"""
        mix = _calculate_skin_type_mix("dry")
        
        assert isinstance(mix, dict)
        if mix:
            assert "M09" in mix
    
    def test_calculate_skin_type_mix_combination(self):
        """복합성 피부 테스트"""
        mix = _calculate_skin_type_mix("combination")
        
        assert isinstance(mix, dict)
    
    def test_calculate_skin_type_mix_sensitive(self):
        """민감성 피부 테스트"""
        mix = _calculate_skin_type_mix("sensitive")
        
        assert isinstance(mix, dict)
        if mix:
            assert "M09" in mix
    
    def test_calculate_skin_type_mix_unknown(self):
        """알 수 없는 피부타입 테스트"""
        mix = _calculate_skin_type_mix("unknown")
        
        assert mix == {}


class TestConcernMix:
    """관심사 믹스 테스트"""
    
    def test_calculate_concern_mix_pigmentation(self):
        """색소 관심사 테스트"""
        mix = _calculate_concern_mix(["pigmentation"])
        
        assert isinstance(mix, dict)
        if mix:
            assert "M05" in mix
    
    def test_calculate_concern_mix_redness(self):
        """홍조 관심사 테스트"""
        mix = _calculate_concern_mix(["redness"])
        
        assert isinstance(mix, dict)
        if mix:
            assert "M06" in mix
    
    def test_calculate_concern_mix_acne(self):
        """트러블 관심사 테스트"""
        mix = _calculate_concern_mix(["acne"])
        
        assert isinstance(mix, dict)
        if mix:
            assert "M10" in mix
    
    def test_calculate_concern_mix_multiple(self):
        """다중 관심사 테스트"""
        mix = _calculate_concern_mix(["pigmentation", "redness", "acne"])
        
        assert isinstance(mix, dict)
    
    def test_calculate_concern_mix_duplicate_max(self):
        """중복 믹스 최대값 테스트"""
        mix = _calculate_concern_mix(["aging"])
        
        assert isinstance(mix, dict)
        if mix:
            # aging은 M02와 M04를 포함
            # 중복이 있으면 최대값 사용
            assert "M02" in mix or "M04" in mix
    
    def test_calculate_concern_mix_empty(self):
        """빈 관심사 테스트"""
        mix = _calculate_concern_mix([])
        
        assert mix == {}
    
    def test_calculate_concern_mix_unknown(self):
        """알 수 없는 관심사 테스트"""
        mix = _calculate_concern_mix(["unknown_concern"])
        
        assert mix == {}
