"""
routers/customer.py — 인증된 고객 전용 API (자기 데이터만 접근)

GET    /v1/customer/my/trends
GET    /v1/customer/my/analysis
GET    /v1/customer/my/errors
DELETE /v1/customer/my/data
GET    /v1/customer/my/data/export
GET    /v1/customer/my/analyses
GET    /v1/customer/my/analyses/{analysis_id}
GET    /v1/customer/my/analyses/{analysis_id}/image/{image_type}
GET    /v1/customer/my/analyses/compare
GET    /v1/customer/my/recommendations
POST   /v1/customer/my/analyses/{analysis_id}/bookmark
DELETE /v1/customer/my/analyses/{analysis_id}/bookmark
GET    /v1/customer/my/bookmarks
GET    /v1/customer/my/notifications/settings
PUT    /v1/customer/my/notifications/settings
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path
from pydantic import BaseModel

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


# ── Pydantic Models ─────────────────────────────────────────────────────────────

class BookmarkRequest(BaseModel):
    notes: Optional[str] = None


class NotificationSettingsRequest(BaseModel):
    analysis_complete: Optional[bool] = None
    score_improvement: Optional[bool] = None
    care_reminder: Optional[bool] = None
    marketing: Optional[bool] = None
    reminder_hours: Optional[int] = None


class CompareRequest(BaseModel):
    analysis_id_1: int
    analysis_id_2: int


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


@router.get("/analyses", response_model=None)
async def get_my_analyses(
    limit: int = 50,
    offset: int = 0,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """인증된 고객의 전체 분석 기록 목록 조회."""
    ep = "/v1/customer/my/analyses"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        analyses = db.get_customer_analyses(customer_id)
        
        # 페이지네이션 적용
        paginated_analyses = analyses[offset:offset + limit]
        
        return {
            "analyses": paginated_analyses,
            "total": len(analyses),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        log.error("분석 기록 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve analyses")


@router.get("/analyses/{analysis_id}", response_model=None)
async def get_my_analysis_detail(
    analysis_id: int,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """인증된 고객의 특정 분석 상세 정보 조회."""
    ep = f"/v1/customer/my/analyses/{analysis_id}"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        analysis = db.get_customer_analysis_detail(customer_id, analysis_id)
        
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        log.error("분석 상세 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve analysis detail")


@router.get("/analyses/{analysis_id}/image/{image_type}", response_model=None)
async def get_my_analysis_image(
    analysis_id: int,
    image_type: str,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """인증된 고객의 분석 이미지 다운로드 (original 또는 restored)."""
    ep = f"/v1/customer/my/analyses/{analysis_id}/image/{image_type}"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    # 이미지 타입 검증
    if image_type not in ["original", "restored"]:
        raise HTTPException(status_code=400, detail="Invalid image type. Must be 'original' or 'restored'")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        analysis = db.get_customer_analysis_detail(customer_id, analysis_id)
        
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        # 이미지 경로 결정
        if image_type == "original":
            image_path = analysis["original_image_path"]
        else:
            image_path = analysis["restored_image_path"]
        
        # 파일 존재 확인
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image file not found")
        
        # 파일명 추출
        filename = os.path.basename(image_path)
        
        return FileResponse(
            image_path,
            media_type="image/jpeg",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("이미지 다운로드 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to download image")


@router.post("/analyses/compare", response_model=None)
async def compare_analyses(
    request_data: CompareRequest,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """두 분석 결과 비교."""
    ep = "/v1/customer/my/analyses/compare"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        
        # 두 분석 결과 조회
        analysis_1 = db.get_customer_analysis_detail(customer_id, request_data.analysis_id_1)
        analysis_2 = db.get_customer_analysis_detail(customer_id, request_data.analysis_id_2)
        
        if analysis_1 is None or analysis_2 is None:
            raise HTTPException(status_code=404, detail="One or both analyses not found")
        
        # 점수 비교
        result_1 = analysis_1.get("json_result", {})
        result_2 = analysis_2.get("json_result", {})
        
        internal_1 = result_1.get("internal_analysis", {}).get("restored", {})
        internal_2 = result_2.get("internal_analysis", {}).get("restored", {})
        
        # 주요 점수 추출
        def extract_scores(internal):
            return {
                "overall_score": internal.get("overall_score", 0),
                "melasma_score": internal.get("melasma_score", 0),
                "redness_score": internal.get("redness_score", 0),
                "wrinkle_score": internal.get("wrinkle_score", 0),
                "pore_score": internal.get("pore_score", 0),
            }
        
        scores_1 = extract_scores(internal_1)
        scores_2 = extract_scores(internal_2)
        
        # 변화 계산
        changes = {}
        for key in scores_1:
            change = scores_2[key] - scores_1[key]
            changes[key] = {
                "before": scores_1[key],
                "after": scores_2[key],
                "change": change,
                "improved": change > 0
            }
        
        return {
            "analysis_1": {
                "id": analysis_1["id"],
                "date": analysis_1["created_at"],
                "scores": scores_1
            },
            "analysis_2": {
                "id": analysis_2["id"],
                "date": analysis_2["created_at"],
                "scores": scores_2
            },
            "changes": changes,
            "overall_improvement": changes["overall_score"]["change"]
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("분석 비교 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to compare analyses")


@router.get("/recommendations", response_model=None)
async def get_my_recommendations(
    analysis_id: Optional[int] = None,
    limit: int = 10,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """맞춤형 제품 추천 조회."""
    ep = "/v1/customer/my/recommendations"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        
        if analysis_id:
            recommendations = db.get_product_recommendations(customer_id, analysis_id, limit)
        else:
            recommendations = db.get_latest_recommendations(customer_id, limit)
        
        return {
            "recommendations": recommendations,
            "total": len(recommendations)
        }
    except Exception as e:
        log.error("제품 추천 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve recommendations")


@router.post("/analyses/{analysis_id}/bookmark", response_model=None)
async def add_bookmark(
    analysis_id: int,
    bookmark_data: BookmarkRequest,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """분석 결과 북마크 추가."""
    ep = f"/v1/customer/my/analyses/{analysis_id}/bookmark"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        
        # 분석 존재 확인
        analysis = db.get_customer_analysis_detail(customer_id, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        success = db.add_bookmark(customer_id, analysis_id, bookmark_data.notes)
        
        if not success:
            raise HTTPException(status_code=409, detail="Already bookmarked")
        
        return {"message": "Bookmark added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("북마크 추가 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to add bookmark")


@router.delete("/analyses/{analysis_id}/bookmark", response_model=None)
async def remove_bookmark(
    analysis_id: int,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """분석 결과 북마크 삭제."""
    ep = f"/v1/customer/my/analyses/{analysis_id}/bookmark"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db.remove_bookmark(customer_id, analysis_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Bookmark not found")
        
        return {"message": "Bookmark removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("북마크 삭제 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to remove bookmark")


@router.get("/bookmarks", response_model=None)
async def get_my_bookmarks(
    limit: int = 50,
    offset: int = 0,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """북마크된 분석 목록 조회."""
    ep = "/v1/customer/my/bookmarks"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        bookmarks = db.get_bookmarks(customer_id, limit, offset)
        
        return {
            "bookmarks": bookmarks,
            "total": len(bookmarks),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        log.error("북마크 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve bookmarks")


@router.get("/notifications/settings", response_model=None)
async def get_notification_settings(
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """알림 설정 조회."""
    ep = "/v1/customer/my/notifications/settings"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        settings = db.get_notification_settings(customer_id)
        return settings
    except Exception as e:
        log.error("알림 설정 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve notification settings")


@router.put("/notifications/settings", response_model=None)
async def update_notification_settings(
    settings_data: NotificationSettingsRequest,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    request: Request = None,
):
    """알림 설정 업데이트."""
    ep = "/v1/customer/my/notifications/settings"
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        
        # 제공된 필드만 업데이트
        success = db.update_notification_settings(
            customer_id=customer_id,
            analysis_complete=settings_data.analysis_complete,
            score_improvement=settings_data.score_improvement,
            care_reminder=settings_data.care_reminder,
            marketing=settings_data.marketing,
            reminder_hours=settings_data.reminder_hours,
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        return {"message": "Notification settings updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("알림 설정 업데이트 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update notification settings")
