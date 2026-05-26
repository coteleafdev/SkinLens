"""
llm_model_manager.py — LLM 모델 관리 모듈

사용 가능한 Gemini 모델 목록 조회 및 모델 가용성 확인 기능을 제공합니다.
"""

from __future__ import annotations

import logging
from typing import List, Optional

log = logging.getLogger(__name__)


def _load_llm_api_key(provider: str = "gemini") -> str:
    """config/secrets.json에서 LLM API key를 로드합니다.

    Parameters
    ----------
    provider : str
        프로바이더 이름 (gemini, openai, anthropic)

    Returns
    -------
    str
        API 키 문자열. 로드 실패 시 빈 문자열 반환.
    """
    import os
    from src.utils.config import load_config as _load_config

    # 1. 환경 변수 우선
    env_var_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY"
    }
    env_var = env_var_map.get(provider, f"{provider.upper()}_API_KEY")
    api_key = os.environ.get(env_var)
    if api_key:
        return api_key

    # 2. config.secrets.json에서 로드
    config = _load_config()
    secrets_path = config.get("secrets_file", "config/config.secrets.json")

    try:
        import json
        from pathlib import Path

        secrets_file = Path(secrets_path)
        if secrets_file.exists():
            with open(secrets_file, "r", encoding="utf-8") as f:
                secrets = json.load(f)

                # ai_providers.{provider}.api_key 경로 시도
                if "ai_providers" in secrets:
                    ai_providers = secrets["ai_providers"]
                    if provider in ai_providers:
                        provider_config = ai_providers[provider]
                        if "api_key" in provider_config and provider_config["api_key"]:
                            log.info(f"[LLM] API 키 로드 성공: ai_providers.{provider}.api_key")
                            return provider_config["api_key"]

                # 하위 호환성: 최상위 레벨 키 시도
                possible_keys = [
                    f"{provider}_api_key",
                    f"{provider.upper()}_API_KEY",
                    f"{provider}_api_key_env",
                    "api_key", "API_KEY",
                    f"{provider}_key",
                    f"{provider.upper()}_KEY"
                ]
                for key in possible_keys:
                    value = secrets.get(key)
                    if value:
                        log.info(f"[LLM] API 키 로드 성공: {key}")
                        return value

                log.warning(f"[LLM] config.secrets.json에서 API 키를 찾을 수 없습니다. ai_providers.{provider}.api_key 또는 최상위 키 확인 필요.")
    except Exception as e:
        log.warning(f"시크릿 파일 로드 실패: {e}")

    return ""


def list_available_models(api_key: Optional[str] = None) -> List[str]:
    """사용 가능한 Gemini 모델 목록을 반환합니다.
    
    Parameters
    ----------
    api_key : str, optional
        Gemini API 키. None이면 환경 변수 또는 config.secrets.json에서 로드.
    
    Returns
    -------
    List[str]
        사용 가능한 모델 이름 목록 (예: ["models/gemini-2.5-pro", "models/gemini-2.5-flash", ...])
    """
    try:
        import google.generativeai as genai
        _genai_available = True
    except ImportError:
        _genai_available = False
        log.warning("[LLM] generativeai 패키지가 설치되지 않았습니다.")
        return []
    
    if api_key is None:
        api_key = _load_llm_api_key()
    
    if not api_key:
        log.warning("[LLM] API 키가 설정되지 않았습니다.")
        return []
    
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        # generateContent를 지원하는 모델만 필터링
        vision_models = [m.name for m in models if "generateContent" in m.supported_generation_methods]
        return vision_models
    except Exception as e:
        log.error(f"[LLM] 모델 목록 조회 실패: {e}")
        return []


def check_model_availability(model_name: str, api_key: Optional[str] = None) -> bool:
    """특정 모델이 사용 가능한지 확인합니다.
    
    Parameters
    ----------
    model_name : str
        확인할 모델 이름 (예: "models/gemini-2.5-pro")
    api_key : str, optional
        Gemini API 키. None이면 환경 변수 또는 config.secrets.json에서 로드.
    
    Returns
    -------
    bool
        모델 사용 가능 여부
    """
    available_models = list_available_models(api_key)
    return model_name in available_models
