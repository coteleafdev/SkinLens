"""
skin.core.config_parser
=======================
설정 파싱 전용 SSOT 모듈.

[REFACTOR 2026-05-24] config.json 기반 설정 로드로 전환.
llm_prompt_template.md는 순수 프롬프트 템플릿으로 유지.

기존 기능:
    - llm_prompt_template.md 파싱 (하위 호환용)
    - config.json 기반 설정 로드 (신규)

설계 원칙:
  - config.json 우선: measurement_weights, actual_ranges 등은 config.json에서 로드
  - 하위 호환: llm_prompt_template.md 파싱 함수 유지 (기존 코드 호환)
  - 로드 함수(load_*, get_*): 파일 I/O + 캐시. functools.cache 로 단순화.
  - 로거 이름: "skin.core.config_parser"

사용법:
    # config.json 기반 설정 로드 (신규)
    from skin.core.config_parser import (
        get_measurement_weights,           # 레이어B 18개 측정항목 가중치 (합계 1.0)
        get_restoration_quality_weights,   # 레이어B 복원품질 가중치 (합계 0.214)
        get_actual_ranges,                 # 실측 범위
        get_score_mapping,                  # 점수 매핑
        get_score_criteria,                 # 점수 기준
        get_recommendation_guidelines_from_config,  # 권고사항 가이드라인
    )
    
    # llm_prompt_template.md 파싱 (하위 호환)
    from skin.core.config_parser import (
        load_prompt_template,
        extract_section,
        parse_score_criteria,
        get_improvement_threshold,
        get_min_score,
        parse_metric_meta,
        get_metric_meta,
        get_llm_api_config,
        get_v3_categories,
        get_recommendation_guidelines,  # 템플릿 기반 (하위 호환)
    )
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

log = logging.getLogger(__name__)

# ── 기본 템플릿 경로 ────────────────────────────────────────────
# 이 파일 위치: src/skin/core/config_parser.py
# 경로 계산:
#   __file__              = src/skin/core/config_parser.py
#   parent                = src/skin/core
#   parent.parent          = src/skin
#   parent.parent.parent  = src
#   parent.parent.parent.parent = project_root (parent 4번 필요)
# 템플릿 경로: <project_root>/docs/llm_prompt_template.md
_DEFAULT_TEMPLATE_PATH: Path = (
    Path(__file__).parent.parent.parent.parent / "docs" / "llm_prompt_template.md"
)


# ═══════════════════════════════════════════════════════════════
#  파일 로드 (캐시)
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def load_prompt_template(path: Optional[Path] = None) -> str:
    """llm_prompt_template.md 내용을 읽어 캐싱하여 반환합니다.

    Args:
        path: 템플릿 파일 경로. None 이면 프로젝트 기본 경로(_DEFAULT_TEMPLATE_PATH) 사용.

    Returns:
        템플릿 문자열. 파일이 없으면 빈 문자열.
    """
    target = Path(path) if path else _DEFAULT_TEMPLATE_PATH
    if not target.exists():
        log.warning("프롬프트 템플릿 파일을 찾을 수 없습니다: %s", target)
        return ""
    content = target.read_text(encoding="utf-8")
    log.debug("프롬프트 템플릿 로드 완료: %s (%d chars)", target.name, len(content))
    return content


def invalidate_template_cache() -> None:
    """load_prompt_template 캐시를 비웁니다. 테스트·hot-reload 용도."""
    load_prompt_template.cache_clear()


# ═══════════════════════════════════════════════════════════════
#  섹션 추출 (순수 함수)
# ═══════════════════════════════════════════════════════════════

def extract_section(markdown: str, start_tag: str, end_tag: str) -> str:
    """마크다운에서 HTML 주석 태그로 감싼 섹션 내용을 반환합니다.

    Args:
        markdown:  템플릿 전체 문자열.
        start_tag: 시작 태그 (예: "<!-- SCORE_CRITERIA_START -->").
        end_tag:   종료 태그 (예: "<!-- SCORE_CRITERIA_END -->").

    Returns:
        태그 사이 텍스트 (strip). 태그를 찾지 못하면 빈 문자열.
    """
    pattern = rf"{re.escape(start_tag)}\s*(.*?)\s*{re.escape(end_tag)}"
    match = re.search(pattern, markdown, re.DOTALL)
    return match.group(1).strip() if match else ""


# ═══════════════════════════════════════════════════════════════
#  점수 기준 파싱
# ═══════════════════════════════════════════════════════════════

def parse_score_criteria(
    markdown: str,
    *,
    strict: bool = False,
) -> Dict[str, Tuple[int, int, str]]:
    """마크다운에서 점수 기준(등급별 범위)을 파싱합니다.

    [REFACTOR 2026-05-24] config.json 우선, 마크다운은 하위 호환용.

    Args:
        markdown: 템플릿 전체 문자열.
        strict:   True 이면 섹션 없거나 결과 0개 시 ValueError 발생.
                  False (기본) 이면 경고 로그 후 빈 dict 반환.

    Returns:
        Dict[등급명, (min_score, max_score, 라벨_문자열)]
    """
    # config.json 우선
    try:
        config = _load_config_json()
        score_criteria = config.get("score_criteria", {})
        score_scale = score_criteria.get("점수 스케일", {})
        grade_labels = score_criteria.get("등급 라벨", {})
        
        if score_scale and grade_labels:
            criteria: Dict[str, Tuple[int, int, str]] = {}
            for grade_name, range_info in score_scale.items():
                min_score = range_info.get("min", 0)
                max_score = range_info.get("max", 100)
                label = grade_labels.get(grade_name, grade_name)
                criteria[grade_name] = (min_score, max_score, label)
            return criteria
    except Exception as e:
        log.debug("config.json에서 점수 기준 로드 실패: %s", e)
    
    # 하위 호환: 마크다운 파싱
    section = extract_section(
        markdown,
        "<!-- SCORE_CRITERIA_START -->",
        "<!-- SCORE_CRITERIA_END -->",
    )
    if not section:
        msg = "점수 기준 섹션을 찾을 수 없습니다 (config.json 또는 <!-- SCORE_CRITERIA_START/END -->)."
        if strict:
            raise ValueError(msg)
        log.warning(msg)
        return {}

    criteria: Dict[str, Tuple[int, int, str]] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line or not line.startswith("- ") or ":" not in line:
            continue
        parts = line[2:].split(":", 1)
        if len(parts) < 2:
            continue
        grade_name = parts[0].strip()
        score_desc = parts[1].strip()
        try:
            if "이상" in score_desc:
                min_score = int(score_desc.split("점")[0].strip())
                criteria[grade_name] = (min_score, 100, f"{grade_name} ({min_score}점 이상)")
            elif "~" in score_desc:
                lo, hi = score_desc.split("~", 1)
                min_score = int(lo.strip())
                max_score = int(hi.split("점")[0].strip())
                criteria[grade_name] = (min_score, max_score, f"{grade_name} ({min_score}~{max_score}점)")
            elif "미만" in score_desc:
                max_score = int(score_desc.split("점")[0].strip())
                criteria[grade_name] = (0, max_score, f"{grade_name} ({max_score}점 미만)")
        except (ValueError, IndexError):
            log.debug("점수 기준 파싱 실패 (무시): %s", line)

    if not criteria:
        msg = "점수 기준이 0개입니다. config.json 또는 마크다운 템플릿을 확인하세요."
        if strict:
            raise ValueError(msg)
        log.warning(msg)

    return criteria


def get_improvement_threshold(template_path: Optional[Path] = None) -> float:
    """'개선필요' 등급 기준 점수(미만 경계)를 반환합니다.

    마크다운에서 min_score==0 이고 라벨에 '미만'이 포함된 등급의 max_score 반환.
    파싱 실패 시 기본값 60.0.
    """
    template = load_prompt_template(template_path)
    if not template:
        return 60.0
    criteria = parse_score_criteria(template)
    for _name, (min_score, max_score, label) in criteria.items():
        if min_score == 0 and "미만" in label:
            return float(max_score)
    return 60.0


def get_min_score(template_path: Optional[Path] = None) -> float:
    """개선필요 구간 최소 점수 (improvement_threshold - 10)를 반환합니다."""
    return get_improvement_threshold(template_path) - 10.0


# ═══════════════════════════════════════════════════════════════
#  측정항목 메타데이터 파싱
# ═══════════════════════════════════════════════════════════════

def parse_metric_meta(
    markdown: str,
    *,
    strict: bool = False,
) -> List[Tuple[str, str, str, bool]]:
    """마크다운에서 측정항목 메타데이터를 파싱합니다.

    마크다운 형식:
        <!-- METRIC_META_START -->
        ### 색소 (Pigmentation)
        - melasma_score: 기미·잡티: true
        - freckle_score: 주근깨: true
        <!-- METRIC_META_END -->

    Args:
        markdown: 템플릿 전체 문자열.
        strict:   True 이면 결과 0개 시 ValueError.

    Returns:
        List[(key, display_name, category, higher_is_better)]
    """
    section = extract_section(
        markdown,
        "<!-- METRIC_META_START -->",
        "<!-- METRIC_META_END -->",
    )
    if not section:
        msg = "측정항목 메타데이터 섹션을 찾을 수 없습니다 (<!-- METRIC_META_START/END -->)."
        if strict:
            raise ValueError(msg)
        log.warning(msg)
        return []

    metrics: List[Tuple[str, str, str, bool]] = []
    current_category: Optional[str] = None

    for line in section.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            current_category = line[4:].strip()
            continue
        if line.startswith("- ") and ":" in line and current_category:
            parts = line[2:].split(":")
            key = parts[0].strip()
            display = parts[1].strip() if len(parts) >= 2 else key
            higher_is_better = (
                parts[2].strip().lower() == "true" if len(parts) >= 3 else True
            )
            metrics.append((key, display, current_category, higher_is_better))

    if not metrics:
        msg = "측정항목이 0개입니다. 마크다운 템플릿을 확인하세요."
        if strict:
            raise ValueError(msg)
        log.warning(msg)

    log.debug("측정항목 %d개 파싱 완료", len(metrics))
    return metrics


def get_metric_meta(
    template_path: Optional[Path] = None,
    *,
    strict: bool = True,
) -> List[Tuple[str, str, str, bool]]:
    """템플릿 파일에서 측정항목 메타데이터를 로드합니다.

    Args:
        template_path: 템플릿 파일 경로. None 이면 기본 경로 사용.
        strict:        True (기본) 이면 결과 0개 시 ValueError.
    """
    template = load_prompt_template(template_path)
    if not template:
        msg = "프롬프트 템플릿을 찾을 수 없습니다. docs/llm_prompt_template.md 파일을 확인하세요."
        if strict:
            raise ValueError(msg)
        return []
    return parse_metric_meta(template, strict=strict)


# ═══════════════════════════════════════════════════════════════
#  디스플레이 이름 파싱 (METRIC_META에서 추출)
# ═══════════════════════════════════════════════════════════════

def parse_display_names(markdown: str) -> Dict[str, str]:
    """마크다운 METRIC_META 섹션에서 항목별 디스플레이 이름을 파싱합니다.

    DISPLAY_NAMES 섹션은 삭제되었으므로 METRIC_META에서 추출합니다.
    """
    metrics = parse_metric_meta(markdown, strict=False)
    return {key: display for key, display, _category, _higher in metrics}


def get_display_names(template_path: Optional[Path] = None) -> Dict[str, str]:
    """템플릿 파일에서 디스플레이 이름을 로드합니다."""
    template = load_prompt_template(template_path)
    return parse_display_names(template) if template else {}


# ═══════════════════════════════════════════════════════════════
#  카테고리 파싱
# ═══════════════════════════════════════════════════════════════

def parse_categories(markdown: str) -> List[Tuple[str, List[str]]]:
    """마크다운 METRIC_META 섹션에서 카테고리별 키 목록을 파싱합니다."""
    metrics = parse_metric_meta(markdown, strict=False)
    cat_order: List[str] = []
    cat_map: Dict[str, List[str]] = {}
    for key, _display, category, _higher in metrics:
        if category not in cat_map:
            cat_order.append(category)
            cat_map[category] = []
        cat_map[category].append(key)
    return [(cat, cat_map[cat]) for cat in cat_order]


def get_categories(template_path: Optional[Path] = None) -> List[Tuple[str, List[str]]]:
    """템플릿 파일에서 카테고리를 로드합니다."""
    template = load_prompt_template(template_path)
    return parse_categories(template) if template else []


# ═══════════════════════════════════════════════════════════════
#  측정항목 가중치 파싱
# ═══════════════════════════════════════════════════════════════

def parse_measurement_weights(markdown: str) -> Dict[str, float]:
    """마크다운에서 측정항목별 가중치를 파싱합니다."""
    section = extract_section(
        markdown,
        "<!-- MEASUREMENT_WEIGHTS_START -->",
        "<!-- MEASUREMENT_WEIGHTS_END -->",
    )
    if not section:
        return {}
    weights: Dict[str, float] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line or not line.startswith("- ") or ":" not in line:
            continue
        parts = line[2:].split(":", 1)
        if len(parts) == 2:
            try:
                weights[parts[0].strip()] = float(parts[1].strip())
            except ValueError:
                pass
    return weights


def get_measurement_weights(template_path: Optional[Path] = None) -> Dict[str, float]:
    """템플릿 파일에서 가중치를 로드합니다."""
    template = load_prompt_template(template_path)
    return parse_measurement_weights(template) if template else {}


# ═══════════════════════════════════════════════════════════════
#  실측 범위 파싱
# ═══════════════════════════════════════════════════════════════

def parse_actual_ranges(markdown: str) -> Dict[str, Tuple[float, float]]:
    """마크다운에서 항목별 실측 범위를 파싱합니다."""
    section = extract_section(
        markdown,
        "<!-- ACTUAL_RANGES_START -->",
        "<!-- ACTUAL_RANGES_END -->",
    )
    if not section:
        return {}
    ranges: Dict[str, Tuple[float, float]] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line or not line.startswith("- ") or ":" not in line:
            continue
        parts = line[2:].split(":", 1)
        if len(parts) == 2:
            values = parts[1].strip().split(",")
            if len(values) == 2:
                try:
                    ranges[parts[0].strip()] = (float(values[0].strip()), float(values[1].strip()))
                except ValueError:
                    pass
    return ranges


def get_actual_ranges(template_path: Optional[Path] = None) -> Dict[str, Tuple[float, float]]:
    """템플릿 파일에서 실측 범위를 로드합니다."""
    template = load_prompt_template(template_path)
    return parse_actual_ranges(template) if template else {}


# ═══════════════════════════════════════════════════════════════
#  점수 매핑 파싱
# ═══════════════════════════════════════════════════════════════

def parse_score_mapping(markdown: str) -> Dict[str, Tuple[str, float]]:
    """마크다운에서 점수 매핑(source_key, coefficient)을 파싱합니다."""
    section = extract_section(
        markdown,
        "<!-- SCORE_MAPPING_START -->",
        "<!-- SCORE_MAPPING_END -->",
    )
    if not section:
        return {}
    mapping: Dict[str, Tuple[str, float]] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line or not line.startswith("- ") or ":" not in line:
            continue
        parts = line[2:].split(":", 1)
        if len(parts) == 2:
            vals = parts[1].strip().split(",")
            if len(vals) == 2:
                try:
                    mapping[parts[0].strip()] = (vals[0].strip(), float(vals[1].strip()))
                except ValueError:
                    pass
    return mapping


def get_score_mapping(template_path: Optional[Path] = None) -> Dict[str, Tuple[str, float]]:
    """템플릿 파일에서 점수 매핑을 로드합니다."""
    template = load_prompt_template(template_path)
    return parse_score_mapping(template) if template else {}


# ═══════════════════════════════════════════════════════════════
#  LLM API 설정 파싱
# ═══════════════════════════════════════════════════════════════

def get_llm_api_config() -> Dict[str, Any]:
    """LLM API 호출 설정을 반환합니다.

    [REFACTOR 2026-05-24] config.json에서 설정을 동적으로 로드.

    Returns:
        Dict[temperature, max_output_tokens_single, max_output_tokens_dual,
             max_retries, retry_delay, score_correction, ...]
    """
    from src.scoring.config._config import _load_scoring_config

    config = _load_scoring_config()
    llm_config = config.get("llm", {})

    return {
        "temperature": llm_config.get("temperature", 0.3),
        "max_output_tokens_single": llm_config.get("max_output_tokens_single", 8192),
        "max_output_tokens_dual": llm_config.get("max_output_tokens_dual", 32768),
        "max_retries": llm_config.get("max_retries", 3),
        "retry_delay": 2,
        "score_correction": llm_config.get("score_correction", {}),
        "scoring_mode": llm_config.get("scoring_mode", "independent"),
    }


# ═══════════════════════════════════════════════════════════════
#  v3 직교 키 카테고리 생성 (SCORE_MAPPING 기반)
# ═══════════════════════════════════════════════════════════════

def parse_v3_categories(markdown: str) -> List[Tuple[str, List[str]]]:
    """마크다운 SCORE_MAPPING 섹션에서 직교 키 카테고리를 생성합니다.
    
    SCORE_MAPPING의 source_key를 기반으로 카테고리를 그룹화합니다.
    source_key → 카테고리 매핑:
        - pigmentation_cov, spot_density → 색소 (Pigmentation)
        - diffuse_redness, focal_lesion → 홍조·병변 (Redness/Lesion)
        - pore_score → 모공 (Pore)
        - wrinkle_score → 주름 (Wrinkle)
        - roughness_score → 텍스처 (Texture)
        - tone_score → 톤·밝기 (Tone)
        - elasticity_score → 탄력 (Elasticity)
        - skin_type_score → 피부 타입 (Skin Type)
    
    Args:
        markdown: 템플릿 전체 문자열.
    
    Returns:
        List[(카테고리명, [source_key 목록])]
    """
    mapping = parse_score_mapping(markdown)
    if not mapping:
        return []
    
    # source_key → 카테고리 매핑
    key_to_category: Dict[str, str] = {
        "pigmentation_cov": "색소 (Pigmentation)",
        "spot_density": "색소 (Pigmentation)",
        "diffuse_redness": "홍조·병변 (Redness/Lesion)",
        "focal_lesion": "홍조·병변 (Redness/Lesion)",
        "pore_score": "모공 (Pore)",
        "wrinkle_score": "주름 (Wrinkle)",
        "roughness_score": "텍스처 (Texture)",
        "tone_score": "톤·밝기 (Tone)",
        "elasticity_score": "탄력 (Elasticity)",
        "skin_type_score": "피부 타입 (Skin Type)",
    }
    
    # 카테고리별 키 그룹화
    cat_map: Dict[str, List[str]] = {}
    for source_key, _coefficient in mapping.values():
        cat = key_to_category.get(source_key, "기타 (Other)")
        if cat not in cat_map:
            cat_map[cat] = []
        cat_map[cat].append(source_key)
    
    # 카테고리 순서 유지
    category_order = [
        "색소 (Pigmentation)",
        "홍조·병변 (Redness/Lesion)",
        "모공 (Pore)",
        "주름 (Wrinkle)",
        "텍스처 (Texture)",
        "톤·밝기 (Tone)",
        "탄력 (Elasticity)",
        "피부 타입 (Skin Type)",
    ]
    
    result: List[Tuple[str, List[str]]] = []
    for cat in category_order:
        if cat in cat_map:
            result.append((cat, cat_map[cat]))
    
    # 순서에 없는 카테고리 추가
    for cat, keys in cat_map.items():
        if cat not in category_order:
            result.append((cat, keys))
    
    return result


def get_v3_categories(template_path: Optional[Path] = None) -> List[Tuple[str, List[str]]]:
    """템플릿 파일에서 v3 직교 키 카테고리를 로드합니다.
    
    Args:
        template_path: 템플릿 파일 경로. None 이면 기본 경로 사용.
    
    Returns:
        List[(카테고리명, [source_key 목록])]
    """
    template = load_prompt_template(template_path)
    return parse_v3_categories(template) if template else []


# ═══════════════════════════════════════════════════════════════
#  관리 권고사항 가이드라인 파싱
# ═══════════════════════════════════════════════════════════════

def parse_recommendation_guidelines(markdown: str) -> Dict[str, Any]:
    """마크다운에서 관리 권고사항 가이드라인을 파싱합니다.
    
    Args:
        markdown: 템플릿 전체 문자열.
    
    Returns:
        Dict[format_requirements, content_guidelines, example_format]
    """
    section = extract_section(
        markdown,
        "<!-- RECOMMENDATION_GUIDELINES_START -->",
        "<!-- RECOMMENDATION_GUIDELINES_END -->",
    )
    if not section:
        return {}
    
    result: Dict[str, Any] = {
        "format_requirements": [],
        "content_guidelines": [],
        "example_format": ""
    }
    
    current_section = None
    for line in section.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("**형식 요구사항**"):
            current_section = "format_requirements"
            continue
        elif line.startswith("**내용 가이드라인**"):
            current_section = "content_guidelines"
            continue
        elif line.startswith("**예시 형식**"):
            current_section = "example_format"
            continue
        elif line.startswith("```"):
            continue
        
        if current_section == "format_requirements" and line.startswith("- "):
            result["format_requirements"].append(line[2:].strip())
        elif current_section == "content_guidelines" and line.startswith("- "):
            result["content_guidelines"].append(line[2:].strip())
        elif current_section == "example_format":
            result["example_format"] += line + "\n"
    
    return result


def get_recommendation_guidelines(template_path: Optional[Path] = None) -> Dict[str, Any]:
    """템플릿 파일에서 관리 권고사항 가이드라인을 로드합니다.

    Args:
        template_path: 템플릿 파일 경로. None 이면 기본 경로 사용.

    Returns:
        Dict[format_requirements, content_guidelines, example_format]
    """
    template = load_prompt_template(template_path)
    return parse_recommendation_guidelines(template) if template else {}


def get_category_count() -> int:
    """config.json에서 카테고리 개수를 로드합니다.

    Returns:
        카테고리 개수. 기본값 9.
    """
    from src.prescription.prescription_calculator import _load_prescription_config

    config = _load_prescription_config()
    return config.get("category_count", 9)


def get_measurement_count() -> int:
    """config.json에서 측정항목 개수를 로드합니다.

    Returns:
        측정항목 개수. 기본값 18.
    """
    from src.prescription.prescription_calculator import _load_prescription_config

    config = _load_prescription_config()
    return config.get("measurement_count", 18)


def get_orthogonal_count() -> int:
    """config.json에서 직교 항목 개수를 로드합니다.

    Returns:
        직교 항목 개수. 기본값 10.
    """
    from src.prescription.prescription_calculator import _load_prescription_config

    config = _load_prescription_config()
    return config.get("orthogonal_count", 10)


def get_composition_function_registry() -> Dict[str, Dict[str, str]]:
    """config.json에서 합성 함수 레지스트리를 로드합니다.

    Returns:
        합성 함수 레지스트리. {함수명: {module, description}}
    """
    from src.prescription.prescription_calculator import _load_prescription_config

    config = _load_prescription_config()
    return config.get("composition_function_registry", {})


# ═══════════════════════════════════════════════════════════════
#  config.json 기반 설정 로드 (신규)
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_config_json() -> Dict[str, Any]:
    """config.json을 로드하여 캐싱합니다.

    Returns:
        config.json 내용. 파일이 없으면 빈 dict.
    """
    # 기본 경로: 루트 config/config.json
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "config.json"
    
    # 하위 호환성: src/config/config/config.json도 확인
    if not config_path.exists():
        legacy_path = Path(__file__).parent.parent.parent / "config" / "config" / "config.json"
        if legacy_path.exists():
            config_path = legacy_path
    
    if not config_path.exists():
        log.warning("config.json 파일을 찾을 수 없습니다: %s", config_path)
        return {}
    import json
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    log.debug("config.json 로드 완료")
    return config


def get_measurement_weights() -> Dict[str, Any]:
    """config.json에서 측정항목 가중치를 로드합니다.

    [REFACTOR 2026-05-24] llm_prompt_template.md에서 이전.

    Returns:
        측정항목 가중치 dict. {metric_key: weight}
    """
    config = _load_config_json()
    weights = config.get("measurement_weights", {})
    # 18개 측정항목만 반환 (복원품질은 별도 섹션으로 분리)
    return weights.get("18개 측정항목", {})


def get_restoration_quality_weights() -> Dict[str, Any]:
    """config.json에서 복원품질 가중치를 로드합니다.

    [REFACTOR 2026-05-24] 별도 섹션으로 분리.

    Returns:
        복원품질 가중치 dict. {metric_key: weight}
    """
    config = _load_config_json()
    weights = config.get("restoration_quality_weights", {})
    return weights.get("복원품질 관련 항목", {})


def get_actual_ranges() -> Dict[str, Any]:
    """config.json에서 실측 범위를 로드합니다.

    [REFACTOR 2026-05-24] llm_prompt_template.md에서 이전.

    Returns:
        실측 범위 dict. {metric_key: [min, max]}
    """
    config = _load_config_json()
    ranges = config.get("actual_ranges", {})
    # 카테고리별 + 18개 측정항목 병합
    result = {}
    if "카테고리별 커버리지 범위" in ranges:
        result.update(ranges["카테고리별 커버리지 범위"])
    if "18개 측정항목 실측 범위" in ranges:
        result.update(ranges["18개 측정항목 실측 범위"])
    return result


def get_score_mapping() -> Dict[str, Any]:
    """config.json에서 점수 매핑을 로드합니다.

    [REFACTOR 2026-05-24] llm_prompt_template.md에서 이전.

    Returns:
        점수 매핑 dict. {metric_key: {source, coefficient}}
    """
    config = _load_config_json()
    mapping = config.get("score_mapping", {})
    return mapping.get("원시 점수 소스 매핑 및 보정 계수", {})


def get_score_criteria() -> Dict[str, Any]:
    """config.json에서 점수 기준을 로드합니다.

    [REFACTOR 2026-05-24] llm_prompt_template.md에서 이전.

    Returns:
        점수 기준 dict. {점수 스케일, 등급 라벨}
    """
    config = _load_config_json()
    return config.get("score_criteria", {})


def get_recommendation_guidelines_from_config() -> Dict[str, Any]:
    """config.json에서 관리 권고사항 가이드라인을 로드합니다.

    [REFACTOR 2026-05-24] llm_prompt_template.md에서 이전.
    기존 get_recommendation_guidelines()와 이름 충돌 방지를 위해 접미사 추가.

    Returns:
        관리 권고사항 가이드라인 dict. {형식 요구사항, 내용 가이드라인}
    """
    config = _load_config_json()
    return config.get("recommendation_guidelines", {})
