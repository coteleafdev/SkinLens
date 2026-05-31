"""
routers/admin.py — 관리자 전용 API

GET  /v1/admin/audit-logs
GET  /v1/admin/db/metrics
GET  /v1/admin/audit/summary
GET  /v1/health/db          ← 관리자·분석가 전용 (prefix 없음)
GET  /v1/admin/customers
GET  /v1/admin/customers/{customer_id}
PUT  /v1/admin/customers/{customer_id}/status
DELETE /v1/admin/customers/{customer_id}
GET  /v1/admin/products
POST /v1/admin/products
PUT  /v1/admin/products/{product_id}
DELETE /v1/admin/products/{product_id}
GET  /v1/admin/analyses
DELETE /v1/admin/analyses/{analysis_id}
GET  /v1/admin/active-sessions
DELETE /v1/admin/active-sessions/{session_id}
GET  /v1/admin/anomalies
POST /v1/admin/anomalies/{id}/resolve
GET  /v1/admin/roles
POST /v1/admin/roles
PUT  /v1/admin/customers/{customer_id}/role
GET  /v1/admin/blocked-ips
POST /v1/admin/blocked-ips
DELETE /v1/admin/blocked-ips/{ip_address}
GET  /v1/admin/dashboard/overview
GET  /v1/admin/reports/usage
GET  /v1/admin/reports/revenue
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.cli.execution_history import ExecutionHistoryDB
from src.utils.config import get_db_path_from_env
from src.utils.utils import get_logging_level, set_logging_level
from src.db.skin_analysis_db import SkinAnalysisDB
from src.server.deps import (
    get_current_customer,
    get_db,
    limiter,
    require_roles,
    log,
    log_audit,
)
from functools import lru_cache

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

router = APIRouter(tags=["admin"])


# ── Pydantic Models ─────────────────────────────────────────────────────────────

class CustomerStatusRequest(BaseModel):
    status: str


class ProductCreateRequest(BaseModel):
    product_id: str
    product_name: str
    category: str
    key_ingredients: List[str]
    efficacy: str
    target_skin_types: Optional[List[str]] = None
    target_concerns: Optional[List[str]] = None


class ProductUpdateRequest(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    key_ingredients: Optional[List[str]] = None
    efficacy: Optional[str] = None


class UserRoleRequest(BaseModel):
    role: str


class BlockIPRequest(BaseModel):
    ip_address: str
    reason: Optional[str] = None
    expires_in_hours: Optional[int] = None
    is_permanent: bool = False


# ── 캐싱 ─────────────────────────────────────────────────────────────────────

# 시스템 메트릭 캐시 (TTL: 30초)
_metrics_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 30  # seconds
}


# ── 감사 로그 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/audit-logs")
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
    ep = "/v1/admin/audit-logs"
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
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("감사 로그 조회 실패: %s", e)
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request,
                  success=False, error_message=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve audit logs")


# ── DB 헬스 (관리자·분석가) ───────────────────────────────────────────────

@router.get("/v1/health/db")
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
    except (sqlite3.Error, OSError) as e:  # [FIX P2] 구체적 예외
        log.error("DB health check failed: %s", e)
        return JSONResponse(content={"healthy": False, "error": str(e)}, status_code=503)


# ── DB 메트릭 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/db/metrics")
@limiter.limit("10/minute")
async def get_db_metrics(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """DB 성능 메트릭 조회 (관리자 전용)."""
    ep = "/v1/admin/db/metrics"
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
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("DB metrics retrieval failed: %s", e)
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request,
                  success=False, error_message=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve DB metrics")


# ── 감사 요약 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/audit/summary")
@limiter.limit("10/minute")
async def get_audit_summary(
    days: int = 30,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """감사 로그 요약 분석 (관리자 전용)."""
    ep = "/v1/admin/audit/summary"
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
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("Audit summary retrieval failed: %s", e)
        log_audit(db=db, actor_customer_id=actor_id, target_customer_id=None,
                  endpoint=ep, method="GET", user_role=role, request=request,
                  success=False, error_message=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve audit summary")


# ── 로그 레벨 관리 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/logging/level")
async def get_current_log_level(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    request: Request = None,
):
    """현재 로그 레벨 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        current_level = get_logging_level()
        return {
            "current_level": current_level,
            "available_levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
            "timestamp": datetime.now().isoformat(),
        }
    except (OSError, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("로그 레벨 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve log level")


@router.put("/v1/admin/logging/level")
async def update_log_level(
    level: str,
    persist: bool = False,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """로그 레벨 동적 변경 (관리자 전용).

    Args:
        level: 새로운 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        persist: True이면 config.json에도 저장 (서버 재시작 후에도 유지)
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    ep = "/v1/admin/logging/level"
    actor_id = current_customer.get("sub")

    # 유효한 로그 레벨 검증
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    if level.upper() not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid log level. Must be one of: {', '.join(valid_levels)}"
        )

    try:
        previous_level = get_logging_level()
        set_logging_level(level.upper(), persist=persist)
        new_level = get_logging_level()

        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=None,
            endpoint=ep,
            method="PUT",
            user_role=role,
            request=request,
            success=True
        )

        return {
            "previous_level": previous_level,
            "new_level": new_level,
            "persisted": persist,
            "timestamp": datetime.now().isoformat(),
            "message": f"Log level changed from {previous_level} to {new_level}" + (" (persisted to config.json)" if persist else " (runtime only)")
        }
    except (OSError, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("로그 레벨 변경 실패: %s", e)
        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=None,
            endpoint=ep,
            method="PUT",
            user_role=role,
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to update log level")


# ── 시스템 메트릭 모니터링 ─────────────────────────────────────────────────────

@router.get("/v1/admin/metrics/system")
async def get_system_metrics(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    request: Request = None,
):
    """시스템 메트릭 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    if not PSUTIL_AVAILABLE:
        return {
            "error": "psutil not installed",
            "message": "Install psutil to enable system metrics: pip install psutil",
            "timestamp": datetime.now().isoformat(),
        }

    import time
    current_time = time.time()

    # 캐시 유효성 확인
    if _metrics_cache["data"] and (current_time - _metrics_cache["timestamp"]) < _metrics_cache["ttl"]:
        return _metrics_cache["data"]

    try:
        # CPU 메트릭
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()

        # 메모리 메트릭
        memory = psutil.virtual_memory()
        memory_metrics = {
            "total_gb": memory.total / (1024**3),
            "available_gb": memory.available / (1024**3),
            "used_gb": memory.used / (1024**3),
            "percent": memory.percent,
        }

        # 디스크 메트릭
        disk = psutil.disk_usage('/')
        disk_metrics = {
            "total_gb": disk.total / (1024**3),
            "used_gb": disk.used / (1024**3),
            "free_gb": disk.free / (1024**3),
            "percent": disk.percent,
        }

        # 네트워크 메트릭
        net_io = psutil.net_io_counters()
        network_metrics = {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
        }

        # 프로세스 메트릭
        process = psutil.Process()
        process_metrics = {
            "pid": process.pid,
            "memory_percent": process.memory_percent(),
            "cpu_percent": process.cpu_percent(),
            "num_threads": process.num_threads(),
            "num_fds": process.num_fds() if hasattr(process, 'num_fds') else None,
        }

        result = {
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
            },
            "memory": memory_metrics,
            "disk": disk_metrics,
            "network": network_metrics,
            "process": process_metrics,
            "timestamp": datetime.now().isoformat(),
        }

        # 캐시 저장
        _metrics_cache["data"] = result
        _metrics_cache["timestamp"] = current_time

        return result
    except (OSError, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("시스템 메트릭 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve system metrics")


# ── API 키 관리 ─────────────────────────────────────────────────────────────

@router.post("/v1/admin/api-keys")
async def create_api_key(
    name: str,
    owner_id: str,
    description: Optional[str] = None,
    scopes: Optional[str] = None,  # JSON string
    expires_in_days: Optional[int] = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """API 키 생성 (관리자 전용).

    Args:
        name: API 키 이름
        owner_id: 소유자 ID
        description: 설명
        scopes: 권한 범위 (JSON 문자열, 예: '["read", "write"]')
        expires_in_days: 만료일수
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    ep = "/v1/admin/api-keys"
    actor_id = current_customer.get("sub")

    try:
        # scopes 파싱
        import json
        scopes_list = json.loads(scopes) if scopes else None

        # API 키 생성
        skin_db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        result = skin_db.create_api_key(
            name=name,
            owner_id=owner_id,
            description=description,
            scopes=scopes_list,
            expires_in_days=expires_in_days,
        )

        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=owner_id,
            endpoint=ep,
            method="POST",
            user_role=role,
            request=request,
            success=True
        )

        return result
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("API 키 생성 실패: %s", e)
        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=owner_id,
            endpoint=ep,
            method="POST",
            user_role=role,
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to create API key")


@router.get("/v1/admin/api-keys")
async def list_api_keys(
    owner_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 100,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    request: Request = None,
):
    """API 키 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        skin_db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        api_keys = skin_db.list_api_keys(
            owner_id=owner_id,
            is_active=is_active,
            limit=limit,
        )
        return {"api_keys": api_keys, "count": len(api_keys)}
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("API 키 목록 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve API keys")


@router.delete("/v1/admin/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    reason: Optional[str] = None,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """API 키 폐지 (관리자 전용).

    Args:
        key_id: 폐지할 API 키 ID
        reason: 폐지 사유
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    ep = f"/v1/admin/api-keys/{key_id}"
    actor_id = current_customer.get("sub")

    try:
        skin_db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = skin_db.revoke_api_key(key_id=key_id, reason=reason)

        if not success:
            raise HTTPException(status_code=404, detail="API key not found")

        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=None,
            endpoint=ep,
            method="DELETE",
            user_role=role,
            request=request,
            success=True
        )

        return {"message": "API key revoked successfully", "key_id": key_id}
    except HTTPException:
        raise
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("API 키 폐지 실패: %s", e)
        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=None,
            endpoint=ep,
            method="DELETE",
            user_role=role,
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to revoke API key")


# ── 캐싱 관리 ────────────────────────────────────────────────────────────────

@router.get("/v1/admin/cache/stats")
async def get_cache_stats(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """캐시 통계 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    import time
    current_time = time.time()
    cache_age = current_time - _metrics_cache["timestamp"] if _metrics_cache["timestamp"] else 0
    is_valid = cache_age < _metrics_cache["ttl"]

    return {
        "metrics_cache": {
            "valid": is_valid,
            "age_seconds": cache_age,
            "ttl": _metrics_cache["ttl"],
            "cached": _metrics_cache["data"] is not None,
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/v1/admin/cache/clear")
async def clear_cache(
    cache_type: str = "all",
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """캐시 초기화 (관리자 전용).

    Args:
        cache_type: 초기화할 캐시 타입 (all, metrics, config)
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    ep = "/v1/admin/cache/clear"
    actor_id = current_customer.get("sub")

    cleared_caches = []

    try:
        if cache_type in ("all", "metrics"):
            _metrics_cache["data"] = None
            _metrics_cache["timestamp"] = 0
            cleared_caches.append("metrics")

        if cache_type in ("all", "config"):
            from src.config.config_manager import ConfigManager
            ConfigManager._instance = None
            from src.scoring._breakpoints import _clear_breakpoints_cache
            from src.llm.llm_metadata import clear_metadata_cache
            _clear_breakpoints_cache()
            clear_metadata_cache()
            cleared_caches.append("config")

        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=None,
            endpoint=ep,
            method="POST",
            user_role=role,
            request=request,
            success=True
        )

        return {
            "message": "Cache cleared successfully",
            "cleared_caches": cleared_caches,
            "timestamp": datetime.now().isoformat(),
        }
    except (OSError, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error("캐시 초기화 실패: %s", e)
        log_audit(
            db=db,
            actor_customer_id=actor_id,
            target_customer_id=None,
            endpoint=ep,
            method="POST",
            user_role=role,
            request=request,
            success=False,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to clear cache")


# ── WebSocket 연결 관리 ───────────────────────────────────────────────────────

@router.get("/v1/admin/websocket/stats")
async def get_websocket_stats(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """WebSocket 연결 통계 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        from src.server.routers.websocket import manager
        stats = manager.get_connection_stats()
        return stats
    except Exception as e:
        log.error("WebSocket 통계 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve WebSocket stats")


# ── 작업 큐 관리 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/job-queue/stats")
async def get_job_queue_stats(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """작업 큐 통계 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        from src.server.job_queue import get_job_queue
        queue = get_job_queue()
        stats = queue.get_queue_stats()
        return stats
    except Exception as e:
        log.error("작업 큐 통계 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve job queue stats")


@router.get("/v1/admin/job-queue/{job_id}")
async def get_job_status(
    job_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """작업 상태 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        from src.server.job_queue import get_job_queue
        queue = get_job_queue()
        status = queue.get_job_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="Job not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        log.error("작업 상태 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve job status")


# ── 고객 관리 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/customers")
async def list_customers(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """고객 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        customers = db.list_customers(status=status, limit=limit, offset=offset)
        return {"customers": customers, "total": len(customers)}
    except Exception as e:
        log.error("고객 목록 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve customers")


@router.get("/v1/admin/customers/{customer_id}")
async def get_customer_detail(
    customer_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """고객 상세 정보 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        customer = db.get_customer_profile(customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer
    except HTTPException:
        raise
    except Exception as e:
        log.error("고객 상세 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve customer")


@router.put("/v1/admin/customers/{customer_id}/status")
async def update_customer_status(
    customer_id: str,
    request_data: CustomerStatusRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """고객 상태 변경 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/customers/{customer_id}/status"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.update_customer_status(customer_id, request_data.status)
        
        if not success:
            raise HTTPException(status_code=404, detail="Customer not found")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=customer_id,
            endpoint=ep, method="PUT", user_role=role, request=request, success=True
        )
        return {"message": "Customer status updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("고객 상태 변경 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=customer_id,
            endpoint=ep, method="PUT", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to update customer status")


@router.delete("/v1/admin/customers/{customer_id}")
async def delete_customer(
    customer_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """고객 삭제 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/customers/{customer_id}"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.delete_customer_profile(customer_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Customer not found")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=customer_id,
            endpoint=ep, method="DELETE", user_role=role, request=request, success=True
        )
        return {"message": "Customer deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("고객 삭제 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=customer_id,
            endpoint=ep, method="DELETE", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to delete customer")


# ── 제품 관리 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/products")
async def list_products(
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """제품 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        products = db.list_products(category=category, limit=limit, offset=offset)
        return {"products": products, "total": len(products)}
    except Exception as e:
        log.error("제품 목록 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve products")


@router.post("/v1/admin/products")
async def create_product(
    request_data: ProductCreateRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """제품 생성 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = "/v1/admin/products"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.create_product(
            product_id=request_data.product_id,
            product_name=request_data.product_name,
            category=request_data.category,
            key_ingredients=request_data.key_ingredients,
            efficacy=request_data.efficacy,
            target_skin_types=request_data.target_skin_types,
            target_concerns=request_data.target_concerns,
        )
        
        if not success:
            raise HTTPException(status_code=409, detail="Product ID already exists")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="POST", user_role=role, request=request, success=True
        )
        return {"message": "Product created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("제품 생성 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="POST", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to create product")


@router.put("/v1/admin/products/{product_id}")
async def update_product(
    product_id: str,
    request_data: ProductUpdateRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """제품 정보 업데이트 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/products/{product_id}"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.update_product(
            product_id=product_id,
            product_name=request_data.product_name,
            category=request_data.category,
            key_ingredients=request_data.key_ingredients,
            efficacy=request_data.efficacy,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Product not found or no changes")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="PUT", user_role=role, request=request, success=True
        )
        return {"message": "Product updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("제품 업데이트 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="PUT", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to update product")


@router.delete("/v1/admin/products/{product_id}")
async def delete_product(
    product_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """제품 삭제 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/products/{product_id}"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.delete_product(product_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Product not found")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request, success=True
        )
        return {"message": "Product deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("제품 삭제 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to delete product")


# ── 분석 결과 관리 ─────────────────────────────────────────────────────────

@router.get("/v1/admin/analyses")
async def list_all_analyses(
    limit: int = 100,
    offset: int = 0,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """전체 분석 결과 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        analyses = db.get_recent_analyses(limit=limit)
        return {"analyses": analyses, "total": len(analyses)}
    except Exception as e:
        log.error("분석 결과 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve analyses")


@router.delete("/v1/admin/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: int,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """분석 결과 삭제 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/analyses/{analysis_id}"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.delete_analysis(analysis_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Analysis not found")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request, success=True
        )
        return {"message": "Analysis deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("분석 결과 삭제 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to delete analysis")


# ── 사용자 활동 모니터링 ─────────────────────────────────────────────────────

@router.get("/v1/admin/active-sessions")
async def get_active_sessions(
    limit: int = 100,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """활성 세션 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        sessions = db.get_active_sessions(limit=limit)
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        log.error("활성 세션 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve active sessions")


@router.delete("/v1/admin/active-sessions/{session_id}")
async def terminate_session(
    session_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """세션 강제 종료 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/active-sessions/{session_id}"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.end_session(session_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request, success=True
        )
        return {"message": "Session terminated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("세션 종료 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to terminate session")


@router.get("/v1/admin/anomalies")
async def get_anomalies(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """이상 활동 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        anomalies = db.get_anomalies(status=status, severity=severity, limit=limit)
        return {"anomalies": anomalies, "total": len(anomalies)}
    except Exception as e:
        log.error("이상 활동 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve anomalies")


@router.post("/v1/admin/anomalies/{anomaly_id}/resolve")
async def resolve_anomaly(
    anomaly_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """이상 활동 해결 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/anomalies/{anomaly_id}/resolve"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.resolve_anomaly(anomaly_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Anomaly not found")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="POST", user_role=role, request=request, success=True
        )
        return {"message": "Anomaly resolved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("이상 활동 해결 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="POST", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to resolve anomaly")


# ── 보안 관리 ─────────────────────────────────────────────────────────────

@router.get("/v1/admin/roles")
async def list_roles(
    role: Optional[str] = None,
    limit: int = 100,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """역할별 사용자 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    admin_role = current_customer.get("role", "customer")
    if admin_role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        if role:
            users = db.list_users_by_role(role=role, limit=limit)
        else:
            # 모든 역할의 사용자 반환
            users = []
            for r in ["admin", "analyst", "customer"]:
                users.extend(db.list_users_by_role(role=r, limit=limit))
        return {"users": users, "total": len(users)}
    except Exception as e:
        log.error("역할 목록 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve roles")


@router.put("/v1/admin/customers/{customer_id}/role")
async def set_user_role(
    customer_id: str,
    request_data: UserRoleRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """사용자 역할 설정 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/customers/{customer_id}/role"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        db_skin.set_user_role(customer_id=customer_id, role=request_data.role, granted_by=actor_id)

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=customer_id,
            endpoint=ep, method="PUT", user_role=role, request=request, success=True
        )
        return {"message": "User role updated successfully"}
    except Exception as e:
        log.error("역할 설정 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=customer_id,
            endpoint=ep, method="PUT", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to update user role")


@router.get("/v1/admin/blocked-ips")
async def get_blocked_ips(
    limit: int = 100,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """차단된 IP 목록 조회 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        blocked_ips = db.get_blocked_ips(limit=limit)
        return {"blocked_ips": blocked_ips, "total": len(blocked_ips)}
    except Exception as e:
        log.error("차단된 IP 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve blocked IPs")


@router.post("/v1/admin/blocked-ips")
async def block_ip(
    request_data: BlockIPRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """IP 차단 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = "/v1/admin/blocked-ips"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        db_skin.block_ip(
            ip_address=request_data.ip_address,
            reason=request_data.reason,
            blocked_by=actor_id,
            expires_in_hours=request_data.expires_in_hours,
            is_permanent=request_data.is_permanent,
        )

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="POST", user_role=role, request=request, success=True
        )
        return {"message": "IP blocked successfully"}
    except Exception as e:
        log.error("IP 차단 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="POST", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to block IP")


@router.delete("/v1/admin/blocked-ips/{ip_address}")
async def unblock_ip(
    ip_address: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
    db: ExecutionHistoryDB = Depends(get_db),
    request: Request = None,
):
    """IP 차단 해제 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")

    ep = f"/v1/admin/blocked-ips/{ip_address}"
    actor_id = current_customer.get("sub")

    try:
        db_skin = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db_skin.unblock_ip(ip_address)
        
        if not success:
            raise HTTPException(status_code=404, detail="IP not found in blocked list")

        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request, success=True
        )
        return {"message": "IP unblocked successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("IP 차단 해제 실패: %s", e)
        log_audit(
            db=db, actor_customer_id=actor_id, target_customer_id=None,
            endpoint=ep, method="DELETE", user_role=role, request=request,
            success=False, error_message=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to unblock IP")


# ── 비즈니스 인텔리전스 ─────────────────────────────────────────────────────

@router.get("/v1/admin/dashboard/overview")
async def get_dashboard_overview(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """관리자 대시보드 개요 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        stats = db.get_stats()
        daily_stats = db.get_daily_stats(limit=7)
        
        return {
            "overview": {
                "total_analyses": stats.get("total_analyses", 0),
                "total_customers": stats.get("total_customers", 0),
                "last_analysis": stats.get("last_analysis"),
            },
            "recent_stats": daily_stats,
        }
    except Exception as e:
        log.error("대시보드 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard overview")


@router.get("/v1/admin/reports/usage")
async def get_usage_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 30,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """사용량 리포트 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        stats = db.get_daily_stats(start_date=start_date, end_date=end_date, limit=limit)
        return {"stats": stats, "total": len(stats)}
    except Exception as e:
        log.error("사용량 리포트 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve usage report")


@router.get("/v1/admin/reports/revenue")
async def get_revenue_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 30,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """수익 리포트 (관리자 전용)."""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Admin 또는 Analyst 권한이 필요합니다.")

    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        stats = db.get_daily_stats(start_date=start_date, end_date=end_date, limit=limit)
        
        # 수익 데이터만 필터링
        revenue_data = [
            {"date": s["date"], "total_revenue": s["total_revenue"]}
            for s in stats
        ]
        
        return {"revenue": revenue_data, "total": len(revenue_data)}
    except Exception as e:
        log.error("수익 리포트 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve revenue report")
