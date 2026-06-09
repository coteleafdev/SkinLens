#!/usr/bin/env python3
"""
GUI Entry Point - 그래픽 사용자 인터페이스 진입점

이 모듈은 GUI 모드의 진입점으로, gui_wrapper를 사용하여
GUI 환경을 초기화하고 메인 윈도우를 표시합니다.

사용법:
    python -m src.gui.entry
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.utils.utils import setup_logging
from src.gui.gui_wrapper import initialize_gui


def main() -> int:
    """GUI 메인 함수."""
    # 로깅 설정
    setup_logging(mode="gui")

    # GUI 초기화 및 실행
    return initialize_gui()


if __name__ == "__main__":
    sys.exit(main())
