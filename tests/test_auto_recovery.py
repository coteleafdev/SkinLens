"""
test_auto_recovery.py — 장애 자동 복구 기능 테스트
"""
import pytest
import asyncio
from src.db.skin_analysis_db import SkinAnalysisDB
from src.recovery import RecoveryEngine, IncidentType, Severity
from src.notification import AlertSystem


@pytest.fixture
def db():
    """테스트용 DB 인스턴스"""
    db = SkinAnalysisDB(db_path=":memory:")
    return db


@pytest.fixture
def alert_system():
    """테스트용 알림 시스템"""
    return AlertSystem()


@pytest.fixture
def recovery_engine(db, alert_system):
    """테스트용 복구 엔진"""
    return RecoveryEngine(db, alert_system)


def test_create_incident(db):
    """장애 이벤트 생성 테스트"""
    incident_id = db.create_incident(
        incident_type=IncidentType.CPU_OVERLOAD.value,
        severity=Severity.P1.value,
        resource_type="cpu",
        resource_id="system",
        description="CPU usage: 95%",
    )
    
    assert incident_id is not None
    assert len(incident_id) > 0
    
    # 장애 조회
    incident = db.get_incident(incident_id)
    assert incident is not None
    assert incident["incident_type"] == IncidentType.CPU_OVERLOAD.value
    assert incident["severity"] == Severity.P1.value
    assert incident["status"] == "detected"


def test_update_incident_status(db):
    """장애 상태 업데이트 테스트"""
    incident_id = db.create_incident(
        incident_type=IncidentType.CPU_OVERLOAD.value,
        severity=Severity.P1.value,
        resource_type="cpu",
        resource_id="system",
    )
    
    # 상태 업데이트
    success = db.update_incident_status(incident_id, "resolved")
    assert success is True
    
    # 상태 확인
    incident = db.get_incident(incident_id)
    assert incident["status"] == "resolved"
    assert incident["resolved_at"] is not None


def test_create_recovery_action(db):
    """복구 작업 생성 테스트"""
    incident_id = db.create_incident(
        incident_type=IncidentType.CPU_OVERLOAD.value,
        severity=Severity.P1.value,
        resource_type="cpu",
        resource_id="system",
    )
    
    action_id = db.create_recovery_action(
        incident_id=incident_id,
        action_type="restart",
    )
    
    assert action_id is not None
    assert len(action_id) > 0
    
    # 복구 작업 조회
    actions = db.get_recovery_actions(incident_id)
    assert len(actions) == 1
    assert actions[0]["action_type"] == "restart"
    assert actions[0]["action_status"] == "pending"


def test_update_recovery_action_status(db):
    """복구 작업 상태 업데이트 테스트"""
    incident_id = db.create_incident(
        incident_type=IncidentType.CPU_OVERLOAD.value,
        severity=Severity.P1.value,
        resource_type="cpu",
        resource_id="system",
    )
    
    action_id = db.create_recovery_action(
        incident_id=incident_id,
        action_type="restart",
    )
    
    # 상태 업데이트
    success = db.update_recovery_action_status(action_id, "in_progress")
    assert success is True
    
    # 상태 확인
    actions = db.get_recovery_actions(incident_id)
    assert actions[0]["action_status"] == "in_progress"
    assert actions[0]["started_at"] is not None


def test_add_recovery_log(db):
    """복구 로그 추가 테스트"""
    incident_id = db.create_incident(
        incident_type=IncidentType.CPU_OVERLOAD.value,
        severity=Severity.P1.value,
        resource_type="cpu",
        resource_id="system",
    )
    
    action_id = db.create_recovery_action(
        incident_id=incident_id,
        action_type="restart",
    )
    
    log_id = db.add_recovery_log(
        recovery_action_id=action_id,
        log_level="info",
        message="Test log message",
    )
    
    assert log_id is not None
    assert len(log_id) > 0
    
    # 로그 조회
    logs = db.get_recovery_logs(action_id)
    assert len(logs) == 1
    assert logs[0]["log_level"] == "info"
    assert logs[0]["message"] == "Test log message"


@pytest.mark.asyncio
async def test_detect_and_recover(recovery_engine):
    """장애 감지 및 복구 테스트"""
    incident_id = await recovery_engine.detect_and_recover(
        incident_type=IncidentType.CPU_OVERLOAD.value,
        severity=Severity.P1.value,
        resource_type="cpu",
        resource_id="system",
        description="CPU usage: 95%",
    )
    
    assert incident_id is not None
    
    # 장애 상태 확인
    incident = recovery_engine.db.get_incident(incident_id)
    assert incident is not None
    # 복구가 완료되었는지 확인 (비동기이므로 잠시 대기 필요)
    await asyncio.sleep(3)
    
    incident = recovery_engine.db.get_incident(incident_id)
    assert incident["status"] in ["resolved", "recovering", "failed"]


def test_get_incidents(db):
    """장애 목록 조회 테스트"""
    # 여러 장애 생성
    for i in range(3):
        db.create_incident(
            incident_type=IncidentType.CPU_OVERLOAD.value,
            severity=Severity.P1.value,
            resource_type="cpu",
            resource_id=f"system_{i}",
        )
    
    # 목록 조회
    incidents = db.get_incidents(limit=10)
    assert len(incidents) >= 3
    
    # 필터링 테스트
    p1_incidents = db.get_incidents(severity=Severity.P1.value)
    assert len(p1_incidents) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
