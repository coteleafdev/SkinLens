"""
xlsx_utils.py — Excel 파일 처리 유틸리티 모듈

openpyxl을 사용한 Excel 파일 생성 및 스타일링에 대한
재사용 가능한 유틸리티 함수를 제공합니다.
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False


def append_with_font(
    ws: Any,
    values: List[Any],
    font: Optional[Font] = None,
) -> int:
    """워크시트에 행을 추가하고 폰트를 적용한 후 현재 행 번호를 반환합니다.
    
    Args:
        ws: openpyxl 워크시트 객체
        values: 추가할 값 리스트
        font: 적용할 폰트 스타일 (None이면 기본 폰트)
    
    Returns:
        추가된 행의 번호 (1-based)
    """
    ws.append(values)
    cur = ws.max_row
    for ci, v in enumerate(values, 1):
        if v is not None:
            c = ws.cell(row=cur, column=ci)
            # "=" 시작 문자열 → 수식 오인 방지
            if isinstance(v, str) and v.startswith("="):
                c.data_type = 's'
            if font:
                c.font = font
    return cur


def calculate_column_width(text: str, padding: int = 2) -> float:
    """텍스트 길이에 기반한 열 너비를 계산합니다.
    
    Args:
        text: 열에 들어갈 텍스트
        padding: 추가 패딩 (기본값: 2)
    
    Returns:
        계산된 열 너비
    """
    if not text:
        return 8.0  # 기본 열 너비
    # 한글 문자는 너비가 더 크므로 가중치 적용
    korean_chars = sum(1 for c in text if '\uAC00' <= c <= '\uD7A3')
    english_chars = len(text) - korean_chars
    return (english_chars * 1.0 + korean_chars * 1.5) + padding


def auto_fit_columns(ws: Any, max_width: float = 50.0) -> None:
    """워크시트의 모든 열을 자동으로 맞춥니다.
    
    Args:
        ws: openpyxl 워크시트 객체
        max_width: 최대 열 너비 (기본값: 50.0)
    """
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            if cell.value:
                cell_length = len(str(cell.value))
                if cell_length > max_length:
                    max_length = cell_length
        adjusted_width = min(max_length + 2, max_width)
        ws.column_dimensions[column_letter].width = adjusted_width
