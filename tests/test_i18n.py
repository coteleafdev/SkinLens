"""
test_i18n.py — 다국어 지원 기능 테스트
"""
import pytest
from src.i18n import Translator, translate


@pytest.fixture
def translator():
    """테스트용 번역기"""
    return Translator()


def test_translate_korean(translator):
    """한국어 번역 테스트"""
    result = translator.translate("welcome", "ko")
    assert result == "환영합니다"
    
    result = translator.translate("skin_analysis", "ko")
    assert result == "피부 분석"


def test_translate_english(translator):
    """영어 번역 테스트"""
    result = translator.translate("welcome", "en")
    assert result == "Welcome"
    
    result = translator.translate("skin_analysis", "en")
    assert result == "Skin Analysis"


def test_translate_chinese(translator):
    """중국어 번역 테스트"""
    result = translator.translate("welcome", "zh")
    assert result == "欢迎"
    
    result = translator.translate("skin_analysis", "zh")
    assert result == "皮肤分析"


def test_translate_japanese(translator):
    """일본어 번역 테스트"""
    result = translator.translate("welcome", "ja")
    assert result == "ようこそ"
    
    result = translator.translate("skin_analysis", "ja")
    assert result == "皮膚分析"


def test_translate_namespace(translator):
    """네임스페이스 테스트"""
    result = translator.translate("oily", "ko", "analysis")
    assert result == "지성"
    
    result = translator.translate("oily", "en", "analysis")
    assert result == "Oily"


def test_translate_fallback(translator):
    """번역 키 없을 때 기본값 테스트"""
    result = translator.translate("nonexistent_key", "ko")
    assert result == "nonexistent_key"


def test_translate_unsupported_language(translator):
    """지원하지 않는 언어 테스트"""
    result = translator.translate("welcome", "fr")
    # 기본 언어로 폴백
    assert result == "환영합니다"


def test_translate_dict(translator):
    """딕셔너리 번역 테스트"""
    data = {
        "message": "welcome",
        "status": "healthy",
        "nested": {
            "key": "skin_analysis"
        }
    }
    
    translated = translator.translate_dict(data, "en")
    assert translated["message"] == "Welcome"
    assert translated["status"] == "Healthy"
    assert translated["nested"]["key"] == "Skin Analysis"


def test_get_supported_languages(translator):
    """지원하는 언어 목록 테스트"""
    languages = translator.get_supported_languages()
    assert "ko" in languages
    assert "en" in languages
    assert "zh" in languages
    assert "ja" in languages


def test_is_language_supported(translator):
    """언어 지원 여부 테스트"""
    assert translator.is_language_supported("ko") is True
    assert translator.is_language_supported("en") is True
    assert translator.is_language_supported("fr") is False


def test_global_translate_function():
    """전역 translate 함수 테스트"""
    result = translate("welcome", "en")
    assert result == "Welcome"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
