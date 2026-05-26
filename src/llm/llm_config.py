"""
llm_config.py — LLM 설정 관리 모듈

config.json에서 LLM 관련 설정을 로드하는 getter 함수들을 제공합니다.
모듈 수준에서 config를 읽지 않고 getter 함수를 통해 접근하여
config reload 시 반영되도록 설계되었습니다.
"""

from __future__ import annotations

from typing import Dict

from src.utils.config import load_config as _load_config


def _get_config() -> Dict:
    """config.json에서 설정을 로드합니다."""
    return _load_config()


def get_default_model() -> str:
    """config.json에서 기본 LLM 모델을 가져옵니다."""
    return _get_config().get("llm", {}).get("default_model", "models/gemini-2.5-pro")


def get_default_provider() -> str:
    """config.json에서 기본 LLM provider를 가져옵니다."""
    return _get_config().get("llm", {}).get("provider", "gemini")


def get_default_timeout_sec() -> int:
    """config.json에서 기본 LLM 타임아웃을 가져옵니다."""
    return _get_config().get("timeouts", {}).get("llm_timeout_sec", 300)


def get_default_max_retries() -> int:
    """config.json에서 기본 최대 재시도 횟수를 가져옵니다."""
    return _get_config().get("llm", {}).get("max_retries", 3)
