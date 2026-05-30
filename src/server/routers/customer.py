"""
routers/customer.py — 인증된 고객 전용 API (자기 데이터만 접근)

GET    /v1/customer/my/trends
GET    /v1/customer/my/analysis
GET    /v1/customer/my/errors
DELETE /v1/customer/my/data
GET    /v1/customer/my/data/export
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
import logging
from datetime import datetime
from typing import Any, Dict

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from src.cli.execution_history import ExecutionHistoryDB
from src.utils.config import get_db_path_from_env
from src.server.deps import get_db
from src.server.deps import (
    filter_sensitive_data,
    get_current_customer,
    log,
    log_audit,
    validate_customer_id_match,
)
from src.db.skin_analysis_db import SkinAnalysisDB

router = APIRouter(prefix="/v1/customer/my", tags=["customer"])


def _ctx(current_customer: Dict[str, Any], db: ExecutionHistoryDB):
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    user_role   = current_customer.get("role", "customer")
    # JWT의 customer_id와 실제 요청 customer_id가 일치하는지 검증
    validate_customer_id_match(current_customer, customer_id)
    return customer_id, user_role, db


def _audit(db, cid, ep, method, role, request, *, ok: bool, error: str = ""):
    log_audit(
        db=db, actor_customer_id=cid, target_customer_id=cid,
        endpoint=ep, method=method, user_role=role,
        request=request, success=ok,
        error_message=error if not ok else None,
    )


@router.get("/trends", response_model=None)
async def get_my_score_trends(
    days: int = 30,
    limit: int = 100,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """인증된 고객의 점수 추이 조회."""
    ep = "/v1/customer/my/trends"
    cid, role, db = _ctx(current_customer, db)
    try:
        rows     = db.get_score_trends(customer_id=cid, days=days, limit=limit)
        filtered = [filter_sensitive_data(r, role) for r in rows]
        _audit(db, cid, ep, "GET", role, request, ok=True)
        return {"trends": filtered, "count": len(filtered)}
    except Exception as e:
        log.error("점수 추이 조회 실패: %s", e)
        _audit(db, cid, ep, "GET", role, request, ok=False, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve score trends")


@router.get("/analysis", response_model=None)
async def get_my_analysis_stats(
    days: int = 7,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """인증된 고객의 분석 통계 조회."""
    ep = "/v1/customer/my/analysis"
    cid, role, db = _ctx(current_customer, db)
    try:
        rows     = db.get_analysis_stats(days=days, customer_id=cid)
        filtered = [filter_sensitive_data(r, role) for r in rows]
        _audit(db, cid, ep, "GET", role, request, ok=True)
        return {"stats": filtered, "count": len(filtered)}
    except Exception as e:
        log.error("분석 통계 조회 실패: %s", e)
        _audit(db, cid, ep, "GET", role, request, ok=False, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve analysis stats")


@router.get("/errors", response_model=None)
async def get_my_errors(
    days: int = 30,
    limit: int = 100,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """인증된 고객의 에러 조회."""
    ep = "/v1/customer/my/errors"
    cid, role, db = _ctx(current_customer, db)
    try:
        rows     = db.get_errors(customer_id=cid, days=days, limit=limit)
        filtered = [filter_sensitive_data(r, role) for r in rows]
        _audit(db, cid, ep, "GET", role, request, ok=True)
        return {"errors": filtered, "count": len(filtered)}
    except Exception as e:
        log.error("에러 조회 실패: %s", e)
        _audit(db, cid, ep, "GET", role, request, ok=False, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve errors")


@router.delete("/data", response_model=None)
async def delete_my_data(
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """인증된 고객의 모든 데이터 삭제 (GDPR 준수)."""
    ep = "/v1/customer/my/data"
    cid, role, db = _ctx(current_customer, db)
    try:
        deleted = db.delete_customer_data(cid)
        _audit(db, cid, ep, "DELETE", role, request, ok=True)
        return {"message": "Data deleted successfully", "deleted_records": deleted}
    except Exception as e:
        log.error("데이터 삭제 실패: %s", e)
        _audit(db, cid, ep, "DELETE", role, request, ok=False, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete data")


@router.get("/data/export")
async def export_my_data(
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """인증된 고객의 모든 데이터 내보내기 (ZIP)."""
    ep = "/v1/customer/my/data/export"
    cid, role, db = _ctx(current_customer, db)
    try:
        temp_dir  = tempfile.mkdtemp()
        json_file = os.path.join(temp_dir, f"customer_data_{cid}.json")
        db.export_customer_data(cid, json_file)

        zip_file = os.path.join(temp_dir, f"customer_data_{cid}.zip")
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.write(json_file, os.path.basename(json_file))

        _audit(db, cid, ep, "GET", role, request, ok=True)

        response = FileResponse(
            zip_file,
            media_type="application/zip",
            filename=f"customer_data_{cid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        )

        # Cleanup temp directory after response is sent
        import atexit
        atexit.register(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        return response
    except Exception as e:
        log.error("데이터 내보내기 실패: %s", e)
        _audit(db, cid, ep, "GET", role, request, ok=False, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to export data")


@router.get("/preferences", response_model=None)
async def get_my_preferences(
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """인증된 고객의 설정 조회."""
    ep = "/v1/customer/my/preferences"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    user_role = current_customer.get("role", "customer")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        preferences = db.get_user_preferences(customer_id)
        if preferences is None:
            # 기본 설정 반환
            preferences = {
                "customer_id": customer_id,
                "language": "ko",
                "timezone": "Asia/Seoul",
            }
        return preferences
    except Exception as e:
        log.error("설정 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve preferences")


@router.put("/preferences/language", response_model=None)
async def set_my_language(
    language: str,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """인증된 고객의 언어 설정."""
    ep = "/v1/customer/my/preferences/language"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    # 지원하는 언어 확인
    from src.i18n import Translator
    if language not in Translator.SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        db.set_user_language(customer_id, language)
        return {"message": "Language updated successfully", "language": language}
    except Exception as e:
        log.error("언어 설정 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update language")


@router.put("/preferences/timezone", response_model=None)
async def set_my_timezone(
    timezone: str,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """인증된 고객의 시간대 설정."""
    ep = "/v1/customer/my/preferences/timezone"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        db.set_user_timezone(customer_id, timezone)
        return {"message": "Timezone updated successfully", "timezone": timezone}
    except Exception as e:
        log.error("시간대 설정 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update timezone")
