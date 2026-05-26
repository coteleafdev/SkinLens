"""
routers/admin.py — 관리자 전용 API

GET  /v3/admin/audit-logs
GET  /v3/admin/db/metrics
GET  /v3/admin/audit/summary
GET  /v3/health/db          ← 관리자·분석가 전용 (prefix 없음)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.cli.execution_history import ExecutionHistoryDB
from src.utils.config import get_db_path_from_env
from src.server.deps import (
    get_current_customer,
    get_db,
    limiter,
    require_roles,
    log,
    log_audit,
)

router = APIRouter(tags=["admin"])



# ── 감사 로그 ─────────────────────────────────────────────────────────────

@router.get("/v3/admin/audit-logs")
async def get_audit_logs(
    actor_customer_id:  Optional[str] = None,
    target_customer_id: Optional[str] = None,
    days:  int = 30,
    limit: int = 100,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """감사 로그 조회 (관리자 전용)."""
    ep = "/v3/admin/audit-logs"
    role = require_roles("admin")(current_customer)
    actor_id = current_customer.get("sub")
    try:
        logs = db.get_audit_logs(
            actor_customer_id=actor_customer_id,
            target_customer_id=target_customer_id,
            days=days, limit=limit,
        )
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request, success=True)
        return {"audit_logs": logs, "count": len(logs)}
    except Exception as e:
        log.error("감사 로그 조회 실패: %s", e)
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request,
                  success=False, error_message=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve audit logs")


# ── DB 헬스 (관리자·분석가) ───────────────────────────────────────────────

@router.get("/v3/health/db")
async def check_db_health(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """DB 상태 확인 (관리자·분석가 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")
    try:
        db = ExecutionHistoryDB(get_db_path_from_env())
        health = db.check_health()
        return JSONResponse(content=health, status_code=200 if health.get("healthy") else 503)
    except Exception as e:
        log.error("DB health check failed: %s", e)
        return JSONResponse(content={"healthy": False, "error": str(e)}, status_code=503)


# ── DB 메트릭 ─────────────────────────────────────────────────────────────

@router.get("/v3/admin/db/metrics")
@limiter.limit("10/minute")
async def get_db_metrics(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """DB 성능 메트릭 조회 (관리자 전용)."""
    ep = "/v3/admin/db/metrics"
    role = require_roles("admin")(current_customer)
    actor_id = current_customer.get("sub")
    try:
        eh       = db.check_health()
        metrics  = {
            "execution_history": {
                "healthy":        eh.get("healthy"),
                "file_size_mb":   eh.get("file_size_mb"),
                "file_size_bytes": eh.get("file_size_bytes"),
                "row_counts":     eh.get("row_counts"),
                "db_path":        eh.get("db_path"),
            },
            "analysis_results": {"healthy": True,  "note": "Analysis results DB health check not implemented yet"},
            "supabase":         {"healthy": True,  "note": "Supabase health check not implemented yet"},
            "timestamp": datetime.now().isoformat(),
        }
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request, success=True)
        return metrics
    except Exception as e:
        log.error("DB metrics retrieval failed: %s", e)
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request,
                  success=False, error_message=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve DB metrics")


# ── 감사 요약 ─────────────────────────────────────────────────────────────

@router.get("/v3/admin/audit/summary")
@limiter.limit("10/minute")
async def get_audit_summary(
    days: int = 30,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """감사 로그 요약 분석 (관리자 전용)."""
    ep = "/v3/admin/audit/summary"
    role = require_roles("admin")(current_customer)
    actor_id = current_customer.get("sub")
    try:
        rows = db.get_audit_logs(days=days, limit=1000)

        total   = len(rows)
        unique  = len({r.get("actor_customer_id") for r in rows if r.get("actor_customer_id")})
        failed  = sum(1 for r in rows if not r.get("success", True))

        ep_counts: Dict[str, int] = {}
        ip_fail:   Dict[str, int] = {}
        for r in rows:
            ep_counts[r.get("endpoint", "unknown")] = ep_counts.get(r.get("endpoint", "unknown"), 0) + 1
            if not r.get("success", True):
                ip = r.get("ip_address", "unknown")
                ip_fail[ip] = ip_fail.get(ip, 0) + 1

        top_eps    = sorted(ep_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        suspicious = [
            {"type": "multiple_failures", "ip_address": ip, "failure_count": cnt}
            for ip, cnt in ip_fail.items() if cnt > 10
        ]

        summary = {
            "total_access":       total,
            "unique_users":       unique,
            "failed_access":      failed,
            "success_rate":       round((total - failed) / total * 100, 2) if total > 0 else 100,
            "top_endpoints":      [{"endpoint": e, "count": c} for e, c in top_eps],
            "suspicious_activity": suspicious,
            "period_days":        days,
        }
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request, success=True)
        return summary
    except Exception as e:
        log.error("Audit summary retrieval failed: %s", e)
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request,
                  success=False, error_message=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve audit summary")
