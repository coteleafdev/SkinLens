"""
health.py — 헬스 체크 및 장애 자동 복구 관련 라우터

기능:
- GET /v1/health - 상세한 서비스 헬스 체크
- GET /v1/admin/incidents - 장애 이벤트 조회
- GET /v1/admin/incidents/{incident_id} - 특정 장애 조회
- POST /v1/admin/incidents/{incident_id}/recover - 수동 복구 트리거
- GET /v1/admin/incidents/{incident_id}/recovery-actions - 복구 작업 조회
- POST /v1/admin/recovery-actions/{action_id}/rollback - 롤백 트리거
"""
import logging
import sqlite3
import psutil
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.db.skin_analysis_db import SkinAnalysisDB
from src.utils.config import get_db_path_from_env

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3", tags=["health", "incident-recovery"])


# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class HealthCheckResponse(BaseModel):
    status: str
    services: Dict[str, str]
    timestamp: str


class IncidentCreate(BaseModel):
    incident_type: str
    severity: str
    resource_type: str
    resource_id: str
    description: Optional[str] = None


class IncidentResponse(BaseModel):
    id: str
    incident_type: str
    severity: str
    resource_type: str
    resource_id: str
    detected_at: str
    resolved_at: Optional[str]
    status: str
    description: Optional[str]


class RecoveryActionCreate(BaseModel):
    action_type: str
    force: bool = False


class RecoveryActionResponse(BaseModel):
    recovery_action_id: str
    status: str


# ── 헬퍼 함수 ───────────────────────────────────────────────────────────────

def check_database_health() -> str:
    """데이터베이스 헬스 체크"""
    try:
        db_path = get_db_path_from_env()
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        return "healthy"
    except (sqlite3.Error, OSError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Database health check failed: {e}")
        return "unhealthy"


def check_disk_health() -> str:
    """디스크 헬스 체크"""
    try:
        disk_usage = psutil.disk_usage('/')
        usage_percent = disk_usage.percent
        if usage_percent < 80:
            return "healthy"
        elif usage_percent < 90:
            return "warning"
        else:
            return "critical"
    except (OSError, psutil.Error) as e:  # [FIX P2] 구체적 예외
        log.error(f"Disk health check failed: {e}")
        return "unhealthy"


def check_memory_health() -> str:
    """메모리 헬스 체크"""
    try:
        memory = psutil.virtual_memory()
        usage_percent = memory.percent
        if usage_percent < 70:
            return "healthy"
        elif usage_percent < 85:
            return "warning"
        else:
            return "critical"
    except (psutil.Error, OSError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Memory health check failed: {e}")
        return "unhealthy"


def check_cpu_health() -> str:
    """CPU 헬스 체크"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent < 70:
            return "healthy"
        elif cpu_percent < 85:
            return "warning"
        else:
            return "critical"
    except (psutil.Error, OSError) as e:  # [FIX P2] 구체적 예외
        log.error(f"CPU health check failed: {e}")
        return "unhealthy"


# ── 헬스 체크 엔드포인트 ─────────────────────────────────────────────────────

@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """상세한 서비스 헬스 체크"""
    services = {
        "api_server": "healthy",
        "database": check_database_health(),
        "disk": check_disk_health(),
        "memory": check_memory_health(),
        "cpu": check_cpu_health(),
    }
    
    # 전체 상태 결정
    overall_status = "healthy"
    if any(status == "critical" for status in services.values()):
        overall_status = "critical"
    elif any(status == "warning" for status in services.values()):
        overall_status = "warning"
    elif any(status == "unhealthy" for status in services.values()):
        overall_status = "unhealthy"
    
    return HealthCheckResponse(
        status=overall_status,
        services=services,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ── 장애 관리 엔드포인트 ─────────────────────────────────────────────────────

@router.get("/admin/incidents", response_model=List[IncidentResponse])
async def get_incidents(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
):
    """장애 이벤트 목록 조회"""
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        incidents = db.get_incidents(
            severity=severity,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [IncidentResponse(**incident) for incident in incidents]
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Failed to get incidents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str):
    """특정 장애 이벤트 조회"""
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        incident = db.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return IncidentResponse(**incident)
    except HTTPException:
        raise
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Failed to get incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/incidents/{incident_id}/recover", response_model=RecoveryActionResponse)
async def trigger_recovery(incident_id: str, action: RecoveryActionCreate):
    """수동 복구 트리거"""
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        # 장애 확인
        incident = db.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # 복구 작업 생성
        action_id = db.create_recovery_action(
            incident_id=incident_id,
            action_type=action.action_type,
        )
        
        # 복구 작업 상태를 in_progress로 변경
        db.update_recovery_action_status(action_id, "in_progress")
        
        # 로그 추가
        db.add_recovery_log(action_id, "info", f"Manual recovery triggered: {action.action_type}")
        
        return RecoveryActionResponse(
            recovery_action_id=action_id,
            status="in_progress",
        )
    except HTTPException:
        raise
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Failed to trigger recovery for incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/incidents/{incident_id}/recovery-actions")
async def get_recovery_actions(incident_id: str):
    """복구 작업 목록 조회"""
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        actions = db.get_recovery_actions(incident_id)
        return actions
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Failed to get recovery actions for incident {incident_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/recovery-actions/{action_id}/rollback")
async def trigger_rollback(action_id: str):
    """롤백 트리거"""
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        # 복구 작업 상태를 rolled_back으로 변경
        success = db.update_recovery_action_status(action_id, "rolled_back")
        if not success:
            raise HTTPException(status_code=404, detail="Recovery action not found")
        
        # 로그 추가
        db.add_recovery_log(action_id, "info", "Rollback triggered")
        
        return {"status": "rolling_back"}
    except HTTPException:
        raise
    except (sqlite3.Error, ValueError) as e:  # [FIX P2] 구체적 예외
        log.error(f"Failed to trigger rollback for action {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
