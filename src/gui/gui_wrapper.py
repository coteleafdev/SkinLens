#!/usr/bin/env python3
"""
GUI Wrapper - GUI 특화 로직

이 모듈은 GUI 모드의 특화 로직을 포함합니다.
PySide6 관련 초기화, GUI 윈도우 생성 및 표시 등을 담당합니다.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def initialize_gui() -> int:
    """GUI 환경을 초기화하고 메인 윈도우를 표시합니다.

    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except ImportError as e:
        log.error("PySide6 가 설치되어 있지 않습니다: %s", e)
        log.error("  pip install PySide6")
        return 1

    try:
        from src.gui.skin_analysis_gui import SkinAnalysisWindow, _center_window_on_screen
    except ImportError as e:
        log.error("GUI 모듈을 불러오지 못했습니다 (PySide6 외 의존성): %s", e)
        log.error("  프로젝트 루트에서 실행하는지, skin_scoring 가 요구하는 모듈이 있는지 확인하세요.")
        return 1

    # Windows에서 종료 직전 일시 정지 시 뜨는 "응답 없음(ghost window)" 표시를 억제
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.DisableProcessWindowsGhosting()
        except Exception as e:
            log.warning(f"DisableProcessWindowsGhosting failed: {e}", exc_info=True)

    # DPI 설정
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # QApplication 생성
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # 메인 윈도우 생성
    w = SkinAnalysisWindow()
    _center_window_on_screen(w)
    w.show()

    # 이벤트 루프 실행
    return app.exec()


def run_gui_pipeline(
    input_image: Path,
    output_dir: Path,
    **kwargs
) -> dict:
    """GUI 모드에서 파이프라인을 실행합니다.

    이 함수는 GUI 내부에서 파이프라인을 실행할 때 사용합니다.
    CLI와 동일한 파이프라인을 사용하지만, GUI 특화 파라미터를 추가로 처리합니다.

    Args:
        input_image: 입력 이미지 경로
        output_dir: 출력 디렉토리 경로
        **kwargs: 추가 파라미터

    Returns:
        파이프라인 결과 딕셔너리
    """
    from src.cli.skin_analysis_cli import run_analysis_pipeline

    # GUI 특화 파라미터 처리
    gui_kwargs = kwargs.copy()

    # 파이프라인 실행 (CLI와 동일한 전체 파이프라인 사용)
    result = run_analysis_pipeline(
        input_image=input_image,
        output_dir=output_dir,
        **gui_kwargs
    )

    return result
