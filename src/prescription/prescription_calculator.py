"""
prescription.prescription_calculator
====================================
피부 평가 점수 및 PCR 결과 기반 처방전 계산 모듈.

[REFACTOR 2026-05-22] 처방전 로직 중앙화.
- SKIN_ASSESSMENT_PRESCRIPTION.md: 피부 평가 점수 기반 처방
- PRESCRIPTION_CALCULATION.md: PCR 결과 기반 처방
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  설정 로드
# ═══════════════════════════════════════════════════════════════

def _load_prescription_config() -> Dict[str, Any]:
    """config.json에서 처방전 설정을 로드합니다.
    
    Returns:
        처방전 설정 딕셔너리
    """
    try:
        from src.scoring.config._config import _load_scoring_config
        config = _load_scoring_config()
        if config and "prescription" in config:
            return config["prescription"]
    except Exception as e:
        log.warning(f"처방전 설정 로드 실패: {e}")
    
    # 기본값 반환
    return {
        "enabled": False,
        "skin_assessment": {
            "good_threshold": 76,
            "critical_threshold": 40,
            "max_percentage": 3.0,
            "min_percentage": 0.5,  # 문서 기준: 최소 0.5%
        },
        "age_group_mapping": [
            {"min_age": 0, "max_age": 9, "group": 0},
            {"min_age": 10, "max_age": 19, "group": 10},
            {"min_age": 20, "max_age": 25, "group": 20},
            {"min_age": 26, "max_age": 30, "group": 26},
            {"min_age": 31, "max_age": 35, "group": 31},
            {"min_age": 36, "max_age": 40, "group": 36},
            {"min_age": 41, "max_age": 45, "group": 41},
            {"min_age": 46, "max_age": 50, "group": 46},
            {"min_age": 51, "max_age": 55, "group": 51},
            {"min_age": 56, "max_age": 60, "group": 56},
            {"min_age": 61, "max_age": 65, "group": 61},
            {"min_age": 66, "max_age": 70, "group": 66},
            {"min_age": 71, "max_age": 75, "group": 71},
            {"min_age": 76, "max_age": 80, "group": 76},
            {"min_age": 81, "max_age": 999, "group": 81}
        ],
        "pcr": {
            "total_rules": [],
            "beneficial_rules": [],
            "trouble_rules": [],
            "harmful_rules": [],
        }
    }


# ═══════════════════════════════════════════════════════════════
#  피부 평가 점수 기반 처방 (Skin Assessment Prescription)
# ═══════════════════════════════════════════════════════════════

# [REFACTOR 2026-05-23] 믹스 코드 매핑을 config.json에서 동적으로 로드하도록 변경
# 향후 믹스 코드 추가/변경/삭제 시 config.json만 수정하면 됨


def _get_measurement_to_mix_code_mapping() -> Dict[str, str]:
    """config.json에서 측정항목 → 믹스 코드 매핑을 로드합니다.

    [REFACTOR 2026-05-23] 하드코딩된 기본값 제거. config.json에만 의존.
    향후 믹스 코드 추가/변경/삭제 시 config.json의 measurement_to_mix_code_mapping만 수정.

    Returns:
        {measurement_key: mix_code}
    """
    config = _load_prescription_config()
    mapping = config.get("measurement_to_mix_code_mapping", {})

    if not mapping:
        log.warning("config.json에 measurement_to_mix_code_mapping이 없습니다. 빈 매핑을 반환합니다.")

    return mapping


def get_measurement_metadata(measurement_key: str) -> Optional[Dict[str, Any]]:
    """config.json에서 측정항목 메타데이터를 로드합니다.

    [REFACTOR 2026-05-24] 측정항목 메타데이터를 동적으로 로드.
    향후 측정항목 추가/변경/삭제 시 config.json의 measurements 섹션만 수정.

    Args:
        measurement_key: 측정항목 키 (예: melasma_score, redness_score)

    Returns:
        {name_ko, name_en, category, description} 또는 None
    """
    config = _load_prescription_config()
    measurements = config.get("measurements", {})

    return measurements.get(measurement_key)


def get_all_measurements() -> Dict[str, Dict[str, Any]]:
    """config.json에서 모든 측정항목 메타데이터를 로드합니다.

    [REFACTOR 2026-05-24] 측정항목 메타데이터를 동적으로 로드.
    향후 측정항목 추가/변경/삭제 시 config.json의 measurements 섹션만 수정.

    Returns:
        {measurement_key: {name_ko, name_en, category, description}}
    """
    config = _load_prescription_config()
    return config.get("measurements", {})


def get_category_metadata(category_key: str) -> Optional[Dict[str, Any]]:
    """config.json에서 카테고리 메타데이터를 로드합니다.

    [REFACTOR 2026-05-24] 카테고리 메타데이터를 동적으로 로드.
    향후 카테고리 추가/변경/삭제 시 config.json의 categories 섹션만 수정.

    Args:
        category_key: 카테고리 키 (예: pigmentation, wrinkle, redness)

    Returns:
        {name_ko, name_en, description, measurements, mix_codes, orthogonal_categories} 또는 None
    """
    config = _load_prescription_config()
    categories = config.get("categories", {})

    return categories.get(category_key)


def get_all_categories() -> Dict[str, Dict[str, Any]]:
    """config.json에서 모든 카테고리 메타데이터를 로드합니다.

    [REFACTOR 2026-05-24] 카테고리 메타데이터를 동적으로 로드.
    향후 카테고리 추가/변경/삭제 시 config.json의 categories 섹션만 수정.

    Returns:
        {category_key: {name_ko, name_en, description, measurements, mix_codes, orthogonal_categories}}
    """
    config = _load_prescription_config()
    return config.get("categories", {})


def get_measurements_by_category(category_key: str) -> List[str]:
    """카테고리에 속한 측정항목 목록을 반환합니다.

    [REFACTOR 2026-05-24] 카테고리 기반 측정항목 필터링.

    Args:
        category_key: 카테고리 키 (예: pigmentation, wrinkle)

    Returns:
        측정항목 키 목록
    """
    category_meta = get_category_metadata(category_key)
    if not category_meta:
        return []

    return category_meta.get("measurements", [])


def get_measurement_display_names() -> Dict[str, str]:
    """모든 측정항목의 디스플레이 이름을 반환합니다.

    [REFACTOR 2026-05-24] GUI 테이블 동적 생성용. 측정항목 키 → 한글명 매핑.

    Returns:
        {measurement_key: name_ko}
    """
    measurements = get_all_measurements()
    return {key: data.get("name_ko", key) for key, data in measurements.items() if not key.startswith("_")}


def get_ordered_measurement_keys() -> List[str]:
    """카테고리 순서대로 정렬된 측정항목 키 목록을 반환합니다.

    [REFACTOR 2026-05-24] GUI 테이블 동적 생성용. 카테고리별로 그룹화된 순서.

    Returns:
        정렬된 측정항목 키 목록
    """
    categories = get_all_categories()
    ordered_keys = []

    # 카테고리 순서대로 측정항목 수집
    category_order = ["pigmentation", "redness", "acne", "pore", "wrinkle", "texture", "tone", "elasticity", "skin_type"]

    for category_key in category_order:
        if category_key in categories:
            measurements = categories[category_key].get("measurements", [])
            ordered_keys.extend(measurements)

    return ordered_keys


def get_mix_code_definition(mix_code: str) -> Optional[Dict[str, Any]]:
    """config.json에서 믹스 코드 정의를 로드합니다.
    
    [REFACTOR 2026-05-23] 믹스 코드 정보를 동적으로 로드.
    향후 믹스 코드 추가/변경/삭제 시 config.json의 mix_codes만 수정.
    
    Args:
        mix_code: 믹스 코드 (예: M01, M02)
    
    Returns:
        {name, category, description, ingredients, status} 또는 None
    """
    config = _load_prescription_config()
    mix_codes = config.get("mix_codes", {})
    return mix_codes.get(mix_code)


def get_all_mix_codes() -> Dict[str, Dict[str, Any]]:
    """config.json에서 모든 믹스 코드 정의를 로드합니다.
    
    [REFACTOR 2026-05-23] 모든 믹스 코드 정보를 동적으로 로드.
    
    Returns:
        {mix_code: {name, category, description, ingredients, status}}
    """
    config = _load_prescription_config()
    return config.get("mix_codes", {})


def _attach_mix_names(recipe: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    """숫자 형식 처방전을 이름 포함 신 형식으로 변환합니다.

    [REFACTOR 2026-06-08] 믹스 코드 한글 이름을 처방전 객체에 직접 포함(SSOT).
    이렇게 하면 보고서 렌더러(GUI/HTML/Excel/CLI)가 config를 다시 조회할 필요가 없습니다.

    Args:
        recipe: {mix_code: percentage} 형식의 처방전

    Returns:
        {mix_code: {"percentage": percentage, "name": 한글이름}} 형식.
        이름이 config에 없으면 믹스 코드 자체를 이름으로 사용합니다.
    """
    mix_codes_info = get_all_mix_codes()
    enriched: Dict[str, Dict[str, Any]] = {}
    for mix_code, percentage in recipe.items():
        name = mix_codes_info.get(mix_code, {}).get("name", mix_code)
        enriched[mix_code] = {"percentage": percentage, "name": name}
    return enriched


def calculate_skin_assessment_percentage(score: float) -> float:
    """피부 평가 점수를 처방 비율로 변환합니다.
    
    변환 규칙:
    - good_threshold 이상 (Good): 0%
    - critical_threshold ~ good_threshold (Moderate): min_percentage ~ max_percentage (선형 계산)
    - critical_threshold 미만 (Critical): max_percentage
    
    선형 계산 공식:
    percentage = max_percentage - ((score - critical_threshold) * (max_percentage - min_percentage) / (good_threshold - critical_threshold))
    
    Args:
        score: 피부 평가 점수 (0-100)
    
    Returns:
        처방 비율 (0.0 ~ max_percentage, 0.1% 단위 반올림)
    """
    config = _load_prescription_config()
    skin_config = config.get("skin_assessment", {})
    
    good_threshold = skin_config.get("good_threshold", 76)
    critical_threshold = skin_config.get("critical_threshold", 40)
    max_percentage = skin_config.get("max_percentage", 3.0)
    min_percentage = skin_config.get("min_percentage", 0.5)  # 문서 기준: 최소 0.5%
    
    if score >= good_threshold:
        return 0.0
    elif score <= critical_threshold:
        return max_percentage
    else:
        # 선형 계산
        percentage = max_percentage - ((score - critical_threshold) * (max_percentage - min_percentage) / (good_threshold - critical_threshold))
        # 범위 제한
        percentage = max(min_percentage, min(max_percentage, percentage))
        # 0.1% 단위 반올림
        return round(percentage * 10) / 10


def calculate_skin_assessment_recipe(
    skin_assessment_scores: Optional[Dict[str, float]]
) -> Dict[str, float]:
    """측정항목 점수를 기반으로 처방전을 계산합니다.

    [REFACTOR 2026-05-23] 측정항목 → 믹스 코드 직접 매핑 적용.
    문서 기준: SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md 믹스 코드 매핑
    매핑된 측정항목 중 가장 낮은 점수를 기준으로 처방 비율 결정.

    Args:
        skin_assessment_scores: 측정항목 점수 객체 (0-100점)

    Returns:
        {mix_code: percentage} 형식의 처방전
    """
    if not skin_assessment_scores or not isinstance(skin_assessment_scores, dict):
        return {}
    
    # measurements 키가 있으면 실제 측정항목 점수 추출
    if 'measurements' in skin_assessment_scores:
        skin_assessment_scores = skin_assessment_scores['measurements']
    
    # config.json에서 매핑 로드
    measurement_mapping = _get_measurement_to_mix_code_mapping()
    
    log.info(f"[처방전] 측정항목 점수: {skin_assessment_scores}")
    log.info(f"[처방전] 매핑: {measurement_mapping}")
    
    # 믹스 코드별로 매핑된 측정항목 점수 수집
    mix_code_scores: Dict[str, List[float]] = {}
    
    for measurement_key, mix_code in measurement_mapping.items():
        score = skin_assessment_scores.get(measurement_key)
        
        # 점수 유효성 검증
        if score is None or score != score:  # NaN 체크
            continue
        
        if mix_code not in mix_code_scores:
            mix_code_scores[mix_code] = []
        mix_code_scores[mix_code].append(score)
    
    log.debug(f"[처방전] 믹스 코드별 점수: {mix_code_scores}")
    
    # 믹스 코드별로 가장 낮은 점수 기준으로 처방 비율 계산
    recipe: Dict[str, float] = {}
    
    for mix_code, scores in mix_code_scores.items():
        if not scores:
            continue
        
        # 가장 낮은 점수 선택 (가장 취약한 부분 기준)
        min_score = min(scores)
        
        # 처방 비율 계산
        percentage = calculate_skin_assessment_percentage(min_score)
        
        log.debug(f"[처방전] {mix_code}: min_score={min_score}, percentage={percentage}")
        
        # 비율이 0보다 크면 처방에 추가
        if percentage > 0:
            recipe[mix_code] = percentage
    
    log.info(f"[처방전] 최종 처방전: {recipe}")
    return recipe


# ═══════════════════════════════════════════════════════════════
#  PCR 결과 기반 처방 (PCR Prescription)
# ═══════════════════════════════════════════════════════════════

# 나이대 매핑 로드 함수
def _get_age_group_mapping() -> List[Tuple[int, int, int]]:
    """config.json에서 나이대 매핑을 로드합니다.
    
    [FIX P3-26] 하드코딩된 AGE_GROUP_MAPPING을 config.json에서 로드하도록 변경.
    
    Returns:
        나이대 매핑 리스트 [(min_age, max_age, group), ...]
    """
    config = _load_prescription_config()
    mapping = config.get("age_group_mapping", [])
    
    # config 형식에서 튜플 형식으로 변환
    return [(m["min_age"], m["max_age"], m["group"]) for m in mapping]


def get_age_group(age: int) -> int:
    """나이를 나이대로 변환합니다.
    
    [FIX P3-26] config.json에서 로드한 나이대 매핑을 사용합니다.
    
    Args:
        age: 나이
    
    Returns:
        나이대 코드
    """
    age_mapping = _get_age_group_mapping()
    for min_age, max_age, group in age_mapping:
        if min_age <= age <= max_age:
            return group
    return 81  # 기본값


# PCR 처방 규칙 (기본값 - config.json 로드 실패 시 사용)
PCR_PRESCRIPTION_RULES_DEFAULT: Dict[str, List[Tuple[float, float, Optional[str], float]]] = {
    "total": [
        (float('-inf'), 0, None, 0.0),
        (0, -10, "M11", 1.5),
        (-10, -20, "M11", 2.0),
        (-20, -30, "PM04", 2.5),
        (-30, float('-inf'), "PM04", 3.0),
    ],
    "beneficial": [
        (float('-inf'), 0, None, 0.0),
        (0, -10, "PM01", 1.5),
        (-10, -20, "PM01", 2.0),
        (-20, -30, "PM05", 2.5),
        (-30, float('-inf'), "PM05", 3.0),
    ],
    "trouble": [
        (float('-inf'), 0, None, 0.0),
        (0, 10, "PM02", 1.5),
        (10, 20, "PM02", 2.0),
        (20, 30, "PM06", 2.5),
        (30, float('inf'), "PM06", 3.0),
    ],
    "harmful": [
        (float('-inf'), 0, None, 0.0),
        (0, 10, "PM03", 1.5),
        (10, 20, "PM03", 2.0),
        (20, 30, "PM07", 2.5),
        (30, float('inf'), "PM07", 3.0),
    ],
}


def _get_pcr_prescription_rules() -> Dict[str, List[Tuple[float, float, Optional[str], float]]]:
    """config.json에서 PCR 처방 규칙을 로드합니다.
    
    Returns:
        {category: [(rv_min, rv_max, mix_code, percentage)]}
    """
    config = _load_prescription_config()
    pcr_config = config.get("pcr", {})
    
    rules: Dict[str, List[Tuple[float, float, Optional[str], float]]] = {}
    
    for category in ["total", "beneficial", "trouble", "harmful"]:
        rules_key = f"{category}_rules"
        config_rules = pcr_config.get(rules_key, [])
        
        if config_rules:
            # config.json에서 로드
            parsed_rules = []
            for rule in config_rules:
                rv_min = rule.get("rv_min", 0)
                rv_max = rule.get("rv_max", 0)
                mix_code = rule.get("mix_code")
                percentage = rule.get("percentage", 0.0)
                parsed_rules.append((rv_min, rv_max, mix_code, percentage))
            rules[category] = parsed_rules
        else:
            # 기본값 사용
            rules[category] = PCR_PRESCRIPTION_RULES_DEFAULT.get(category, [])
    
    return rules


def calculate_pcr_prescription_for_category(
    category: str,
    rv: float
) -> Optional[Tuple[str, float]]:
    """카테고리별 rV 값에 따른 처방을 결정합니다.
    
    Args:
        category: 카테고리 (total, beneficial, trouble, harmful)
        rv: 차이값 (cV - aV)
    
    Returns:
        (mix_code, percentage) 또는 None (처방 없음)
    """
    rules = _get_pcr_prescription_rules().get(category, [])
    
    for rv_min, rv_max, mix_code, percentage in rules:
        # config.json 기준: rv_min <= rv < rv_max 범위
        if rv_min <= rv < rv_max:
            return (mix_code, percentage) if mix_code else None
    
    return None


def calculate_pcr_recipe(
    pcr_result: Optional[Dict[str, float]],
    age_group_statistics: Optional[Dict[str, Dict[str, float]]],
    age: int,
    gender: str
) -> Dict[str, Any]:
    """PCR 결과를 기반으로 처방전을 계산합니다.
    
    Args:
        pcr_result: PCR 결과 (미생물 코드 → 함량)
        age_group_statistics: 나이대별 통계 데이터
        age: 나이
        gender: 성별
    
    Returns:
        {
            pcr_recipe: {pcr: {mix_code: percentage}},
            calculation_basis: {category: {cV, aV, rV, prescription}}
        }
    """
    if not pcr_result or not age_group_statistics:
        return {
            "pcr_recipe": {"pcr": {}},
            "calculation_basis": {}
        }
    
    age_group = get_age_group(age)
    stats_key = f"{age_group}_{gender}"
    stats = age_group_statistics.get(stats_key, {})
    
    if not stats:
        log.warning(f"나이대별 통계 데이터 없음: {stats_key}")
        return {
            "pcr_recipe": {"pcr": {}},
            "calculation_basis": {}
        }
    
    # 측정 총량 계산
    measured_total = sum(pcr_result.values())
    average_total = stats.get("total", {}).get("average_amount", 1)
    
    # cV (current Volume) 계산: 현재 측정된 총량 / 평균 총량 * 100
    # - 측정된 세균 총량이 평균보다 얼마나 많은지를 백분율로 표현
    cv_total = (measured_total / average_total) * 100 if average_total > 0 else 0
    
    # aV (average Volume) 계산: 카테고리 평균 총량 / 전체 평균 총량 * 100
    # - 전체 평균을 기준(100)으로 설정하여 상대적 비교
    # [FIX P1-8] 실제 평균 총량 사용
    av_total = (average_total / average_total) * 100 if average_total > 0 else 100
    
    # rV (relative Volume) 계산: cV - aV
    # - 평균 대비 상대적 차이 (양수: 평균보다 많음, 음수: 평균보다 적음)
    rv_total = cv_total - av_total
    
    # 처방 결정
    prescription_total = calculate_pcr_prescription_for_category("total", rv_total)
    
    # 카테고리별 계산
    categories = ["beneficial", "trouble", "harmful"]
    calculation_basis: Dict[str, Dict[str, Any]] = {
        "total": {
            "cV": cv_total,
            "aV": av_total,
            "rV": rv_total,
            "prescription": prescription_total
        }
    }
    
    pcr_recipe: Dict[str, float] = {}
    
    if prescription_total:
        pcr_recipe[prescription_total[0]] = prescription_total[1]
    
    for category in categories:
        # 카테고리 함량 계산
        category_amount = sum(
            amount for code, amount in pcr_result.items()
            if stats.get("bacteria", {}).get(code, {}).get("category") == category
        )
        
        # cV (current Volume) 계산: 카테고리 측정량 / 전체 측정량 * 100
        # - 해당 카테고리가 전체 측정량에서 차지하는 비율
        cv_category = (category_amount / measured_total) * 100 if measured_total > 0 else 0
        
        # aV (average Volume) 계산: 카테고리 평균량 / 전체 평균량 * 100
        # - 해당 카테고리의 평균 비율 (전체 평균 대비)
        category_average = stats.get(category, {}).get("average_amount", 0)
        av_category = (category_average / average_total) * 100 if average_total > 0 else 0
        
        # rV (relative Volume) 계산: cV - aV
        # - 평균 비율 대비 현재 비율의 차이
        rv_category = cv_category - av_category
        
        # 처방 결정
        prescription = calculate_pcr_prescription_for_category(category, rv_category)
        
        calculation_basis[category] = {
            "cV": cv_category,
            "aV": av_category,
            "rV": rv_category,
            "prescription": prescription
        }
        
        if prescription:
            pcr_recipe[prescription[0]] = prescription[1]
    
    return {
        "pcr_recipe": {
            "base": {},
            "skin": {},
            "care": {},
            "pcr": pcr_recipe,
            "assessment": {}
        },
        "calculation_basis": calculation_basis
    }


# ═══════════════════════════════════════════════════════════════
#  통합 처방전 생성
# ═══════════════════════════════════════════════════════════════

def create_prescription(
    skin_assessment_scores: Optional[Dict[str, float]] = None,
    pcr_result: Optional[Dict[str, float]] = None,
    age_group_statistics: Optional[Dict[str, Dict[str, float]]] = None,
    age: int = 30,
    gender: str = "female",
    skin_type: Optional[str] = None,  # 향후 설문 연동용
    concerns: Optional[List[str]] = None  # 향후 설문 연동용
) -> Dict[str, Any]:
    """피부 평가 점수와 PCR 결과를 기반으로 통합 처방전을 생성합니다.

    문서 흐름도 기준:
    - 1단계: 설문 조사 (피부타입별 믹스, 관심별 믹스) - 향후 구현 예정
    - 2단계: 피부 분석 (M01-M10 믹스)
    - 3단계: 마이크로바이옴 분석 (PCR 믹스)
    - 4단계: 베이스 비율 계산 (100 - 총믹스합)

    향후 설문 연동 구현 가이드:
    - skin_type 파라미터: "oily", "dry", "combination", "sensitive" 중 하나
    - concerns 파라미터: ["pigmentation", "redness", "pore", "wrinkle", "texture", "tone", "elasticity", "aging", "acne"] 중 복수 선택
    - skin_type별 믹스 매핑: config.json의 measurement_to_mix_code_mapping 참조
    - concerns별 믹스 매핑: config.json의 measurement_to_mix_code_mapping 참조
    - 구현 시 skin, care 딕셔너리를 채우고 assessment_recipe와 합산

    Args:
        skin_assessment_scores: 피부 평가 점수
        pcr_result: PCR 결과
        age_group_statistics: 나이대별 통계 데이터
        age: 나이
        gender: 성별
        skin_type: 피부 타입 (향후 설문 연동용)
        concerns: 관심사 목록 (향후 설문 연동용)

    Returns:
        {
            base: {"percentage": 베이스 비율},
            skin: {mix_code: {"percentage": pct, "name": 한글이름}},  # 피부타입별 믹스
            care: {mix_code: {"percentage": pct, "name": 한글이름}},  # 관심별 믹스
            pcr: {mix_code: percentage},  # PCR 코드는 한글 이름이 없어 숫자 유지
            assessment: {mix_code: {"percentage": pct, "name": 한글이름}}
        }
        [REFACTOR 2026-06-08] assessment/skin/care는 믹스 이름을 직접 포함합니다(SSOT).
    """
    log.info(f"[처방전] create_prescription 호출: skin_assessment_scores={type(skin_assessment_scores)}")
    # 피부 평가 기반 처방 (M01-M10)
    assessment_recipe = calculate_skin_assessment_recipe(skin_assessment_scores)
    log.info(f"[처방전] assessment_recipe 결과: {assessment_recipe}")

    # 설문 연동: 피부타입별 믹스 (향후 구현 예정)
    skin_recipe = {}
    if skin_type:
        skin_recipe = _calculate_skin_type_mix(skin_type)

    # 설문 연동: 관심사별 믹스 (향후 구현 예정)
    care_recipe = {}
    if concerns:
        care_recipe = _calculate_concern_mix(concerns)

    # PCR 기반 처방
    pcr_result_data = calculate_pcr_recipe(
        pcr_result, age_group_statistics, age, gender
    )
    pcr_recipe = pcr_result_data.get("pcr_recipe", {}).get("pcr", {})
    
    # 총 믹스합 계산 (assessment + pcr + skin + care)
    # [FIX P1-9] 믹스 코드 중복 시 이중 계산 방지 - 믹스 코드별로 합산
    all_recipes = {
        **assessment_recipe,
        **pcr_recipe,
        **skin_recipe,
        **care_recipe
    }
    # 동일 믹스 코드가 있으면 최대값 사용 (중복 합산 방지)
    merged_recipe: Dict[str, float] = {}
    for mix_code, percentage in all_recipes.items():
        if mix_code in merged_recipe:
            merged_recipe[mix_code] = max(merged_recipe[mix_code], percentage)
        else:
            merged_recipe[mix_code] = percentage
    
    total_mix_percentage = sum(merged_recipe.values())

    # 베이스 비율 계산 (100 - 총믹스합)
    base_percentage = max(0, 100 - total_mix_percentage)

    # [REFACTOR 2026-06-08] 이름 포함 신 형식으로 반환 (SSOT).
    # 보고서 렌더러는 더 이상 config에서 믹스 이름을 조회하지 않음.
    # PCR 코드(PM01-PM07)도 한글 이름 포함.
    return {
        "base": {"percentage": base_percentage},
        "skin": _attach_mix_names(skin_recipe),  # 피부타입별 믹스
        "care": _attach_mix_names(care_recipe),  # 관심별 믹스
        "pcr": _attach_mix_names(pcr_recipe),  # PCR 믹스
        "assessment": _attach_mix_names(assessment_recipe)
    }


def _calculate_skin_type_mix(skin_type: str) -> Dict[str, float]:
    """피부타입별 믹스 계산

    Args:
        skin_type: "oily", "dry", "combination", "sensitive" 중 하나

    Returns:
        {mix_code: percentage} 딕셔너리
    """
    # 피부타입별 믹스 매핑
    skin_type_mapping = {
        "oily": {"M03": 2.0},  # 지성: 지성믹스
        "dry": {"M04": 2.0},  # 건성: 건성믹스
        "combination": {"M05": 2.0},  # 복합성: 복합성믹스
        "sensitive": {"M06": 2.0},  # 민감성: 민감성믹스
    }
    
    return skin_type_mapping.get(skin_type, {})


def _calculate_concern_mix(concerns: List[str]) -> Dict[str, float]:
    """관심사별 믹스 계산

    Args:
        concerns: 설문의 skin_concerns 필드 (예: ["acne", "red_marks", "pore_sebum", "pore_care", "wrinkle"])

    Returns:
        {mix_code: percentage} 딕셔너리
    """
    # 관심사별 믹스 매핑 (upload-spec.md 기반)
    concern_mapping = {
        # 색소 관련
        "pigmentation": {"M08": 2.0},  # 미백케어믹스
        "melasma": {"M08": 2.0},  # 기미
        "freckle": {"M08": 2.0},  # 주근깨

        # 홍조 관련
        "redness": {"M14": 2.0},  # 홍조케어믹스
        "red_marks": {"M14": 2.0},  # 붉은 자국

        # 트러블 관련
        "acne": {"M11": 2.0},  # 트러블케어믹스
        "pimple": {"M11": 2.0},  # 여드름

        # 모공 관련
        "pore": {"M12": 2.0},  # 모공케어믹스
        "pore_sebum": {"M12": 2.0},  # 모공/피지
        "pore_care": {"M12": 2.0},  # 모공 케어

        # 주름 관련
        "wrinkle": {"M10": 2.0},  # 주름케어믹스
        "eye_wrinkle": {"M10": 2.0},  # 눈가 주름
        "nasolabial": {"M10": 2.0},  # 팔자 주름

        # 텍스처 관련
        "texture": {"M13": 2.0},  # 피부결케어믹스
        "roughness": {"M13": 2.0},  # 거칠기

        # 톤 관련
        "tone": {"M08": 2.0},  # 미백케어믹스
        "dullness": {"M08": 2.0},  # 칙칙함
        "uneven_tone": {"M08": 2.0},  # 톤 불균일

        # 탄력 관련
        "elasticity": {"M09": 2.0},  # 탄력케어믹스
        "sagging": {"M09": 2.0},  # 처짐
        "jawline": {"M09": 2.0},  # 턱선

        # 노화 관련
        "aging": {"M10": 1.5, "M09": 1.5},  # 주름케어믹스 + 탄력케어믹스
    }

    # 관심사별 믹스 합산
    care_recipe: Dict[str, float] = {}

    for concern in concerns:
        if concern in concern_mapping:
            mix_codes = concern_mapping[concern]
            for mix_code, percentage in mix_codes.items():
                if mix_code in care_recipe:
                    # 동일 믹스 코드가 있으면 최대값 사용
                    care_recipe[mix_code] = max(care_recipe[mix_code], percentage)
                else:
                    care_recipe[mix_code] = percentage

    return care_recipe
