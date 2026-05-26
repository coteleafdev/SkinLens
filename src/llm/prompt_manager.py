"""src.llm.prompt_manager — LLM 프롬프트 관리자.

[REFACTOR P3] LLM 프롬프트 관리:
  - 프롬프트 버전 관리
  - A/B 테스트 지원
  - 프롬프트 템플릿 로드 및 캐싱
  - 실험 용이성 확보

사용법:
    from src.llm.prompt_manager import PromptManager

    pm = PromptManager.get_instance()
    prompt = pm.get_prompt("dual_image", version="v1")
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class PromptManager:
    """LLM 프롬프트 관리자 (싱글톤).
    
    프롬프트 버전 관리, A/B 테스트, 템플릿 로드를 중앙에서 관리합니다.
    """
    
    _instance: Optional["PromptManager"] = None
    
    def __new__(cls) -> "PromptManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        
        # 프로젝트 루트 경로 계산
        self._project_root = Path(__file__).resolve().parents[3]
        self._prompts_dir = self._project_root / "docs" / "llm_prompts"
        
        # 캐시
        self._prompt_cache: Dict[str, str] = {}
    
    # ── 프롬프트 로드 ───────────────────────────────────────────────────
    
    def get_prompt(
        self,
        prompt_name: str,
        version: str = "v1",
        *,
        use_cache: bool = True,
    ) -> str:
        """프롬프트를 로드합니다.
        
        Args:
            prompt_name: 프롬프트 이름 (예: "dual_image", "single_image")
            version: 프롬프트 버전 (예: "v1", "v2")
            use_cache: 캐시 사용 여부
        
        Returns:
            프롬프트 문자열. 파일이 없으면 빈 문자열.
        """
        cache_key = f"{prompt_name}_{version}"
        
        if use_cache and cache_key in self._prompt_cache:
            return self._prompt_cache[cache_key]
        
        # 프롬프트 파일 경로 계산
        prompt_file = self._prompts_dir / f"{prompt_name}_{version}.md"
        
        if not prompt_file.exists():
            log.warning("프롬프트 파일을 찾을 수 없습니다: %s", prompt_file)
            return ""
        
        try:
            content = prompt_file.read_text(encoding="utf-8")
            if use_cache:
                self._prompt_cache[cache_key] = content
            log.debug("프롬프트 로드 완료: %s (v%s)", prompt_name, version)
            return content
        except IOError as e:
            log.warning("프롬프트 로드 실패: %s", e)
            return ""
    
    def get_prompt_from_template(
        self,
        template_name: str,
        variables: Dict[str, Any],
        version: str = "v1",
    ) -> str:
        """템플릿에서 프롬프트를 생성합니다.
        
        Args:
            template_name: 템플릿 이름
            variables: 템플릿 변수 딕셔너리
            version: 프롬프트 버전
        
        Returns:
            변수가 치환된 프롬프트 문자열
        """
        template = self.get_prompt(template_name, version)
        
        if not template:
            return ""
        
        # 간단한 변수 치환
        for key, value in variables.items():
            template = template.replace(f"{{{key}}}", str(value))
        
        return template
    
    # ── 프롬프트 버전 관리 ─────────────────────────────────────────────
    
    def list_available_versions(self, prompt_name: str) -> list[str]:
        """사용 가능한 프롬프트 버전을 나열합니다.
        
        Args:
            prompt_name: 프롬프트 이름
        
        Returns:
            버전 리스트 (예: ["v1", "v2"])
        """
        if not self._prompts_dir.exists():
            return []
        
        versions = []
        pattern = f"{prompt_name}_*.md"
        
        for file in self._prompts_dir.glob(pattern):
            # 파일명에서 버전 추출 (예: dual_image_v1.md -> v1)
            stem = file.stem  # dual_image_v1
            if "_" in stem:
                version = stem.split("_")[-1]
                versions.append(version)
        
        return sorted(versions)
    
    def get_latest_version(self, prompt_name: str) -> str:
        """최신 프롬프트 버전을 반환합니다.
        
        Args:
            prompt_name: 프롬프트 이름
        
        Returns:
            최신 버전 문자열 (예: "v2"). 버전이 없으면 "v1".
        """
        versions = self.list_available_versions(prompt_name)
        
        if not versions:
            return "v1"
        
        # 버전 정렬 (v1, v2, v3 ...)
        versions.sort(key=lambda x: int(x[1:]) if x.startswith("v") else 0)
        return versions[-1]
    
    # ── A/B 테스트 지원 ─────────────────────────────────────────────────
    
    def get_ab_test_prompt(
        self,
        prompt_name: str,
        variant: str = "A",
        version: str = "v1",
    ) -> str:
        """A/B 테스트용 프롬프트를 반환합니다.
        
        Args:
            prompt_name: 프롬프트 이름
            variant: 변형 (예: "A", "B")
            version: 프롬프트 버전
        
        Returns:
            A/B 테스트용 프롬프트
        """
        ab_prompt_name = f"{prompt_name}_{variant}"
        return self.get_prompt(ab_prompt_name, version)
    
    # ── 캐시 관리 ─────────────────────────────────────────────────────
    
    def clear_cache(self) -> None:
        """프롬프트 캐시를 비웁니다."""
        self._prompt_cache.clear()
        log.debug("프롬프트 캐시 초기화 완료")
    
    def reload_prompt(self, prompt_name: str, version: str = "v1") -> None:
        """특정 프롬프트를 다시 로드합니다.
        
        Args:
            prompt_name: 프롬프트 이름
            version: 프롬프트 버전
        """
        cache_key = f"{prompt_name}_{version}"
        if cache_key in self._prompt_cache:
            del self._prompt_cache[cache_key]
        log.debug("프롬프트 재로드: %s (v%s)", prompt_name, version)
    
    # ── 유틸리티 ───────────────────────────────────────────────────────
    
    @staticmethod
    def get_instance() -> "PromptManager":
        """싱글톤 인스턴스를 반환합니다."""
        if PromptManager._instance is None:
            PromptManager._instance = PromptManager()
        return PromptManager._instance


# 편의 함수: 싱글톤 인스턴스 접근
get_prompt_manager = PromptManager.get_instance
