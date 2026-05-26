"""src.scoring._config — 피부 분석 설정 로드.

[REFACTOR P1] ConfigManager 위임: 중앙화된 ConfigManager 사용.
[REFACTOR] skin_scoring.py에서 분리.
  - reload_scoring_config
  - get_* 설정 접근자 함수들 (ConfigManager 위임)

모든 경로는 __file__ 기준으로 계산하여 CWD 의존 제거.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_CONFIG_LOCK = threading.Lock()


def _load_scoring_config(config_path: Optional["Path"] = None) -> Dict[str, Any]:
    """설정을 로드합니다 (ConfigManager 위임).
    
    [REFACTOR P1] ConfigManager 사용 - 중앙화된 설정 관리자.
    """
    try:
        from src.config.config_manager import ConfigManager
        return ConfigManager.get_instance().get_config()
    except ImportError:
        log.warning("ConfigManager import 실패. 폴백 로직 사용.")
        # 폴백: 직접 로드 (하위 호환)
        import json
        from pathlib import Path
        _PROJECT_ROOT = Path(__file__).resolve().parents[3]
        _DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.json"
        if config_path is None:
            config_path = _DEFAULT_CONFIG_PATH
        try:
            if not config_path.exists():
                log.warning("점수 설정 파일 없음: %s. 기본값 사용.", config_path)
                return {}
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            json_ver = str(loaded.get("config_version", "0"))
            req = "3.6"
            if (tuple(int(x) for x in json_ver.split("."))
                    < tuple(int(x) for x in req.split("."))):
                log.warning("config.json 버전(%s) < 요구(%s) — 기본값 사용.", json_ver, req)
                return {}
            log.info("점수 설정 로드: %s (v%s)", config_path, json_ver)
            return loaded
        except Exception as e:
            log.error("점수 설정 로드 실패: %s", e)
            return {}


def reload_scoring_config() -> None:
    """설정을 다시 로드하고 모든 캐시를 초기화합니다.
    
    [REFACTOR P1] ConfigManager.reload() 호출 - 중앙화된 캐시 초기화.
    """
    try:
        from src.config.config_manager import ConfigManager
        ConfigManager.get_instance().reload()
    except ImportError:
        log.warning("ConfigManager import 실패. 캐시 초기화 건너뜀.")

    # _LazyReportAttr 캐시도 초기화
    from src.scoring._report import _LazyReportAttr
    _LazyReportAttr._weights = None
    _LazyReportAttr._keys = None
    _LazyReportAttr._categories = None
    _LazyReportAttr._display_names = None

    # _breakpoints.py 캐시도 초기화
    from src.scoring._breakpoints import _DEFAULT_BREAKPOINTS, _IMAGE_PROC_PARAMS
    _DEFAULT_BREAKPOINTS.clear()
    _IMAGE_PROC_PARAMS.clear()

    # OUTPUT_KEYS 캐시도 초기화
    from src.skin.compose.score_composition import reload_weights_cache, OUTPUT_KEYS, WEIGHTS
    reload_weights_cache()
    OUTPUT_KEYS.reload()
    WEIGHTS.reload()

    # config_parser lru_cache도 초기화
    from src.skin.core.config_parser import invalidate_template_cache
    invalidate_template_cache()

    # _score_utils _MEASUREMENT_ACTUAL_RANGES 캐시도 초기화
    from src.scoring._score_utils import invalidate_actual_ranges_cache
    invalidate_actual_ranges_cache()


# ── config_parser 위임 접근자 ──────────────────────────────────────

def get_measurement_weights() -> Dict[str, float]:
    from src.skin.core.config_parser import get_measurement_weights as _impl
    w = _impl()
    if w:
        return w
    log.warning("측정항목 가중치 로드 실패.")
    return {}


def get_display_names() -> Dict[str, str]:
    from src.skin.core.config_parser import get_display_names as _impl
    d = _impl()
    if d:
        return d
    log.warning("디스플레이 이름 로드 실패.")
    return {}


def get_categories() -> List[Tuple[str, List[str]]]:
    from src.skin.core.config_parser import get_categories as _impl
    c = _impl()
    if c:
        return c
    log.warning("카테고리 로드 실패.")
    return []


def get_v3_categories() -> List[Tuple[str, List[str]]]:
    from src.skin.core.config_parser import get_v3_categories as _impl
    c = _impl()
    if c:
        return c
    log.warning("v3 카테고리 로드 실패.")
    return []


def get_actual_ranges() -> Dict[str, Tuple[float, float]]:
    from src.skin.core.config_parser import get_actual_ranges as _impl
    r = _impl()
    if r:
        return r
    log.warning("실측 범위 로드 실패.")
    return {}


def get_display_range() -> Tuple[float, float]:
    cfg = _load_scoring_config()
    return tuple(cfg["display_range"]) if cfg and "display_range" in cfg else (10.0, 90.0)


def get_score_safety_net_config() -> Dict[str, Any]:
    cfg = _load_scoring_config()
    if cfg and "score_safety_net" in cfg:
        return cfg["score_safety_net"]
    return {
        "enabled": True,
        "acne_weight": 0.095,
        "target_score_increase_min": 14.0,
        "target_score_increase_max": 16.0,
        "max_score_limit": 90.0,
        "min_score_increase_when_lower": 1.0,
    }


def get_restoration_config() -> Dict[str, Any]:
    cfg = _load_scoring_config()
    if cfg and "restoration" in cfg:
        return cfg["restoration"]
    return {
        "codeformer_fidelity": 1.0,
        "codeformer_fidelity_min": 0.0,
        "codeformer_fidelity_max": 1.0,
        "codeformer_upscale": 2,
        "codeformer_additional": True,
    }


def get_product_recommendation_config() -> Dict[str, Any]:
    """맞춤형 화장품 추천 설정을 반환합니다.
    
    [REFACTOR 2026-05-22] 화장품 매칭 로직 파라미터화.
    
    Returns:
        Dict[enabled, min_match_score, max_products, categories]
    """
    cfg = _load_scoring_config()
    if cfg and "product_recommendation" in cfg:
        return cfg["product_recommendation"]
    return {
        "enabled": False,
        "min_match_score": 0.70,
        "max_products": 5,
        "categories": ["세안제", "토너", "세럼", "크림", "선크림"],
    }
