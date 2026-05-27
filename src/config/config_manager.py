"""src.config.config_manager — 통합 설정 관리자.

[REFACTOR P1] 설정 로직 중앙화:
  - utils.config, scoring.config._config, skin.core.config_parser 통합
  - 단일 진입점으로 설정 로드 일관성 확보
  - Thread-safe 캐싱, mtime 기반 자동 리로드
  - 설정 검증 및 기본값 제공

사용법:
    from src.config.config_manager import ConfigManager

    config = ConfigManager.get_instance()
    weights = config.get_measurement_weights()
    display_names = config.get_display_names()
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class ConfigManager:
    """통합 설정 관리자 (싱글톤).
    
    config.json, llm_prompt_template.md 등 모든 설정 파일을
    중앙에서 관리하고 캐싱합니다.
    """
    
    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        
        # 프로젝트 루트 경로 계산
        self._project_root = Path(__file__).resolve().parents[2]
        self._config_path = self._project_root / "config" / "config.json"
        self._template_path = self._project_root / "docs" / "llm_prompt_template.md"
        self._secrets_path = self._project_root / "config" / "config.secrets.json"
        
        # 하위 호환성: src/config/config/ 디렉토리도 확인
        legacy_config_path = self._project_root / "src" / "config" / "config" / "config.json"
        if legacy_config_path.exists() and not self._config_path.exists():
            self._config_path = legacy_config_path
            log.info("레거시 config.json 경로 사용: %s", self._config_path)
        
        legacy_secrets_path = self._project_root / "src" / "config" / "config" / "config.secrets.json"
        if legacy_secrets_path.exists() and not self._secrets_path.exists():
            self._secrets_path = legacy_secrets_path
            log.info("레거시 config.secrets.json 경로 사용: %s", self._secrets_path)
        
        # 설정 파일 존재 여부 로그
        log.info("ConfigManager 초기화: config_path=%s (존재=%s)", 
                 self._config_path, self._config_path.exists())
        
        # 캐시
        self._config_cache: Dict[str, Any] = {}
        self._template_cache: str = ""
        self._secrets_cache: Dict[str, Any] = {}
        self._config_mtime: Optional[float] = None
        self._template_mtime: Optional[float] = None
        self._secrets_mtime: Optional[float] = None
        self._cache_lock = threading.Lock()
        
        # 필수 버전
        self._required_config_version = "3.6"
        
        # secrets 파일 로드 (환경 변수 설정)
        self._load_secrets()
    
    def _load_config(self) -> Dict[str, Any]:
        """config.json을 로드합니다 (mtime 기반 캐싱)."""
        with self._cache_lock:
            if not self._config_path.exists():
                log.error("config.json 파일을 찾을 수 없습니다: %s", self._config_path)
                # 폴백: 레거시 경로 시도
                legacy_path = self._project_root / "src" / "config" / "config" / "config.json"
                if legacy_path.exists():
                    log.warning("레거시 경로에서 config.json 로드 시도: %s", legacy_path)
                    self._config_path = legacy_path
                else:
                    log.error("레거시 경로에도 config.json 없음: %s", legacy_path)
                    return {}
            
            current_mtime = self._config_path.stat().st_mtime
            if (self._config_cache 
                and self._config_mtime is not None 
                and current_mtime <= self._config_mtime):
                log.debug("config.json 캐시 사용 (mtime 변경 없음)")
                return self._config_cache
            
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                
                # 버전 검증
                json_ver = str(loaded.get("config_version", "0"))
                req = self._required_config_version
                if (tuple(int(x) for x in json_ver.split("."))
                        < tuple(int(x) for x in req.split("."))):
                    log.warning("config.json 버전(%s) < 요구(%s) — 기본값 사용.", json_ver, req)
                    return {}
                
                self._config_cache = loaded
                self._config_mtime = current_mtime
                log.info("config.json 로드 완료: %s (v%s)", self._config_path, json_ver)
                return self._config_cache
            except (json.JSONDecodeError, IOError) as e:
                log.error("config.json 로드 실패: %s (경로: %s)", e, self._config_path)
                return {}
    
    def _load_template(self) -> str:
        """llm_prompt_template.md를 로드합니다 (mtime 기반 캐싱)."""
        with self._cache_lock:
            if not self._template_path.exists():
                log.warning("프롬프트 템플릿 파일을 찾을 수 없습니다: %s", self._template_path)
                return ""
            
            current_mtime = self._template_path.stat().st_mtime
            if (self._template_cache 
                and self._template_mtime is not None 
                and current_mtime <= self._template_mtime):
                return self._template_cache
            
            try:
                content = self._template_path.read_text(encoding="utf-8")
                self._template_cache = content
                self._template_mtime = current_mtime
                log.debug("프롬프트 템플릿 로드 완료: %s (%d chars)", 
                         self._template_path.name, len(content))
                return content
            except IOError as e:
                log.warning("프롬프트 템플릿 로드 실패: %s", e)
                return ""
    
    def _load_secrets(self) -> None:
        """config.secrets.json을 로드하여 환경 변수로 설정합니다."""
        import os
        if not self._secrets_path.exists():
            log.debug("config.secrets.json 파일을 찾을 수 없습니다: %s", self._secrets_path)
            return
        
        try:
            with open(self._secrets_path, encoding="utf-8") as f:
                secrets = json.load(f)
            
            # API 키를 환경 변수로 설정
            if "gemini_api_key" in secrets:
                os.environ["GEMINI_API_KEY"] = secrets["gemini_api_key"]
            if "telegram_bot_token" in secrets:
                os.environ["TELEGRAM_BOT_TOKEN"] = secrets["telegram_bot_token"]
            if "telegram_chat_id" in secrets:
                os.environ["TELEGRAM_CHAT_ID"] = secrets["telegram_chat_id"]
            
            # Supabase 설정
            if "supabase" in secrets:
                supabase = secrets["supabase"]
                if supabase.get("url"):
                    os.environ["SUPABASE_URL"] = supabase["url"]
                if supabase.get("key"):
                    os.environ["SUPABASE_KEY"] = supabase["key"]
                if supabase.get("enabled") is not None:
                    os.environ["SUPABASE_ENABLED"] = str(supabase["enabled"])
            
            log.debug("config.secrets.json 로드 완료: 환경 변수 설정됨")
        except Exception as e:
            log.warning("config.secrets.json 로드 실패: %s", e)
    
    def reload(self) -> None:
        """모든 캐시를 비우고 설정을 다시 로드합니다."""
        with self._cache_lock:
            self._config_mtime = None
            self._template_mtime = None
            self._config_cache.clear()
            self._template_cache = ""
        log.info("설정 캐시 초기화 완료")
    
    # ── config.json 접근자 ─────────────────────────────────────────
    
    def get_config(self) -> Dict[str, Any]:
        """전체 config.json을 반환합니다."""
        return self._load_config()
    
    def get_measurement_weights(self) -> Dict[str, float]:
        """측정항목 가중치를 반환합니다."""
        cfg = self._load_config()
        if cfg and "measurement_weights" in cfg:
            return cfg["measurement_weights"]
        log.warning("측정항목 가중치 로드 실패.")
        return {}
    
    def get_display_names(self) -> Dict[str, str]:
        """디스플레이 이름을 반환합니다."""
        cfg = self._load_config()
        if cfg and "display_names" in cfg:
            return cfg["display_names"]
        log.warning("디스플레이 이름 로드 실패.")
        return {}
    
    def get_categories(self) -> List[Tuple[str, List[str]]]:
        """카테고리를 반환합니다."""
        cfg = self._load_config()
        if cfg and "categories" in cfg:
            return cfg["categories"]
        log.warning("카테고리 로드 실패.")
        return []
    
    def get_actual_ranges(self) -> Dict[str, Tuple[float, float]]:
        """실측 범위를 반환합니다."""
        cfg = self._load_config()
        if cfg and "actual_ranges" in cfg:
            return cfg["actual_ranges"]
        log.warning("실측 범위 로드 실패.")
        return {}
    
    def get_score_mapping(self) -> Dict[str, Tuple[str, float]]:
        """점수 매핑을 반환합니다."""
        cfg = self._load_config()
        if cfg and "score_mapping" in cfg:
            return cfg["score_mapping"]
        log.warning("점수 매핑 로드 실패.")
        return {}
    
    def get_score_criteria(self) -> Dict[str, Any]:
        """점수 기준을 반환합니다."""
        cfg = self._load_config()
        if cfg and "score_criteria" in cfg:
            return cfg["score_criteria"]
        log.warning("점수 기준 로드 실패.")
        return {}
    
    def get_restoration_quality_weights(self) -> Dict[str, float]:
        """복원품질 가중치를 반환합니다."""
        cfg = self._load_config()
        if cfg and "restoration_quality_weights" in cfg:
            return cfg["restoration_quality_weights"]
        log.warning("복원품질 가중치 로드 실패.")
        return {}
    
    def get_display_range(self) -> Tuple[float, float]:
        """디스플레이 범위를 반환합니다."""
        cfg = self._load_config()
        if cfg and "display_range" in cfg:
            return tuple(cfg["display_range"])
        return (10.0, 90.0)
    
    def get_score_safety_net_config(self) -> Dict[str, Any]:
        """안전장치 설정을 반환합니다."""
        cfg = self._load_config()
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
    
    def get_restoration_config(self) -> Dict[str, Any]:
        """복원 설정을 반환합니다."""
        cfg = self._load_config()
        if cfg and "restoration" in cfg:
            return cfg["restoration"]
        return {
            "codeformer_fidelity": 1.0,
            "codeformer_fidelity_min": 0.0,
            "codeformer_fidelity_max": 1.0,
            "codeformer_upscale": 2,
            "codeformer_additional": True,
        }
    
    def get_product_recommendation_config(self) -> Dict[str, Any]:
        """맞춤형 화장품 추천 설정을 반환합니다."""
        cfg = self._load_config()
        if cfg and "product_recommendation" in cfg:
            return cfg["product_recommendation"]
        return {
            "enabled": False,
            "min_match_score": 0.70,
            "max_products": 5,
            "categories": ["세안제", "토너", "세럼", "크림", "선크림"],
        }
    
    # ── 프롬프트 템플릿 접근자 ───────────────────────────────────────
    
    def get_template(self) -> str:
        """프롬프트 템플릿 내용을 반환합니다."""
        return self._load_template()
    
    def get_llm_api_config(self) -> Dict[str, Any]:
        """LLM API 설정을 반환합니다 (config.json 우선)."""
        cfg = self._load_config()
        if cfg and "llm_api" in cfg:
            return cfg["llm_api"]
        # 하위 호환: 템플릿에서 파싱 시도
        from src.skin.core.config_parser import get_llm_api_config as _legacy
        return _legacy()
    
    def get_recommendation_guidelines(self) -> Dict[str, Any]:
        """권고사항 가이드라인을 반환합니다 (config.json 우선)."""
        cfg = self._load_config()
        if cfg and "recommendation_guidelines" in cfg:
            return cfg["recommendation_guidelines"]
        # 하위 호환: 템플릿에서 파싱 시도
        from src.skin.core.config_parser import get_recommendation_guidelines as _legacy
        return _legacy()
    
    # ── 유틸리티 ───────────────────────────────────────────────────
    
    @staticmethod
    def get_instance() -> "ConfigManager":
        """싱글톤 인스턴스를 반환합니다."""
        if ConfigManager._instance is None:
            ConfigManager._instance = ConfigManager()
        return ConfigManager._instance


# 편의 함수: 싱글톤 인스턴스 접근
get_config_manager = ConfigManager.get_instance
