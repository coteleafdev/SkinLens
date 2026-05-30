"""
routers/logs.py — 로그 조회·다운로드 (관리자·분석가 전용)

GET /v3/logs
GET /v3/logs/download
"""
from __future__ import annotations

import os
import tempfile
import logging
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.cli.execution_history import ExecutionHistoryDB
from src.server.deps import get_db
from src.server.deps import get_current_customer, log, require_roles

router = APIRouter(prefix="/v3/logs", tags=["logs"])

_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@router.get("/download", response_model=None)
async def download_logs(
    level: Optional[str] = None,
    hours: Optional[int] = None,
    format: str = "csv",
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """로그를 파일로 다운로드 (관리자·분석가 전용).

    Args:
        level:  필터링할 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        hours:  최근 N시간 내의 로그만 다운로드
        format: 출력 형식 (csv, json)
    """
    require_roles("admin", "analyst")(current_customer)

    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'json'")
    if level and level not in _VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {_VALID_LEVELS}")

    try:
        suffix = f".{format}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
            temp_path = f.name

        count = (
            db.export_logs_to_csv(temp_path, level=level, hours=hours)
            if format == "csv"
            else db.export_logs_to_json(temp_path, level=level, hours=hours)
        )

        if count == 0:
            os.unlink(temp_path)
            raise HTTPException(status_code=404, detail="No logs found matching criteria")

        media_type = "text/csv" if format == "csv" else "application/json"
        filename   = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"

        response = FileResponse(path=temp_path, media_type=media_type, filename=filename)

        # Cleanup temp file after response is sent
        import atexit
        atexit.register(lambda: os.unlink(temp_path) if os.path.exists(temp_path) else None)

        return response

    except HTTPException:
        raise
    except Exception as e:
        log.error("로그 다운로드 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to download logs")


@router.get("", response_model=None)
async def get_logs(
    level: Optional[str] = None,
    limit: int = 100,
    hours: Optional[int] = None,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """로그를 JSON으로 조회 (관리자·분석가 전용).

    Args:
        level: 필터링할 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        limit: 조회할 레코드 수 (기본 100, 최대 1000)
        hours: 최근 N시간 내의 로그만 조회
    """
    require_roles("admin", "analyst")(current_customer)

    if level and level not in _VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {_VALID_LEVELS}")
    limit = max(1, min(limit, 1000))

    try:
        logs = db.get_logs(level=level, limit=limit, hours=hours)
        return {"logs": logs, "count": len(logs)}
    except Exception as e:
        log.error("로그 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve logs")
