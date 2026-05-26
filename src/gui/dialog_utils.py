"""
dialog_utils.py — 다이얼로그 유틸리티 모듈

환경 변수 설정, 경로 준비, 로깅, 데이터 변환, 라벨링 유틸리티 함수를 제공합니다.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from PySide6.QtWidgets import QDialog

from src.scoring.skin_scoring import get_measurement_categories

log = logging.getLogger(__name__)

# 모듈 임포트 시 한 번만 평가 — 매 _dlog 호출마다 os.environ 조회하던 비효율 제거
_DEBUG_ENABLED: bool = (
    os.environ.get("AI_SKIN_MEASUREMENT_DEBUG", "").strip().lower()
    in ("1", "true", "yes", "on")
)

# 다이얼로그/스레드/워커 추적용 전역 리스트
_OPEN_COMPARE_DIALOGS: list[QDialog] = []
_COMPARE_THREADS: list = []
_COMPARE_WORKERS: list = []


def close_all_compare_dialogs() -> None:
    """열려 있는 모든 비교 다이얼로그를 닫습니다."""
    for dlg in list(_OPEN_COMPARE_DIALOGS):  # 복사본 사용하여 순회
        try:
            dlg.reject()  # reject로 닫기
            dlg.deleteLater()  # 삭제 예약
        except Exception as e:
            log.debug("다이얼로그 정리 실패: %s", e)
    _OPEN_COMPARE_DIALOGS.clear()  # 리스트 비우기


def _env_debug_enabled() -> bool:
    return _DEBUG_ENABLED


def _env_ref_stat_enabled() -> bool:
    v = os.environ.get("AI_SKIN_MEASUREMENT_REF_STAT", "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def _analysis_max_side() -> int:
    """0 이면 리사이즈 안 함."""
    raw = os.environ.get("AI_SKIN_ANALYSIS_MAX_SIDE", "1024").strip()
    if not raw or raw.lower() in ("0", "none", "off"):
        return 0
    try:
        return max(256, int(raw))
    except ValueError as e:
        log.debug("max_side 파싱 실패: %s, 기본값 1600 사용", e)
        return 1600


def _analysis_hard_timeout_seconds() -> int:
    """전체 비교 분석 hard timeout(초). 0이면 비활성."""
    raw = os.environ.get("AI_SKIN_MEASUREMENT_HARD_TIMEOUT_SEC", "240").strip()
    if not raw or raw.lower() in ("0", "none", "off"):
        return 0
    try:
        return max(30, int(raw))
    except ValueError as e:
        log.debug("ref_stat_age 파싱 실패: %s, 기본값 240 사용", e)
        return 240


def _prepare_analysis_path(
    src: Path,
    tag: str,
    max_side: int,
    *,
    t0: float,
) -> tuple[str, Optional[Path]]:
    """긴 변이 max_side 초과일 때만 임시 PNG 로 축소(원본·보정 동일 해상도 전제로 양쪽에 동일 적용)."""
    if max_side <= 0:
        return str(src.resolve()), None
    import cv2
    from src.scoring.skin_scoring import _imread_bgr

    p = str(src.resolve())
    img = _imread_bgr(p)  # 한글 경로 처리를 위해 _imread_bgr 사용
    if img is None:
        return p, None
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return p, None
    scale = max_side / float(m)
    nw = max(8, int(round(w * scale)))
    nh = max(8, int(round(h * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    fd, tmp = tempfile.mkstemp(suffix="_skin_an.png", prefix=f"{tag}_")
    os.close(fd)
    tpath = Path(tmp)
    cv2.imwrite(str(tpath), resized)
    _dlog(
        f"분석용 리사이즈 {src.name}: {w}×{h} → {nw}×{nh} (max_side={max_side}) temp={tpath.name}",
        t0=t0,
    )
    return str(tpath), tpath


def _dlog(msg: str, *, t0: float) -> None:
    """터미널 추적용(옵션) + logging.debug 항상."""
    elapsed = time.perf_counter() - t0
    line = f"[skin_measurement_chart +{elapsed:.2f}s] {msg}"
    log.debug("%s", line)
    if _env_debug_enabled():
        print(line, flush=True)


def _flatten_measurement_keys() -> List[str]:
    keys: List[str] = []
    for _, ks in get_measurement_categories():
        keys.extend(ks)
    return keys


def _numeric_value(raw: Any) -> float:
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        log.debug("점수 파싱 실패: %s, 기본값 0.0 사용", e)
        return 0.0


def _short_label(key: str) -> str:
    """측정항목 키에서 한글 라벨을 반환합니다. config.json에서 동적 로드합니다."""
    # prescription_calculator에서 디스플레이 이름 읽기 (동적)
    try:
        from src.prescription import get_measurement_display_names
        display_names = get_measurement_display_names()
        if key in display_names:
            return display_names[key]
    except Exception:
        log.debug(f"display name 파싱 실패: {key}")

    # 폴백: config_parser에서 디스플레이 이름 읽기
    try:
        from src.skin.core.config_parser import get_display_names
        display_names = get_display_names()
        if key in display_names:
            display = display_names[key]
            # 괄호 안의 영문 제거
            import re
            display = re.sub(r"\s*\(.*?\)", "", display)
            return display
    except Exception:
        log.debug(f"display name 파싱 실패: {key}")

    # 템플릿이 없는 경우 키 자체 반환
    return key
