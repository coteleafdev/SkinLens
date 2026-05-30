"""
Auto Recovery Engine 테스트 - 장애 자동 복구 엔진
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.recovery.auto_recovery_engine import (
    IncidentType,
    Severity,
    RecoveryActionType,
    RecoveryEngine,
    HealthMonitor,
)


class TestIncidentType:
    """IncidentType Enum 테스트"""

    def test_incident_type_values(self):
        """장애 유형 값 검증"""
        assert IncidentType.SERVER_DOWN.value == "server_down"
        assert IncidentType.DATABASE_DOWN.value == "database_down"
        assert IncidentType.NETWORK_FAILURE.value == "network_failure"
        assert IncidentType.CPU_OVERLOAD.value == "cpu_overload"
        assert IncidentType.MEMORY_OVERLOAD.value == "memory_overload"
        assert IncidentType.DISK_FULL.value == "disk_full"


class TestSeverity:
    """Severity Enum 테스트"""

    def test_severity_values(self):
        """심각도 값 검증"""
        assert Severity.P0.value == "P0"
        assert Severity.P1.value == "P1"
        assert Severity.P2.value == "P2"
        assert Severity.P3.value == "P3"


class TestRecoveryActionType:
    """RecoveryActionType Enum 테스트"""

    def test_recovery_action_type_values(self):
        """복구 작업 유형 값 검증"""
        assert RecoveryActionType.RESTART.value == "restart"
        assert RecoveryActionType.FAILOVER.value == "failover"
        assert RecoveryActionType.SCALE_OUT.value == "scale_out"
        assert RecoveryActionType.ROLLBACK.value == "rollback"
        assert RecoveryActionType.DATA_RESTORE.value == "data_restore"


class TestRecoveryEngine:
    """RecoveryEngine 테스트"""

    @pytest.fixture
    def mock_db(self):
        """Mock 데이터베이스"""
        db = Mock()
        db.create_incident = Mock(return_value="incident_123")
        db.update_incident_status = Mock()
        db.create_recovery_action = Mock(return_value="action_123")
        db.update_recovery_action_status = Mock()
        db.add_recovery_log = Mock()
        return db

    @pytest.fixture
    def mock_alert_system(self):
        """Mock 알림 시스템"""
        alert_system = Mock()
        alert_system.send_incident_alert = AsyncMock()
        alert_system.send_recovery_alert = AsyncMock()
        return alert_system

    @pytest.fixture
    def recovery_engine(self, mock_db, mock_alert_system):
        """RecoveryEngine 인스턴스 생성"""
        return RecoveryEngine(db=mock_db, alert_system=mock_alert_system)

    def test_recovery_engine_initialization(self, mock_db, mock_alert_system):
        """RecoveryEngine 초기화 테스트"""
        engine = RecoveryEngine(db=mock_db, alert_system=mock_alert_system)
        assert engine.db is mock_db
        assert engine.alert_system is mock_alert_system
        assert isinstance(engine.recovery_playbooks, dict)

    def test_recovery_engine_playbook_registration(self, recovery_engine):
        """복구 플레이북 등록 검증"""
        expected_playbooks = [
            IncidentType.SERVER_DOWN.value,
            IncidentType.DATABASE_DOWN.value,
            IncidentType.CPU_OVERLOAD.value,
            IncidentType.MEMORY_OVERLOAD.value,
            IncidentType.DISK_FULL.value,
        ]
        
        for playbook in expected_playbooks:
            assert playbook in recovery_engine.recovery_playbooks

    @pytest.mark.asyncio
    async def test_detect_and_recover(self, recovery_engine, mock_db, mock_alert_system):
        """장애 감지 및 복구 테스트"""
        incident_id = await recovery_engine.detect_and_recover(
            incident_type=IncidentType.SERVER_DOWN.value,
            severity=Severity.P1.value,
            resource_type="server",
            resource_id="server_1",
            description="Server is down"
        )
        
        assert incident_id == "incident_123"
        mock_db.create_incident.assert_called_once()
        mock_alert_system.send_incident_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_and_recover_without_playbook(self, recovery_engine, mock_db, mock_alert_system):
        """플레이북이 없는 장애 유형 테스트"""
        incident_id = await recovery_engine.detect_and_recover(
            incident_type="unknown_incident",
            severity=Severity.P1.value,
            resource_type="server",
            resource_id="server_1"
        )
        
        assert incident_id == "incident_123"
        mock_db.update_incident_status.assert_called_with(incident_id, "failed")

    @pytest.mark.asyncio
    async def test_execute_playbook_success(self, recovery_engine, mock_db):
        """복구 플레이북 성공 실행 테스트"""
        await recovery_engine._execute_playbook(
            incident_id="incident_123",
            incident_type=IncidentType.SERVER_DOWN.value
        )
        
        mock_db.update_recovery_action_status.assert_called()
        mock_db.update_incident_status.assert_called_with("incident_123", "resolved")

    @pytest.mark.asyncio
    async def test_execute_playbook_failure(self, recovery_engine, mock_db):
        """복구 플레이북 실패 실행 테스트"""
        # 플레이북이 False를 반환하도록 모킹
        recovery_engine.recovery_playbooks[IncidentType.SERVER_DOWN.value] = AsyncMock(return_value=False)
        
        await recovery_engine._execute_playbook(
            incident_id="incident_123",
            incident_type=IncidentType.SERVER_DOWN.value
        )
        
        mock_db.update_incident_status.assert_called_with("incident_123", "failed")

    @pytest.mark.asyncio
    async def test_playbook_server_restart(self, recovery_engine, mock_db):
        """서버 재시작 플레이북 테스트"""
        result = await recovery_engine._playbook_server_restart("incident_123", "action_123")
        assert result is True
        mock_db.add_recovery_log.assert_called()

    @pytest.mark.asyncio
    async def test_playbook_database_recovery(self, recovery_engine, mock_db):
        """데이터베이스 복구 플레이북 테스트"""
        result = await recovery_engine._playbook_database_recovery("incident_123", "action_123")
        assert result is True
        mock_db.add_recovery_log.assert_called()

    @pytest.mark.asyncio
    async def test_playbook_cpu_scale_out(self, recovery_engine, mock_db):
        """CPU 스케일 아웃 플레이북 테스트"""
        result = await recovery_engine._playbook_cpu_scale_out("incident_123", "action_123")
        assert result is True
        mock_db.add_recovery_log.assert_called()

    @pytest.mark.asyncio
    async def test_playbook_memory_scale_out(self, recovery_engine, mock_db):
        """메모리 스케일 아웃 플레이북 테스트"""
        result = await recovery_engine._playbook_memory_scale_out("incident_123", "action_123")
        assert result is True
        mock_db.add_recovery_log.assert_called()

    @pytest.mark.asyncio
    async def test_playbook_disk_cleanup(self, recovery_engine, mock_db):
        """디스크 정리 플레이북 테스트"""
        result = await recovery_engine._playbook_disk_cleanup("incident_123", "action_123")
        assert result is True
        mock_db.add_recovery_log.assert_called()

    @pytest.mark.asyncio
    async def test_rollback_recovery(self, recovery_engine, mock_db):
        """복구 롤백 테스트"""
        result = await recovery_engine.rollback_recovery("action_123")
        assert result is True
        mock_db.update_recovery_action_status.assert_called_with("action_123", "rolled_back")


class TestHealthMonitor:
    """HealthMonitor 테스트"""

    @pytest.fixture
    def mock_recovery_engine(self):
        """Mock 복구 엔진"""
        engine = Mock()
        engine.detect_and_recover = AsyncMock()
        return engine

    @pytest.fixture
    def health_monitor(self, mock_recovery_engine):
        """HealthMonitor 인스턴스 생성"""
        return HealthMonitor(recovery_engine=mock_recovery_engine)

    def test_health_monitor_initialization(self, mock_recovery_engine):
        """HealthMonitor 초기화 테스트"""
        monitor = HealthMonitor(recovery_engine=mock_recovery_engine)
        assert monitor.recovery_engine is mock_recovery_engine
        assert monitor.monitoring_enabled is True
        assert monitor.check_interval == 30

    def test_stop_monitoring(self, health_monitor):
        """모니터링 중지 테스트"""
        health_monitor.stop_monitoring()
        assert health_monitor.monitoring_enabled is False

    @pytest.mark.asyncio
    async def test_check_system_health_cpu_overload(self, health_monitor, mock_recovery_engine):
        """CPU 오버로드 감지 테스트"""
        with patch('psutil.cpu_percent', return_value=95):
            await health_monitor._check_system_health()
        
        mock_recovery_engine.detect_and_recover.assert_called()

    @pytest.mark.asyncio
    async def test_check_system_health_memory_overload(self, health_monitor, mock_recovery_engine):
        """메모리 오버로드 감지 테스트"""
        mock_memory = Mock()
        mock_memory.percent = 96
        with patch('psutil.virtual_memory', return_value=mock_memory):
            await health_monitor._check_system_health()
        
        mock_recovery_engine.detect_and_recover.assert_called()

    @pytest.mark.asyncio
    async def test_check_system_health_disk_full(self, health_monitor, mock_recovery_engine):
        """디스크 꽉 참 감지 테스트"""
        mock_disk = Mock()
        mock_disk.percent = 91
        with patch('psutil.disk_usage', return_value=mock_disk):
            await health_monitor._check_system_health()
        
        mock_recovery_engine.detect_and_recover.assert_called()

    @pytest.mark.asyncio
    async def test_check_system_health_normal(self, health_monitor, mock_recovery_engine):
        """정상 시스템 상태 테스트"""
        with patch('psutil.cpu_percent', return_value=50):
            mock_memory = Mock()
            mock_memory.percent = 60
            with patch('psutil.virtual_memory', return_value=mock_memory):
                mock_disk = Mock()
                mock_disk.percent = 70
                with patch('psutil.disk_usage', return_value=mock_disk):
                    await health_monitor._check_system_health()
        
        # 정상 상태에서는 복구가 호출되지 않아야 함
        mock_recovery_engine.detect_and_recover.assert_not_called()


class TestRecoveryIntegration:
    """복구 엔진 통합 테스트"""

    def test_enum_completeness(self):
        """Enum 완전성 검증"""
        # 모든 Enum이 정의되어 있어야 함
        assert len(IncidentType) == 6
        assert len(Severity) == 4
        assert len(RecoveryActionType) == 5

    def test_recovery_engine_with_default_alert_system(self, mock_db):
        """기본 알림 시스템으로 초기화 테스트"""
        engine = RecoveryEngine(db=mock_db)
        assert engine.alert_system is not None

    @pytest.mark.asyncio
    async def test_full_recovery_flow(self, mock_db, mock_alert_system):
        """전체 복구 흐름 테스트"""
        engine = RecoveryEngine(db=mock_db, alert_system=mock_alert_system)
        
        # 장애 감지 및 복구
        incident_id = await engine.detect_and_recover(
            incident_type=IncidentType.SERVER_DOWN.value,
            severity=Severity.P1.value,
            resource_type="server",
            resource_id="server_1"
        )
        
        # 장애 생성 확인
        mock_db.create_incident.assert_called_once()
        
        # 알림 전송 확인
        mock_alert_system.send_incident_alert.assert_called_once()
        
        # 복구 작업 생성 확인
        mock_db.create_recovery_action.assert_called_once()
