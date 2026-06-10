"""
docx_utils.py — Word 파일 처리 유틸리티 모듈

python-docx를 사용한 Word 파일 생성 및 스타일링에 대한
재사용 가능한 유틸리티 함수를 제공합니다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False


def create_document() -> Any:
    """새로운 Word 문서를 생성합니다.
    
    Returns:
        Document 객체 (python-docx 라이브러리가 없는 경우 None)
    """
    if not _DOCX_AVAILABLE:
        return None
    return Document()


def add_heading(
    doc: Any,
    text: str,
    level: int = 1,
    alignment: str = "left"
) -> None:
    """문서에 제목을 추가합니다.
    
    Args:
        doc: Document 객체
        text: 제목 텍스트
        level: 제목 레벨 (1-3)
        alignment: 정렬 (left, center, right)
    """
    if not _DOCX_AVAILABLE or doc is None:
        return
    
    heading = doc.add_heading(text, level=level)
    
    if alignment == "center":
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif alignment == "right":
        heading.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    else:
        heading.alignment = WD_ALIGN_PARAGRAPH.LEFT


def add_paragraph(
    doc: Any,
    text: str,
    bold: bool = False,
    italic: bool = False,
    font_size: Optional[int] = None,
    color: Optional[str] = None
) -> None:
    """문서에 단락을 추가합니다.
    
    Args:
        doc: Document 객체
        text: 단락 텍스트
        bold: 굵게 여부
        italic: 기울임 여부
        font_size: 폰트 크기 (pt)
        color: 텍스트 색상 (RGB hex, 예: "FF0000")
    """
    if not _DOCX_AVAILABLE or doc is None:
        return
    
    paragraph = doc.add_paragraph(text)
    run = paragraph.runs[0]
    
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    if font_size:
        run.font.size = Pt(font_size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def add_table(
    doc: Any,
    data: List[List[Any]],
    headers: Optional[List[str]] = None,
    style: str = "Table Grid"
) -> None:
    """문서에 테이블을 추가합니다.
    
    Args:
        doc: Document 객체
        data: 테이블 데이터 (2D 리스트)
        headers: 헤더 행 (선택)
        style: 테이블 스타일
    """
    if not _DOCX_AVAILABLE or doc is None:
        return
    
    if headers:
        table_data = [headers] + data
    else:
        table_data = data
    
    table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
    table.style = style
    
    for i, row_data in enumerate(table_data):
        row = table.rows[i]
        for j, cell_data in enumerate(row_data):
            row.cells[j].text = str(cell_data)


def add_image(
    doc: Any,
    image_path: str | Path,
    width: Optional[float] = None,
    height: Optional[float] = None
) -> None:
    """문서에 이미지를 추가합니다.
    
    Args:
        doc: Document 객체
        image_path: 이미지 파일 경로
        width: 이미지 너비 (인치)
        height: 이미지 높이 (인치)
    """
    if not _DOCX_AVAILABLE or doc is None:
        return
    
    image_path = Path(image_path)
    if not image_path.exists():
        return
    
    kwargs = {}
    if width:
        kwargs["width"] = Inches(width)
    if height:
        kwargs["height"] = Inches(height)
    
    doc.add_picture(str(image_path), **kwargs)


def add_page_break(doc: Any) -> None:
    """문서에 페이지 나누기를 추가합니다.
    
    Args:
        doc: Document 객체
    """
    if not _DOCX_AVAILABLE or doc is None:
        return
    
    doc.add_page_break()


def save_document(doc: Any, file_path: str | Path) -> bool:
    """문서를 저장합니다.
    
    Args:
        doc: Document 객체
        file_path: 저장 경로
    
    Returns:
        저장 성공 여부
    """
    if not _DOCX_AVAILABLE or doc is None:
        return False
    
    try:
        doc.save(str(file_path))
        return True
    except Exception:
        return False


def generate_word_report(
    title: str,
    original_image_path: str | Path,
    restored_image_path: str | Path,
    measurements: Dict[str, Any],
    overall_score: float,
    perceived_age: Optional[int] = None,
    prescription: Optional[Dict[str, Any]] = None,
    llm_report: Optional[str] = None,
) -> Optional[Document]:
    """피부 분석 보고서를 Word 문서로 생성합니다.
    
    Args:
        title: 보고서 제목
        original_image_path: 원본 이미지 경로
        restored_image_path: 복원 이미지 경로
        measurements: 측정 결과 딕셔너리
        overall_score: 종합 점수
        perceived_age: 인식 나이 (선택)
        prescription: 처방전 정보 (선택)
        llm_report: LLM 소견 (선택)
    
    Returns:
        Document 객체 (실패 시 None)
    """
    if not _DOCX_AVAILABLE:
        return None
    
    doc = create_document()
    if doc is None:
        return None
    
    # 제목
    add_heading(doc, title, level=1, alignment="center")
    
    # 타임스탬프
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y년 %m월 %d일 %H:%M:%S")
    add_paragraph(doc, f"생성일시: {timestamp}", font_size=10)
    add_paragraph(doc, "")  # 빈 줄
    
    # 이미지 섹션
    add_heading(doc, "이미지 비교", level=2)
    
    # 원본 이미지
    add_paragraph(doc, "원본 이미지:", bold=True)
    if Path(original_image_path).exists():
        add_image(doc, original_image_path, width=4.0)
    else:
        add_paragraph(doc, "이미지를 찾을 수 없습니다.", italic=True)
    
    add_paragraph(doc, "")  # 빈 줄
    
    # 복원 이미지
    add_paragraph(doc, "복원 이미지:", bold=True)
    if Path(restored_image_path).exists():
        add_image(doc, restored_image_path, width=4.0)
    else:
        add_paragraph(doc, "이미지를 찾을 수 없습니다.", italic=True)
    
    add_page_break(doc)
    
    # 종합 점수 섹션
    add_heading(doc, "종합 점수", level=2)
    add_paragraph(doc, f"피부건강지수: {overall_score:.1f}", bold=True, font_size=14, color="0070C0")
    
    if perceived_age is not None:
        add_paragraph(doc, f"인식 나이: {perceived_age}세")
    
    add_paragraph(doc, "")  # 빈 줄
    
    # 측정 결과 섹션
    add_heading(doc, "측정 결과", level=2)
    
    table_data = []
    for key, value in measurements.items():
        if isinstance(value, (int, float)):
            table_data.append([key, f"{value:.1f}"])
        else:
            table_data.append([key, str(value)])
    
    if table_data:
        add_table(doc, table_data, headers=["항목", "값"])
    else:
        add_paragraph(doc, "측정 결과가 없습니다.", italic=True)
    
    # 처방전 섹션
    if prescription:
        add_page_break(doc)
        add_heading(doc, "처방전", level=2)
        
        if isinstance(prescription, dict):
            for key, value in prescription.items():
                add_paragraph(doc, f"{key}: {value}", bold=True)
        else:
            add_paragraph(doc, str(prescription))
    
    # LLM 소견 섹션
    if llm_report:
        add_page_break(doc)
        add_heading(doc, "LLM 소견", level=2)
        add_paragraph(doc, llm_report)
    
    return doc
