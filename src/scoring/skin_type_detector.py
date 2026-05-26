"""
피부 타입 자동 감지 모듈

Skin Type Auto-Detection Module
"""
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SkinTypeFeatures:
    """피부 타입 감지 특성"""
    # 지성 관련
    shine_score: float
    pore_size_score: float
    oiliness_score: float
    
    # 건성 관련
    dryness_score: float
    roughness_score: float
    hydration_score: float
    
    # 복합성 관련
    t_zone_oiliness: float
    u_zone_oiliness: float
    oiliness_imbalance: float
    
    # 민감성 관련
    redness_score: float
    inflammation_score: float
    capillary_visibility: float


@dataclass
class SkinTypeDetection:
    """피부 타입 감지 결과"""
    skin_types: List[str]
    primary_type: str
    secondary_type: Optional[str]
    confidence: float
    all_scores: Dict[str, float]
    features: Dict[str, float]
    zone_analysis: Optional[Dict[str, Any]] = None


class SkinTypeClassifier:
    """피부 타입 분류기"""
    
    def __init__(self):
        self.thresholds = {
            "oily": 0.4,
            "dry": 0.4,
            "combination": 0.35,
            "sensitive": 0.35
        }
    
    def classify(self, features: SkinTypeFeatures) -> SkinTypeDetection:
        """피부 타입 분류"""
        # 특성을 딕셔너리로 변환
        features_dict = {
            "shine_score": features.shine_score,
            "pore_size_score": features.pore_size_score,
            "oiliness_score": features.oiliness_score,
            "dryness_score": features.dryness_score,
            "roughness_score": features.roughness_score,
            "hydration_score": features.hydration_score,
            "t_zone_oiliness": features.t_zone_oiliness,
            "u_zone_oiliness": features.u_zone_oiliness,
            "oiliness_imbalance": features.oiliness_imbalance,
            "redness_score": features.redness_score,
            "inflammation_score": features.inflammation_score,
            "capillary_visibility": features.capillary_visibility,
        }
        
        # 각 타입별 점수 계산
        scores = self._calculate_scores(features_dict)
        
        # 최고 점수 타입 선택
        predicted_type = max(scores, key=scores.get)
        confidence = scores[predicted_type]
        
        # 신뢰도 낮으면 "unknown" 반환 (타입별 임계값 사용)
        threshold = self.thresholds.get(predicted_type, 0.5)
        if confidence < threshold:
            predicted_type = "unknown"
        
        # 다중 타입 확인
        skin_types, secondary_type = self._determine_multiple_types(scores, predicted_type)
        
        return SkinTypeDetection(
            skin_types=skin_types,
            primary_type=predicted_type,
            secondary_type=secondary_type,
            confidence=confidence,
            all_scores=scores,
            features=features_dict
        )
    
    def _calculate_scores(self, features: Dict[str, float]) -> Dict[str, float]:
        """각 타입별 점수 계산"""
        scores = {
            "oily": self._calculate_oily_score(features),
            "dry": self._calculate_dry_score(features),
            "combination": self._calculate_combination_score(features),
            "sensitive": self._calculate_sensitive_score(features)
        }
        
        # 정규화 (0 ~ 1)
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}
        
        return scores
    
    def _calculate_oily_score(self, features: Dict[str, float]) -> float:
        """지성 점수 계산"""
        score = (
            features["shine_score"] * 0.4 +
            features["pore_size_score"] * 0.3 +
            features["oiliness_score"] * 0.3
        )
        return score / 100.0
    
    def _calculate_dry_score(self, features: Dict[str, float]) -> float:
        """건성 점수 계산"""
        score = (
            features["dryness_score"] * 0.4 +
            features["roughness_score"] * 0.3 +
            (100 - features["hydration_score"]) * 0.3
        )
        return score / 100.0
    
    def _calculate_combination_score(self, features: Dict[str, float]) -> float:
        """복합성 점수 계산"""
        score = (
            features["oiliness_imbalance"] * 0.5 +
            (features["t_zone_oiliness"] - features["u_zone_oiliness"]) * 0.5
        )
        return max(0, min(1, score / 50.0))
    
    def _calculate_sensitive_score(self, features: Dict[str, float]) -> float:
        """민감성 점수 계산"""
        score = (
            features["redness_score"] * 0.4 +
            features["inflammation_score"] * 0.3 +
            features["capillary_visibility"] * 0.3
        )
        return score / 100.0
    
    def _determine_multiple_types(self, scores: Dict[str, float], primary_type: str) -> tuple:
        """다중 타입 결정"""
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        if len(sorted_scores) >= 2:
            second_type, second_confidence = sorted_scores[1]
            
            # 2위 타입도 신뢰도 높으면 다중 타입으로 반환
            if second_confidence > 0.4 and second_type != "unknown":
                return [primary_type, second_type], second_type
        
        return [primary_type], None


