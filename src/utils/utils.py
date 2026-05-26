"""
공통 유틸리티 함수

[REFACTOR P2]
- apply_score_safety_net 핵심 로직 → skin.scoring.safety_net.apply_safety_net_logic 으로 이전.
  이 파일의 apply_score_safety_net 은 하위 호환 래퍼로 유지.
- random.uniform 제거 (결정적 중간값으로 대체, safety_net.py 참고).
- 설정 헬퍼(reload_scoring_config / get_restoration_config) 는 기존과 동일하게 유지.

[FIX v3.6]
- apply_score_safety_net: analyzer_compare_gui import 를 함수 내부 lazy import 로 이동.
- apply_score_safety_net 반환값에 실측 점수 메타데이터 추가 (투명성 개선).

[ADD v3.7]
- setup_logging: 중앙 집중식 로깅 설정 함수 추가.
"""
from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------

def setup_logging(
    level: Optional[str] = None,
    config_path: Optional[Path] = None,
    force: bool = False,
    enable_db_logging: bool = True,
) -> None:
    """중앙 집중식 로깅 설정을 적용합니다.
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR). None이면 config에서 로드.
        config_path: 설정 파일 경로. None이면 기본 경로 사용.
        force: True이면 이미 설정되어 있어도 강제로 재설정.
        enable_db_logging: True이면 DB 로깅 핸들러 추가.
    
    설정 파일 우선순위:
        1. config_path 인자
        2. config/config.json
        3. 기본값 (INFO)
    """
    # 이미 설정되어 있고 force가 False면 스킵
    if logging.getLogger().handlers and not force:
        return
    
    # 로그 레벨 결정
    if level is None:
        level = _load_logging_level(config_path)
    
    # 로그 레벨 문자열을 정수로 변환
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    log_level = level_map.get(level.upper(), logging.INFO)
    
    # logging.config.dictConfig를 사용하여 모든 로거에 일관된 포맷 적용
    log_format = "%(asctime)s [%(levelname)s] %(name)s:%(pathname)s:%(lineno)d: %(message)s"
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': log_format,
                'datefmt': '%H:%M:%S'
            }
        },
        'handlers': {
            'default': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout'
            }
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['default'],
                'level': log_level,
                'propagate': True
            },
            'codeformer': {  # codeformer 라이브러리
                'handlers': ['default'],
                'level': log_level,
                'propagate': False
            }
        }
    })
    
    # matplotlib 로깅 비활성화
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    
    # 기타 라이브러리 로깅 비활성화
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    # DB 로깅 핸들러 추가
    if enable_db_logging:
        try:
            from src.cli.execution_history import setup_db_logging
            setup_db_logging()
        except Exception as e:
            logger.debug("DB 로깅 설정 실패: %s", e)


def apply_formatter_to_all_loggers():
    """모든 로거에 포맷터를 적용합니다 (외부 라이브러리 포함)."""
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s:%(pathname)s:%(lineno)d: %(message)s", datefmt="%H:%M:%S")
    
    # 루트 로거
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    
    # 모든 기존 로거
    if logging.root.manager.loggerDict:
        for logger_name in logging.root.manager.loggerDict:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers:
                handler.setFormatter(formatter)


def _load_logging_level(config_path: Optional[Path] = None) -> str:
    """설정 파일에서 로그 레벨을 로드합니다.
    
    Returns:
        로그 레벨 문자열 (DEBUG, INFO, WARNING, ERROR). 실패 시 "INFO".
    """
    import json
    from pathlib import Path as P
    
    # 설정 파일 경로 결정
    if config_path:
        target = config_path
    else:
        # 프로젝트 루트의 src/config/config.json
        target = P(__file__).parent.parent / "config" / "config.json"
    
    try:
        if target.exists():
            with open(target, encoding="utf-8") as f:
                config = json.load(f)
            return config.get("logging", {}).get("level", "INFO")
    except Exception as e:
        logger.debug("config 로드 실패: %s", e)
    
    return "INFO"


def get_logging_level() -> str:
    """현재 설정된 로그 레벨을 반환합니다."""
    return _load_logging_level()


def set_logging_level(level: str, force: bool = True) -> None:
    """로그 레벨을 동적으로 변경합니다.
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        force: True이면 강제로 재설정
    """
    setup_logging(level=level, force=force)


# ---------------------------------------------------------------------------
# 점수 안전장치 — 하위 호환 래퍼
# ---------------------------------------------------------------------------

def apply_score_safety_net(
    orig_path: Path,
    final_path: Path,
    *,
    pre_analyzed_original: Optional[Dict[str, Any]] = None,
    pre_analyzed_restored: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """점수 안전장치 적용.

    [REFACTOR P2] 핵심 로직은 skin.scoring.safety_net.apply_safety_net_logic 으로 이전.
    이 함수는 기존 호출 인터페이스를 보존하는 하위 호환 래퍼입니다.

    Args:
        orig_path: 원본 이미지 경로.
        final_path: 복원 이미지 경로.
        pre_analyzed_original: 이미 분석된 원본 결과 (재분석 방지용).
        pre_analyzed_restored: 이미 분석된 복원 결과 (재분석 방지용).

    Returns:
        (orig_result, adjusted_result, actual_result)
    """
    # [FIX v3.6] PySide6 의존 모듈을 함수 내부에서 lazy import
    # [REFACTOR P1-18] GUI 의존 제거 - analyze_utils로 분리
    try:
        from src.skin.core.analyze_utils import analyze_compare_triple
    except ImportError as _e:
        raise ImportError(
            "apply_score_safety_net 은 analyze_utils 모듈이 필요합니다: "
            f"analyze_compare_triple import 실패 — {_e}"
        ) from _e

    # [REFACTOR P2] 핵심 로직을 safety_net 모듈로 위임
    from src.skin.scoring.safety_net import apply_safety_net_logic  # noqa: PLC0415

    return apply_safety_net_logic(
        orig_path,
        final_path,
        analyze_fn=analyze_compare_triple,
        pre_analyzed_original=pre_analyzed_original,
        pre_analyzed_restored=pre_analyzed_restored,
    )
