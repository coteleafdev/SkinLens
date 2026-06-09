# -*- coding: utf-8 -*-
"""
원본 vs 보정(기준) 이미지에 대해 analyzer_impl_v3 레이어B 측정 항목을 테이블 형식으로 비교 표시.

환경 변수
─────────
AI_SKIN_MEASUREMENT_DEBUG=1
    stderr 에 단계별 경과 시간 로그.
AI_SKIN_ANALYSIS_MAX_SIDE=1024
    원본·보정은 파이프라인에서 보통 동일 해상도이다. 긴 변이 이보다 크면
    원본·보정 모두 같은 규칙으로 분석 전 임시 축소(0 이면 비활성). 기본 1024.
    분석이 길면 800 등으로 낮춰 시도.
AI_SKIN_MEASUREMENT_REF_STAT=0
    보정 이미지 분석 시 원본 skin_stat(ref_stat) 미사용(파이프라인과 다를 수 있음).

이 파일은 하위 호환성을 위해 유지되는 래퍼입니다.
실제 기능은 다음 모듈로 분리되었습니다:
  - llm_workers.py: LLM 백그라운드 작업자 클래스
  - dialog_utils.py: 유틸리티 함수
  - analysis_worker.py: 분석 백그라운드 작업자
  - compare_dialog.py: 메인 다이얼로그 클래스
  - dialog_helpers.py: 스레드 관리 및 진입점 함수

새로운 코드에서는 각 모듈을 직접 임포트하여 사용하세요.
"""
from __future__ import annotations

import logging
import os
import sys

# Windows 콘솔 한글 깨짐 방지: UTF-8 인코딩 설정
if sys.platform == "win32":
    import io
    # 이미 TextIOWrapper로 감싸져 있는지 확인 후 재설정 방지
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except (ValueError, AttributeError):
            pass  # 이미 닫혀있거나 설정 불가능한 경우 무시
    if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding != 'utf-8':
        try:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except (ValueError, AttributeError):
            pass  # 이미 닫혀있거나 설정 불가능한 경우 무시

# 로깅 설정은 main.py에서 담당하므로 여기서는 하지 않음
# from src.utils.utils import setup_logging
# setup_logging(mode="gui")
log = logging.getLogger(__name__)

# Pillow 디버그 로그 숨기기
logging.getLogger("PIL").setLevel(logging.WARNING)

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QDialog, QWidget

# skin_scoring 레이어B 와 동일한 18키 순서·그룹
from src.scoring.skin_scoring import SkinAnalyzer, get_measurement_categories

# LLM 백그라운드 작업자 클래스
from src.gui.llm_workers import LlmWorker, LlmSingleWorker

# 다이얼로그 유틸리티 함수
from src.gui.dialog_utils import (
    close_all_compare_dialogs,
    _env_debug_enabled,
    _env_ref_stat_enabled,
    _analysis_max_side,
    _analysis_hard_timeout_seconds,
    _prepare_analysis_path,
    _dlog,
    _flatten_measurement_keys,
    _numeric_value,
    _short_label,
    _OPEN_COMPARE_DIALOGS,
    _COMPARE_THREADS,
    _COMPARE_WORKERS,
)

# 분석 백그라운드 작업자
from src.gui.analysis_worker import _AnalyzeWorker

# 다이얼로그 헬퍼 함수
from src.gui.dialog_helpers import (
    _skin_compare_attach,
    _skin_compare_detach,
    show_skin_measurement_compare_dialog,
    resolve_ref_image_path,
)

# 메인 다이얼로그
from src.gui.compare_dialog import SkinMeasurementCompareDialog

try:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as OpenpyxlImage
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False

# ──────────────────────────────────────────────────────────────
# Backward Compatibility: Re-export from new modules
# ──────────────────────────────────────────────────────────────

__all__ = [
    # Workers
    "LlmWorker",
    "LlmSingleWorker",
    "_AnalyzeWorker",
    # Utils
    "close_all_compare_dialogs",
    "_env_debug_enabled",
    "_env_ref_stat_enabled",
    "_analysis_max_side",
    "_analysis_hard_timeout_seconds",
    "_prepare_analysis_path",
    "_dlog",
    "_flatten_measurement_keys",
    "_numeric_value",
    "_short_label",
    # Helpers
    "_skin_compare_attach",
    "_skin_compare_detach",
    "show_skin_measurement_compare_dialog",
    "resolve_ref_image_path",
    # Dialog
    "SkinMeasurementCompareDialog",
]
