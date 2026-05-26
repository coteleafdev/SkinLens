"""
i18n package — 다국어 지원 관련 모듈
"""
from src.i18n.translator import Translator, get_translator, translate

__all__ = [
    "Translator",
    "get_translator",
    "translate",
]
