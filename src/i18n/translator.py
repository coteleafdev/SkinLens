"""
translator.py — 다국어 번역 시스템

기능:
- 번역 리소스 로드
- 언어별 텍스트 번역
- 언어 감지
- 번역 캐싱
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

log = logging.getLogger(__name__)


class Translator:
    """번역기"""
    
    SUPPORTED_LANGUAGES = ["ko", "en", "zh", "ja"]
    DEFAULT_LANGUAGE = "ko"
    
    def __init__(self, locales_dir: Optional[str] = None):
        self.locales_dir = Path(locales_dir) if locales_dir else Path(__file__).parent.parent.parent / "locales"
        self._translations: Dict[str, Dict[str, Any]] = {}
        self._load_translations()
    
    def _load_translations(self):
        """번역 리소스 로드"""
        for lang in self.SUPPORTED_LANGUAGES:
            lang_dir = self.locales_dir / lang
            if not lang_dir.exists():
                log.warning(f"[I18n] 언어 디렉토리 없음: {lang_dir}")
                continue
            
            translations = {}
            for json_file in lang_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        translations[json_file.stem] = json.load(f)
                except Exception as e:
                    log.error(f"[I18n] 번역 파일 로드 실패: {json_file} - {e}")
            
            self._translations[lang] = translations
            log.info(f"[I18n] 번역 리소스 로드 완료: {lang} ({len(translations)} 파일)")
    
    @lru_cache(maxsize=1000)
    def translate(self, key: str, language: str = DEFAULT_LANGUAGE, namespace: str = "common") -> str:
        """
        텍스트 번역
        
        Args:
            key: 번역 키 (예: "welcome")
            language: 언어 코드 (ko, en, zh, ja)
            namespace: 네임스페이스 (common, analysis 등)
        
        Returns:
            번역된 텍스트
        """
        if language not in self.SUPPORTED_LANGUAGES:
            log.warning(f"[I18n] 지원하지 않는 언어: {language}, 기본 언어 사용")
            language = self.DEFAULT_LANGUAGE
        
        translations = self._translations.get(language, {})
        namespace_translations = translations.get(namespace, {})
        
        # 키로 번역 찾기
        if key in namespace_translations:
            return namespace_translations[key]
        
        # 네임스페이스 없이 키로 찾기
        for ns, ns_translations in translations.items():
            if key in ns_translations:
                return ns_translations[key]
        
        # 기본 언어에서 찾기
        if language != self.DEFAULT_LANGUAGE:
            return self.translate(key, self.DEFAULT_LANGUAGE, namespace)
        
        # 키를 그대로 반환
        log.warning(f"[I18n] 번역 키 없음: {key} (lang={language}, ns={namespace})")
        return key
    
    def translate_dict(self, data: Dict[str, Any], language: str = DEFAULT_LANGUAGE, namespace: str = "common") -> Dict[str, Any]:
        """
        딕셔너리의 모든 값을 번역
        
        Args:
            data: 번역할 딕셔너리
            language: 언어 코드
            namespace: 네임스페이스
        
        Returns:
            번역된 딕셔너리
        """
        translated = {}
        for key, value in data.items():
            if isinstance(value, str):
                translated[key] = self.translate(value, language, namespace)
            elif isinstance(value, dict):
                translated[key] = self.translate_dict(value, language, namespace)
            elif isinstance(value, list):
                translated[key] = [
                    self.translate_dict(item, language, namespace) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                translated[key] = value
        return translated
    
    def get_supported_languages(self) -> list:
        """지원하는 언어 목록 반환"""
        return self.SUPPORTED_LANGUAGES.copy()
    
    def is_language_supported(self, language: str) -> bool:
        """언어 지원 여부 확인"""
        return language in self.SUPPORTED_LANGUAGES


# 전역 번역기 인스턴스
_translator: Optional[Translator] = None


def get_translator() -> Translator:
    """전역 번역기 인스턴스 반환"""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def translate(key: str, language: str = Translator.DEFAULT_LANGUAGE, namespace: str = "common") -> str:
    """편의 함수: 텍스트 번역"""
    return get_translator().translate(key, language, namespace)
