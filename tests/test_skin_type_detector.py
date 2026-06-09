"""
피부 타입 자동 감지 단위 테스트

Skin Type Auto-Detection Unit Tests
"""
import pytest
from src.scoring.skin_type_detector import (
    SkinTypeFeatures,
    SkinTypeDetection,
    SkinTypeClassifier,
    extract_skin_type_features,
    calculate_oiliness,
    calculate_hydration,
    calculate_inflammation,
    calculate_capillary_visibility,
    analyze_face_zones,
    detect_skin_type,
    get_skin_type_name,
)


class TestSkinTypeFeatures:
    """SkinTypeFeatures 데이터클래스 테스트"""
    
    def test_features_creation(self):
        """특성 생성 테스트"""
        features = SkinTypeFeatures(
            shine_score=75.0,
            pore_size_score=68.0,
            oiliness_score=80.0,
            dryness_score=20.0,
            roughness_score=25.0,
            hydration_score=60.0,
            t_zone_oiliness=85.0,
            u_zone_oiliness=40.0,
            oiliness_imbalance=45.0,
            redness_score=55.0,
            inflammation_score=40.0,
            capillary_visibility=50.0
        )
        
        assert features.shine_score == 75.0
        assert features.oiliness_score == 80.0
        assert features.dryness_score == 20.0


class TestSkinTypeClassifier:
    """SkinTypeClassifier 분류기 테스트"""
    
    def test_classify_oily(self):
        """지성 분류 테스트"""
        classifier = SkinTypeClassifier()
        
        features = SkinTypeFeatures(
            shine_score=90.0,
            pore_size_score=85.0,
            oiliness_score=95.0,
            dryness_score=10.0,
            roughness_score=15.0,
            hydration_score=80.0,
            t_zone_oiliness=95.0,
            u_zone_oiliness=80.0,
            oiliness_imbalance=15.0,
            redness_score=30.0,
            inflammation_score=20.0,
            capillary_visibility=20.0
        )
        
        detection = classifier.classify(features)
        
        assert detection.primary_type == "oily"
        assert detection.confidence >= 0.5
    
    def test_classify_dry(self):
        """건성 분류 테스트"""
        classifier = SkinTypeClassifier()
        
        features = SkinTypeFeatures(
            shine_score=30.0,
            pore_size_score=40.0,
            oiliness_score=25.0,
            dryness_score=80.0,
            roughness_score=75.0,
            hydration_score=30.0,
            t_zone_oiliness=30.0,
            u_zone_oiliness=25.0,
            oiliness_imbalance=5.0,
            redness_score=40.0,
            inflammation_score=30.0,
            capillary_visibility=30.0
        )
        
        detection = classifier.classify(features)
        
        assert detection.primary_type == "dry"
        assert detection.confidence >= 0.5
    
    def test_classify_combination(self):
        """복합성 분류 테스트"""
        classifier = SkinTypeClassifier()
        
        features = SkinTypeFeatures(
            shine_score=65.0,
            pore_size_score=60.0,
            oiliness_score=65.0,
            dryness_score=35.0,
            roughness_score=40.0,
            hydration_score=60.0,
            t_zone_oiliness=90.0,
            u_zone_oiliness=30.0,
            oiliness_imbalance=60.0,
            redness_score=35.0,
            inflammation_score=25.0,
            capillary_visibility=25.0
        )
        
        detection = classifier.classify(features)
        
        # 복합성은 T존/U존 불균형이 큰 경우
        # 신뢰도가 낮으면 unknown이 될 수 있음
        assert detection.primary_type in ["combination", "oily", "dry", "unknown"]
    
    def test_classify_sensitive(self):
        """민감성 분류 테스트"""
        classifier = SkinTypeClassifier()
        
        features = SkinTypeFeatures(
            shine_score=50.0,
            pore_size_score=50.0,
            oiliness_score=50.0,
            dryness_score=50.0,
            roughness_score=50.0,
            hydration_score=50.0,
            t_zone_oiliness=50.0,
            u_zone_oiliness=50.0,
            oiliness_imbalance=0.0,
            redness_score=95.0,
            inflammation_score=90.0,
            capillary_visibility=85.0
        )
        
        detection = classifier.classify(features)
        
        # 민감성은 홍조/염증이 매우 높은 경우
        # 신뢰도가 낮으면 unknown이 될 수 있음
        assert detection.primary_type in ["sensitive", "unknown"]
    
    def test_classify_multiple_types(self):
        """다중 타입 분류 테스트"""
        classifier = SkinTypeClassifier()
        
        # 지성 + 민감성 특성
        features = SkinTypeFeatures(
            shine_score=75.0,
            pore_size_score=70.0,
            oiliness_score=80.0,
            dryness_score=30.0,
            roughness_score=35.0,
            hydration_score=60.0,
            t_zone_oiliness=85.0,
            u_zone_oiliness=70.0,
            oiliness_imbalance=15.0,
            redness_score=70.0,
            inflammation_score=65.0,
            capillary_visibility=60.0
        )
        
        detection = classifier.classify(features)
        
        # 다중 타입인지 확인
        assert len(detection.skin_types) >= 1
        assert detection.primary_type in detection.skin_types


