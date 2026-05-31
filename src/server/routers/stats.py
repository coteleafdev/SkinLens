"""
routers/stats.py — 통계 조회 API

GET  /v1/stats/analysis
GET  /v1/stats/model-performance
GET  /v1/stats/score-trends
GET  /v1/stats/llm-api
GET  /v1/stats/image-metadata
GET  /v1/stats/errors
POST /v1/stats/errors/{error_id}/resolve
GET  /v1/stats/system-health
GET  /v1/stats/summary
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from src.cli.execution_history import ExecutionHistoryDB
from src.utils.config import get_db_path_from_env
from src.server.deps import get_db
from src.server.deps import (
    check_customer_access,
    filter_sensitive_data,
    get_current_customer,
    require_current_customer,
    limiter,
    log,
    log_audit,
)

router = APIRouter(prefix="/v1/stats", tags=["stats"])


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────

def _ctx(current_customer: Optional[Dict[str, Any]], db: ExecutionHistoryDB, endpoint: str = "", request = None):
    """(user_role, actor_id, db) 튜플 반환. 인증이 필요한 경우 체크."""
    if current_customer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    user_role = current_customer.get("role", "customer")
    # Stats 엔드포인트는 admin/analyst 전용
    if user_role not in ("admin", "analyst"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")
    actor_id  = current_customer.get("sub")
    return user_role, actor_id, db


def _audit_ok(db, actor_id, target_id, endpoint, method, user_role, request):
    log_audit(db=db, actor_customer_id=actor_id, target_customer_id=target_id,
              endpoint=endpoint, method=method, user_role=user_role,
              request=request, success=True)


def _audit_fail(db, actor_id, target_id, endpoint, method, user_role, request, msg):
    log_audit(db=db, actor_customer_id=actor_id, target_customer_id=target_id,
              endpoint=endpoint, method=method, user_role=user_role,
              request=request, success=False, error_message=msg)


def _check_access_or_403(actor_id, target_id, user_role, endpoint, request, db):
    if not check_customer_access(actor_id, target_id, user_role):
        _audit_fail(db, actor_id, target_id, endpoint, "GET", user_role, request, "Unauthorized access")
        raise HTTPException(status_code=403, detail="Access denied")


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@router.get("/analysis", response_model=None)
@limiter.limit("30/minute")
async def get_analysis_stats(
    days: int = 7,
    customer_id: Optional[str] = None,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """분석 통계 조회."""
    ep = "/v1/stats/analysis"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)

    if customer_id and current_customer:
        _check_access_or_403(actor_id, customer_id, user_role, ep, request, db)

    try:
        rows     = db.get_analysis_stats(days=days, customer_id=customer_id)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, customer_id, ep, "GET", user_role, request)
        return {"stats": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("분석 통계 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, customer_id, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve analysis stats")


@router.get("/model-performance", response_model=None)
@limiter.limit("30/minute")
async def get_model_performance(
    model_type: Optional[str] = None,
    hours: Optional[int] = None,
    limit: int = 100,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """모델 성능 조회."""
    ep = "/v1/stats/model-performance"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)
    try:
        rows     = db.get_model_performance(model_type=model_type, hours=hours, limit=limit)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, None, ep, "GET", user_role, request)
        return {"performance": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("모델 성능 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, None, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve model performance")


@router.get("/score-trends", response_model=None)
@limiter.limit("30/minute")
async def get_score_trends(
    customer_id: Optional[str] = None,
    days: int = 30,
    limit: int = 100,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """점수 추이 조회."""
    ep = "/v1/stats/score-trends"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)

    if customer_id and current_customer:
        _check_access_or_403(actor_id, customer_id, user_role, ep, request, db)

    try:
        rows     = db.get_score_trends(customer_id=customer_id, days=days, limit=limit)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, customer_id, ep, "GET", user_role, request)
        return {"trends": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("점수 추이 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, customer_id, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve score trends")


@router.get("/llm-api", response_model=None)
@limiter.limit("30/minute")
async def get_llm_api_stats(
    customer_id: Optional[str] = None,
    days: int = 30,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """LLM API 통계 조회."""
    ep = "/v1/stats/llm-api"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)

    if customer_id and current_customer:
        _check_access_or_403(actor_id, customer_id, user_role, ep, request, db)

    try:
        rows     = db.get_llm_api_stats(customer_id=customer_id, days=days)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, customer_id, ep, "GET", user_role, request)
        return {"stats": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("LLM API 통계 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, customer_id, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve LLM API stats")


@router.get("/image-metadata", response_model=None)
@limiter.limit("30/minute")
async def get_image_metadata(
    analysis_id: Optional[int] = None,
    image_type: Optional[str] = None,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """이미지 메타데이터 조회."""
    ep = "/v1/stats/image-metadata"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)
    try:
        rows     = db.get_image_metadata(analysis_id=analysis_id, image_type=image_type)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, None, ep, "GET", user_role, request)
        return {"metadata": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("이미지 메타데이터 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, None, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve image metadata")


@router.get("/errors", response_model=None)
@limiter.limit("30/minute")
async def get_errors(
    resolved: Optional[bool] = None,
    severity: Optional[str] = None,
    days: int = 30,
    limit: int = 100,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """에러 조회."""
    ep = "/v1/stats/errors"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)
    try:
        rows     = db.get_errors(resolved=resolved, severity=severity, days=days, limit=limit)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, None, ep, "GET", user_role, request)
        return {"errors": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("에러 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, None, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve errors")


@router.post("/errors/{error_id}/resolve", response_model=None)
@limiter.limit("10/minute")
async def resolve_error(
    error_id: int,
    resolution_note: str = Form(...),
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """에러 해결 표시 (관리자 전용)."""
    ep = f"/v1/stats/errors/{error_id}/resolve"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)

    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user_role != "admin":
        _audit_fail(db, actor_id, None, ep, "POST", user_role, request, "Unauthorized access attempt")
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        db.resolve_error(error_id, resolution_note)
        if current_customer:
            _audit_ok(db, actor_id, None, ep, "POST", user_role, request)
        return {"message": "Error resolved successfully", "error_id": error_id}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("에러 해결 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, None, ep, "POST", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to resolve error")


@router.get("/system-health", response_model=None)
@limiter.limit("30/minute")
async def get_system_health(
    hours: int = 24,
    limit: int = 100,
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """시스템 헬스 조회."""
    ep = "/v1/stats/system-health"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)
    try:
        rows     = db.get_system_health(hours=hours, limit=limit)
        filtered = [filter_sensitive_data(r, user_role) for r in rows]
        if current_customer:
            _audit_ok(db, actor_id, None, ep, "GET", user_role, request)
        return {"health": filtered, "count": len(filtered)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("시스템 헬스 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, None, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve system health")


@router.get("/summary", response_model=None)
@limiter.limit("10/minute")
async def get_stats_summary(
    request: Request = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
):
    """전체 통계 요약."""
    ep = "/v1/stats/summary"
    user_role, actor_id, db = _ctx(current_customer, db, ep, request)
    try:
        today_stats   = db.get_analysis_stats(days=1)
        recent_errors = db.get_errors(days=7, limit=10)
        recent_health = db.get_system_health(hours=1, limit=1)
        llm_stats  = db.get_llm_api_stats(days=1)

        summary = {
            "today_analyses":          len(today_stats),
            "recent_errors":           len(recent_errors),
            "recent_errors_critical":  sum(1 for e in recent_errors if e.get("severity") == "critical"),
            "system_health":           recent_health[0] if recent_health else None,
            "llm_api_calls_today":     len(llm_stats),
            "llm_cost_today":          sum(s.get("estimated_cost_usd", 0) for s in llm_stats),
        }
        filtered = filter_sensitive_data(summary, user_role)
        if current_customer:
            _audit_ok(db, actor_id, None, ep, "GET", user_role, request)
        return filtered
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("통계 요약 조회 실패: %s", e)
        if current_customer:
            _audit_fail(db, actor_id, None, ep, "GET", user_role, request, str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve stats summary")
