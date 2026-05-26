"""src.utils.config — 공통 설정 로드 헬퍼.

[REFACTOR P1] ConfigManager 위임: 중앙화된 ConfigManager 사용.
[REFACTOR P3-30] 역방향 의존 해소: scoring.config 의존 제거.

하위 호환: 기존 load_config() 인터페이스 유지.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

log = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """config.json에서 설정을 로드합니다.

    [REFACTOR P1] ConfigManager 위임 - 중앙화된 설정 관리자 사용.
    캐싱을 통해 중복 로드 방지.

    Returns
    -------
    Dict[str, Any]
        로드된 config.json 내용. 파일이 없거나 버전 미달 시 빈 딕셔너리 반환.
    """
    try:
        from src.config.config_manager import ConfigManager
        return ConfigManager.get_instance().get_config()
    except ImportError:
        log.warning("ConfigManager import 실패. 폴백 로직 사용.")
        # 폴백: 직접 로드 (하위 호환)
        import json
        from pathlib import Path
        _CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.json"
        if not _CONFIG_PATH.exists():
            log.warning("config.json 파일을 찾을 수 없습니다: %s", _CONFIG_PATH)
            return {}
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.warning("config.json 로드 실패: %s", e)
            return {}


def get_db_path_from_env() -> str:
    """환경변수에서 데이터베이스 경로 로드.

    [REFACTOR 2026-05-24] execution_history.py에서 이동하여 God Object 완화.
    server/, db/, cli/, telegram/ 등 전방위에서 사용하는 공통 유틸리티.

    Returns:
        데이터베이스 파일 경로 (기본값: "execution_history.db")
    """
    return os.environ.get("EXECUTION_HISTORY_DB", "execution_history.db")