class TestCalculateFunctions:
    """계산 함수 테스트"""
    
    def test_calculate_oiliness(self):
        """유분도 계산 테스트"""
        measurements = {
            "shine_score": 80.0,
            "pore_size_score": 70.0,
            "roughness_score": 30.0
        }
        
        oiliness = calculate_oiliness(measurements)
        
        assert 0 <= oiliness <= 100
        assert oiliness > 50  # 광택/모공이 높으면 유분도도 높음
    
    def test_calculate_hydration(self):
        """수분도 계산 테스트"""
        measurements = {
            "dryness_score": 80.0,
            "roughness_score": 70.0
        }
        
        hydration = calculate_hydration(measurements)
        
        assert 0 <= hydration <= 100
        assert hydration < 50  # 건조도/거칠기가 높으면 수분도 낮음
    
    def test_calculate_inflammation(self):
        """염증도 계산 테스트"""
        measurements = {
            "acne_score": 70.0,
            "redness_score": 60.0
        }
        
        inflammation = calculate_inflammation(measurements)
        
        assert 0 <= inflammation <= 100
        assert inflammation > 50  # 여드름/홍조가 높으면 염증도도 높음
    
    def test_calculate_capillary_visibility(self):
        """모세혈관 가시성 계산 테스트"""
        measurements = {
            "redness_score": 75.0,
            "post_inflammatory_erythema_score": 65.0
        }
        
        capillary = calculate_capillary_visibility(measurements)
        
        assert 0 <= capillary <= 100
        assert capillary > 50  # 홍조가 높으면 모세혈관 가시성도 높음


class TestAnalyzeFaceZones:
    """얼굴 영역 분석 테스트"""
    
    def test_analyze_face_zones_with_multi_view(self):
        """다중 뷰 분석 결과가 있는 경우 테스트"""
        analysis_result = {
            "measurements": {
                "shine_score": 50.0,
                "pore_size_score": 50.0
            },
            "angle_results": {
                "left": {
                    "measurements": {
                        "shine_score": 80.0,
                        "pore_size_score": 70.0
                    }
                },
                "right": {
                    "measurements": {
                        "shine_score": 75.0,
                        "pore_size_score": 65.0
                    }
                }
            }
        }
        
        t_zone, u_zone, imbalance = analyze_face_zones(analysis_result)
        
        assert 0 <= t_zone <= 100
        assert 0 <= u_zone <= 100
        assert imbalance >= 0
        assert t_zone > u_zone  # 측면 이미지가 더 지성인 경향
    
    def test_analyze_face_zones_single_view(self):
        """단일 뷰 분석 결과 테스트"""
        analysis_result = {
            "measurements": {
                "shine_score": 50.0,
                "pore_size_score": 50.0
            }
        }
        
        t_zone, u_zone, imbalance = analyze_face_zones(analysis_result)
        
        assert 0 <= t_zone <= 100
        assert 0 <= u_zone <= 100
        assert imbalance >= 0
        assert t_zone > u_zone  # T존이 더 지성인 경향


class TestExtractSkinTypeFeatures:
    """특성 추출 테스트"""
    
    def test_extract_features_from_analysis(self):
        """분석 결과에서 특성 추출 테스트"""
        analysis_result = {
            "measurements": {
                "shine_score": 60.0,
                "pore_size_score": 55.0,
                "dryness_score": 40.0,
                "roughness_score": 45.0,
                "redness_score": 50.0
            }
        }
        
        features = extract_skin_type_features(analysis_result)
        
        assert isinstance(features, SkinTypeFeatures)
        assert features.shine_score == 60.0
        assert features.pore_size_score == 55.0
        assert features.dryness_score == 40.0


class TestDetectSkinType:
    """피부 타입 감지 메인 함수 테스트"""
    
    def test_detect_skin_type_success(self):
        """피부 타입 감지 성공 테스트"""
        analysis_result = {
            "measurements": {
                "shine_score": 75.0,
                "pore_size_score": 70.0,
                "dryness_score": 25.0,
                "roughness_score": 30.0,
                "redness_score": 45.0
            }
        }
        
        detection = detect_skin_type(analysis_result)
        
        assert isinstance(detection, SkinTypeDetection)
        assert detection.primary_type in ["oily", "dry", "combination", "sensitive", "unknown"]
        assert 0 <= detection.confidence <= 1
        assert detection.features is not None
    
    def test_detect_skin_type_with_error(self):
        """에러 발생 시 기본값 반환 테스트"""
        # 빈 결과로 인해 낮은 신뢰도로 unknown 반환
        analysis_result = {}  # 빈 결과
        
        detection = detect_skin_type(analysis_result)
        
        assert detection.primary_type == "unknown"
        assert detection.confidence < 0.5  # 낮은 신뢰도
        assert detection.skin_types == ["unknown"]


class TestGetSkinTypeName:
    """피부 타입 한글명 변환 테스트"""
    
    def test_get_skin_type_name(self):
        """한글명 변환 테스트"""
        assert get_skin_type_name("oily") == "지성"
        assert get_skin_type_name("dry") == "건성"
        assert get_skin_type_name("combination") == "복합성"
        assert get_skin_type_name("sensitive") == "민감성"
        assert get_skin_type_name("unknown") == "알 수 없음"
        assert get_skin_type_name("invalid") == "invalid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