def extract_skin_type_features(analysis_result: Dict[str, Any]) -> SkinTypeFeatures:
    """피부 타입 감지를 위한 특성 추출"""
    measurements = analysis_result.get("measurements", {})
    
    # 기존 측정값에서 추출
    shine_score = measurements.get("shine_score", 50.0)
    pore_size_score = measurements.get("pore_size_score", 50.0)
    dryness_score = measurements.get("dryness_score", 50.0)
    roughness_score = measurements.get("roughness_score", 50.0)
    redness_score = measurements.get("redness_score", 50.0)
    
    # 파생 특성 계산
    oiliness_score = calculate_oiliness(measurements)
    hydration_score = calculate_hydration(measurements)
    inflammation_score = calculate_inflammation(measurements)
    capillary_visibility = calculate_capillary_visibility(measurements)
    
    # T존/U존 분석 (다중 뷰 분석 결과가 있는 경우)
    t_zone_oiliness, u_zone_oiliness, oiliness_imbalance = analyze_face_zones(
        analysis_result
    )
    
    return SkinTypeFeatures(
        shine_score=shine_score,
        pore_size_score=pore_size_score,
        oiliness_score=oiliness_score,
        dryness_score=dryness_score,
        roughness_score=roughness_score,
        hydration_score=hydration_score,
        t_zone_oiliness=t_zone_oiliness,
        u_zone_oiliness=u_zone_oiliness,
        oiliness_imbalance=oiliness_imbalance,
        redness_score=redness_score,
        inflammation_score=inflammation_score,
        capillary_visibility=capillary_visibility
    )


def calculate_oiliness(measurements: Dict[str, Any]) -> float:
    """유분도 계산"""
    # 광택, 모공 크기, 거칠기 기반
    shine = measurements.get("shine_score", 50.0)
    pore_size = measurements.get("pore_size_score", 50.0)
    roughness = measurements.get("roughness_score", 50.0)
    
    oiliness = (shine * 0.5 + pore_size * 0.3 + (100 - roughness) * 0.2)
    return max(0, min(100, oiliness))


def calculate_hydration(measurements: Dict[str, Any]) -> float:
    """수분도 계산"""
    # 건조도, 거칠기 역수 기반
    dryness = measurements.get("dryness_score", 50.0)
    roughness = measurements.get("roughness_score", 50.0)
    
    hydration = 100 - (dryness * 0.6 + roughness * 0.4)
    return max(0, min(100, hydration))


def calculate_inflammation(measurements: Dict[str, Any]) -> float:
    """염증도 계산"""
    # 여드름, 홍조 기반
    acne = measurements.get("acne_score", 50.0)
    redness = measurements.get("redness_score", 50.0)
    
    inflammation = (acne * 0.5 + redness * 0.5)
    return max(0, min(100, inflammation))


def calculate_capillary_visibility(measurements: Dict[str, Any]) -> float:
    """모세혈관 가시성 계산"""
    # 홍조, 염증후 홍반 기반
    redness = measurements.get("redness_score", 50.0)
    post_inflammatory_erythema = measurements.get("post_inflammatory_erythema_score", 50.0)
    
    capillary = (redness * 0.6 + post_inflammatory_erythema * 0.4)
    return max(0, min(100, capillary))


def analyze_face_zones(analysis_result: Dict[str, Any]) -> tuple:
    """얼굴 영역 분석 (T존/U존)"""
    # 다중 뷰 분석 결과가 있는 경우 측면 이미지에서 T존/U존 분석
    angle_results = analysis_result.get("angle_results", {})
    
    if angle_results:
        # 측면 이미지에서 T존/U존 유분도 추정
        left_result = angle_results.get("left", {}).get("measurements", {})
        right_result = angle_results.get("right", {}).get("measurements", {})
        
        # 측면 이미지의 광택/모공 점수를 T존으로 사용
        t_zone_oiliness = (
            (left_result.get("shine_score", 50.0) + 
             right_result.get("shine_score", 50.0)) / 2
        )
        
        # 정면 이미지의 광택/모공 점수를 U존으로 사용
        front_result = analysis_result.get("measurements", {})
        u_zone_oiliness = front_result.get("shine_score", 50.0)
    else:
        # 단일 이미지인 경우 균등 분배
        overall_oiliness = calculate_oiliness(analysis_result.get("measurements", {}))
        t_zone_oiliness = overall_oiliness * 1.2  # T존은 일반적으로 더 지성
        u_zone_oiliness = overall_oiliness * 0.8
    
    # 불균형 계산
    oiliness_imbalance = abs(t_zone_oiliness - u_zone_oiliness)
    
    return t_zone_oiliness, u_zone_oiliness, oiliness_imbalance


def detect_skin_type(analysis_result: Dict[str, Any]) -> SkinTypeDetection:
    """피부 타입 자동 감지 메인 함수"""
    try:
        # 특성 추출
        features = extract_skin_type_features(analysis_result)
        
        # 분류
        classifier = SkinTypeClassifier()
        detection = classifier.classify(features)
        
        # 존 분석 결과 추가
        t_zone, u_zone, imbalance = analyze_face_zones(analysis_result)
        detection.zone_analysis = {
            "t_zone": {
                "oiliness": t_zone,
                "pore_size": features.pore_size_score,
                "shine": features.shine_score
            },
            "u_zone": {
                "oiliness": u_zone,
                "pore_size": features.pore_size_score * 0.8,
                "shine": features.shine_score * 0.8
            }
        }
        
        log.info(f"피부 타입 감지 완료: {detection.skin_types} (신뢰도: {detection.confidence:.2f})")
        
        return detection
        
    except Exception as e:
        log.error(f"피부 타입 감지 실패: {e}", exc_info=True)
        # 실패 시 기본값 반환
        return SkinTypeDetection(
            skin_types=["unknown"],
            primary_type="unknown",
            secondary_type=None,
            confidence=0.0,
            all_scores={"unknown": 0.0},
            features={}
        )


def get_skin_type_name(skin_type: str) -> str:
    """피부 타입 한글명 반환"""
    type_names = {
        "oily": "지성",
        "dry": "건성",
        "combination": "복합성",
        "sensitive": "민감성",
        "unknown": "알 수 없음"
    }
    return type_names.get(skin_type, skin_type)
